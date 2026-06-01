"""Unified CoLearn server — single process, single port.

Starts FastAPI with REST + WebSocket, using nanobot AgentLoop as a library.
No separate standalone gateway is required.

Usage:
    python -m colearn.server
    python -m colearn.server --port 8001
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from colearn.nanobot_bootstrap import ensure_nanobot_on_path
from colearn.paths import colearn_repo_root


def _load_repo_env(repo_root: Path) -> None:
    env_path = repo_root / ".env"
    if not env_path.exists():
        return

    # Keep existing process env values; only fill in missing local defaults.
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        try:
            parts = shlex.split(line, comments=True, posix=True)
        except ValueError:
            continue
        if len(parts) != 1 or "=" not in parts[0]:
            continue
        key, value = parts[0].split("=", 1)
        key = key.strip()
        if key:
            os.environ.setdefault(key, value)


def _hydrate_provider_env_aliases() -> None:
    """Promote legacy provider keys into the names the current runtime expects."""
    if not os.environ.get("DEEPSEEK_API_KEY"):
        legacy_openai_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
        if legacy_openai_key:
            os.environ["DEEPSEEK_API_KEY"] = legacy_openai_key


def _sync_runtime_from_settings(repo_root: Path) -> None:
    """Prefer the persisted active settings profile when hydrating runtime env."""
    try:
        from colearn.api.state import SettingsStateService, _provider_env_key
        from colearn.storage.json_store import JsonStateStore
    except (ImportError, ModuleNotFoundError):
        return

    state_root = repo_root / ".colearn" / "state"
    service = SettingsStateService(
        state_store=JsonStateStore(root=state_root),
        env_path=repo_root / ".env",
    )
    catalog = service.catalog()
    service.apply_catalog(catalog)

    services = dict(catalog.get("services") or {})
    llm_profile, llm_model = service._resolve_active_selection(services.get("llm"))
    provider_name = service._provider_name(llm_profile)
    provider_env_key = _provider_env_key(provider_name)
    provider_api_key = service._provider_api_key(llm_profile)
    provider_api_base = service._string_or_none(llm_profile.get("base_url"))
    provider_model = (
        service._string_or_none(llm_model.get("model"))
        or service._string_or_none(llm_model.get("name"))
    )

    if provider_env_key and provider_api_key:
        os.environ[provider_env_key] = provider_api_key
    if provider_name == "deepseek":
        if provider_api_key:
            os.environ["DEEPSEEK_API_KEY"] = provider_api_key
        if provider_api_base:
            os.environ["DEEPSEEK_API_BASE"] = provider_api_base
        if provider_model:
            os.environ["DEEPSEEK_MODEL"] = provider_model

    embedding_profile, embedding_model = service._resolve_active_selection(services.get("embedding"))
    embedding_api_key = service._string_or_none(embedding_profile.get("api_key"))
    embedding_api_base = service._string_or_none(embedding_profile.get("base_url"))
    embedding_model_name = (
        service._string_or_none(embedding_model.get("model"))
        or service._string_or_none(embedding_model.get("name"))
    )
    embedding_send_dimensions = embedding_model.get("send_dimensions", False)

    if embedding_api_key:
        os.environ["EMBEDDING_API_KEY"] = embedding_api_key
    if embedding_api_base:
        os.environ["EMBEDDING_BASE_URL"] = embedding_api_base
    if embedding_model_name:
        os.environ["EMBEDDING_MODEL"] = embedding_model_name
    os.environ["EMBEDDING_SEND_DIMENSIONS"] = "true" if bool(embedding_send_dimensions) else "false"


def _try_spawn_lightrag(repo_root: Path) -> Any:
    """Attempt to auto-start LightRAG server as a managed subprocess.

    Returns the subprocess.Popen handle if spawned, None otherwise.
    The process is daemonized so it dies when the parent exits.
    """
    import json
    import subprocess
    import socket

    config_path = repo_root / ".colearn" / "lightrag.json"
    if not config_path.exists():
        return None

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if not config.get("enabled"):
        return None

    provider = config.get("provider", {})
    if isinstance(provider, dict):
        provider_name = provider.get("name", "local")
        base_url = provider.get("base_url", "http://127.0.0.1:9621")
    else:
        provider_name = str(provider or "local")
        base_url = "http://127.0.0.1:9621"

    if provider_name not in ("local", "server"):
        return None

    # Parse port from base_url
    port = 9621
    try:
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        if parsed.port:
            port = parsed.port
    except (ValueError, TypeError):
        pass

    # Check if already running
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            # Already running — check if it needs reconfiguration by looking at the log
            log_path = repo_root / ".colearn" / "lightrag-store" / "lightrag.log"
            needs_restart = False
            if log_path.exists():
                log_tail = log_path.read_text(encoding="utf-8", errors="ignore")[-500:]
                if "binding=ollama" in log_tail and os.environ.get("SILICONFLOW_API_KEY"):
                    needs_restart = True
            if not needs_restart:
                print(f"  LightRAG: ready", file=sys.stderr)
                return None
            # Kill the old process and respawn with correct config
            try:
                import signal
                # Find and kill process on port
                import subprocess as _sp
                result = _sp.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=3)
                for pid_str in result.stdout.strip().split():
                    try:
                        os.kill(int(pid_str), signal.SIGTERM)
                    except (ProcessLookupError, ValueError):
                        pass
                import time as _time
                _time.sleep(1)
                print(f"  LightRAG: killed old process (was using ollama binding, switching to openai)")
            except (OSError, subprocess.SubprocessError):
                pass
    except (ConnectionRefusedError, OSError, TimeoutError):
        pass

    # Try to spawn lightrag-server
    lightrag_bin = None
    for candidate in ["lightrag-server", "lightrag"]:
        import shutil
        if shutil.which(candidate):
            lightrag_bin = candidate
            break

    # Also check if we can run it as a Python module
    if lightrag_bin is None:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "lightrag.api", "--help"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                lightrag_bin = "__module__"
        except (subprocess.TimeoutExpired, OSError):
            pass

    if lightrag_bin is None:
        print(
            f"  LightRAG: not installed (port {port} unreachable, no lightrag binary found). "
            "Knowledge retrieval will use fallback mode.",
            file=sys.stderr,
        )
        return None

    try:
        working_dir = repo_root / ".colearn" / "lightrag-store"
        working_dir.mkdir(parents=True, exist_ok=True)
        input_dir = repo_root / ".colearn" / "knowledge"

        env = {**os.environ}
        env["LLM_BINDING"] = "openai"
        env["LLM_MODEL"] = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
        env["LLM_BINDING_HOST"] = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com") + "/v1"
        env["OPENAI_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")
        env["EMBEDDING_BINDING"] = "openai"
        env["EMBEDDING_MODEL"] = os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")
        env["EMBEDDING_BINDING_HOST"] = os.environ.get("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1/embeddings").replace("/embeddings", "")
        env["EMBEDDING_BINDING_API_KEY"] = os.environ.get("SILICONFLOW_API_KEY") or os.environ.get("EMBEDDING_API_KEY", "")
        env["EMBEDDING_DIM"] = os.environ.get("EMBEDDING_DIM", "1024")

        if lightrag_bin == "__module__":
            cmd = [sys.executable, "-m", "lightrag.api", "--port", str(port), "--host", "127.0.0.1"]
        else:
            cmd = [
                lightrag_bin,
                "--port", str(port),
                "--host", "127.0.0.1",
                "--llm-binding", "openai",
                "--embedding-binding", "openai",
                "--working-dir", str(working_dir),
            ]
            if input_dir.exists():
                cmd.extend(["--input-dir", str(input_dir)])

        proc = subprocess.Popen(
            cmd,
            cwd=str(working_dir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"  LightRAG: spawned (pid={proc.pid}, port={port})")
        return proc
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  LightRAG: spawn failed ({exc}). Using fallback mode.", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="CoLearn unified server")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--config", default=None, help="nanobot config path")
    parser.add_argument("--workspace", default=None, help="nanobot workspace path")
    parser.add_argument("--skip-lightrag", action="store_true", help="skip LightRAG spawn")
    args = parser.parse_args()

    repo_root = colearn_repo_root()
    config_path = args.config or str(repo_root / ".colearn" / "nanobot-v0.2-slim.config.json")
    workspace = args.workspace or str(repo_root / ".colearn" / "nanobot-workspace")

    _load_repo_env(repo_root)
    _hydrate_provider_env_aliases()
    _sync_runtime_from_settings(repo_root)
    os.environ.setdefault("COLEARN_NANOBOT_TOKEN_ISSUE_SECRET", "")
    os.environ.setdefault("COLEARN_REPO_ROOT", str(repo_root))
    os.environ.setdefault("COLEARN_NANOBOT_WORKSPACE", str(workspace))
    os.environ.setdefault("DEEPSEEK_API_KEY", "")
    os.environ.setdefault("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    os.environ.setdefault("DEEPSEEK_MODEL", "deepseek-v4-flash")
    os.environ.setdefault("EMBEDDING_API_KEY", "")
    os.environ.setdefault("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1/embeddings")
    os.environ.setdefault("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")
    os.environ.setdefault("EMBEDDING_SEND_DIMENSIONS", "false")

    nanobot_root = ensure_nanobot_on_path()
    if nanobot_root is None:
        print(
            "Warning: bundled nanobot runtime not found under third_party. "
            "WS runtime may fail to initialize.",
            file=sys.stderr,
        )

    # Initialize nanobot AgentLoop
    try:
        import tempfile
        from nanobot.config.loader import load_config
        from nanobot.agent.loop import AgentLoop
        from nanobot.providers.factory import build_provider_snapshot
        from nanobot.session.manager import SessionManager

        # Expand ${VAR} placeholders in config (nanobot's load_config doesn't)
        with open(config_path, encoding="utf-8") as f:
            raw = f.read()
        expanded = os.path.expandvars(raw)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            tmp.write(expanded)
            tmp_config_path = tmp.name

        config = load_config(Path(tmp_config_path))
        provider_snapshot = build_provider_snapshot(config)
        session_manager = SessionManager(Path(workspace))

        agent = AgentLoop.from_config(
            config,
            bus=None,
            provider=provider_snapshot.provider,
            model=provider_snapshot.model,
            context_window_tokens=provider_snapshot.context_window_tokens,
            session_manager=session_manager,
            provider_snapshot_loader=None,
        )

        # Inject into deps module so ws_handler can access via _deps
        import colearn.api.dependencies as _deps
        _deps.agent_loop = agent
        _deps.session_manager = session_manager
        print(f"AgentLoop initialized: model={provider_snapshot.model}")
        if nanobot_root is not None:
            print(f"  Nanobot: {nanobot_root}")

    except (ImportError, FileNotFoundError, ValueError, OSError) as exc:
        print(f"Warning: AgentLoop init failed ({exc}). WS will return errors but REST works.", file=sys.stderr)

    # Auto-spawn LightRAG server if configured as "local" and not already running
    if not args.skip_lightrag:
        _lightrag_proc = _try_spawn_lightrag(repo_root)
    else:
        _lightrag_proc = None

    # Start uvicorn
    import uvicorn
    from colearn.api.app import app

    print(f"CoLearn server starting on {args.host}:{args.port}")
    print(f"  REST: http://{args.host}:{args.port}/api/v1/...")
    print(f"  WS:   ws://{args.host}:{args.port}/")
    print(f"  Bootstrap: http://{args.host}:{args.port}/webui/bootstrap")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
