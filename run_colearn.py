"""Launch NanoBot with the CoLearn plugin pre-installed.

This script is the recommended entry point for running NanoBot with CoLearn
attached. It supports three modes:

    serve   start the OpenAI-compatible HTTP API (default; matches `nanobot serve`)
    webui   start the WebUI gateway (matches `nanobot gateway`, browser UI)
    run     execute a single SDK turn from the command line and print the result
    chat    open an interactive REPL bound to one CoLearn session

In all modes the CoLearn lifecycle hooks (session binder, preflight, blackboard
monitor, finalize) and the `/colearn` dashboard tool are installed before any
turn runs. The script does not modify NanoBot source.

Examples::

    python run_colearn.py serve --port 8765
    python run_colearn.py webui --port 8080
    python run_colearn.py run --message "I want to learn machine learning" --session user-42
    python run_colearn.py chat --session user-42

The `--config` flag is forwarded to NanoBot's config loader. When omitted, the
default `~/.nanobot/config.json` is used.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any
from types import ModuleType, SimpleNamespace


def _install_dulwich_stub() -> None:
    """Install a tiny dulwich shim so NanoBot can run without the dependency."""

    def _init_repo(path: str) -> None:
        workspace = Path(path)
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / ".git").mkdir(exist_ok=True)

    def _commit(*_args, **_kwargs) -> bytes:
        return b"\0" * 20

    def _status(*_args, **_kwargs):
        return SimpleNamespace(unstaged=[], staged={})

    def _annotate(*_args, **_kwargs):
        return []

    def _diff(*_args, **kwargs) -> None:
        outstream = kwargs.get("outstream")
        if outstream is None:
            return
        try:
            outstream.write("")
        except TypeError:
            outstream.write(b"")

    class _Repo:
        def __init__(self, path: str):
            self.path = Path(path)
            self.refs: dict[bytes, bytes] = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def __getitem__(self, _key):
            raise KeyError(_key)

    dulwich_mod = ModuleType("dulwich")
    porcelain_mod = ModuleType("dulwich.porcelain")
    repo_mod = ModuleType("dulwich.repo")

    porcelain_mod.init = _init_repo
    porcelain_mod.add = lambda *_args, **_kwargs: None
    porcelain_mod.commit = _commit
    porcelain_mod.status = _status
    porcelain_mod.annotate = _annotate
    porcelain_mod.diff = _diff
    repo_mod.Repo = _Repo

    dulwich_mod.porcelain = porcelain_mod
    dulwich_mod.repo = repo_mod

    sys.modules["dulwich"] = dulwich_mod
    sys.modules["dulwich.porcelain"] = porcelain_mod
    sys.modules["dulwich.repo"] = repo_mod


# Mock dulwich if missing so NanoBot's GitStore can degrade cleanly.
try:
    import dulwich  # noqa: F401
except ImportError:
    _install_dulwich_stub()

REPO_ROOT = Path(__file__).resolve().parent
SNAPSHOT_PATH = REPO_ROOT / "third_party" / "nanobot-0.2.1"
if SNAPSHOT_PATH.is_dir() and str(SNAPSHOT_PATH) not in sys.path:
    sys.path.insert(0, str(SNAPSHOT_PATH))

# Import after sys.path tweak so the vendored snapshot is preferred when present.
from nanobot import Nanobot  # noqa: E402

from colearn.colearn_plugin import CoLearnPlugin  # noqa: E402
from colearn.colearn_runtime import enable_for_nanobot, install_colearn  # noqa: E402

DEFAULT_STATE_ROOT = ".colearn/state/sessions"
DEFAULT_WIKI_INDEX = "knowledge/generated"


def _build_plugin(args: argparse.Namespace) -> CoLearnPlugin:
    return CoLearnPlugin(
        {
            "state_root": args.state_root,
            "wiki_index_dir": args.wiki_index_dir,
        }
    )


def _build_bot(args: argparse.Namespace) -> Nanobot:
    config_path = args.config
    if config_path is not None:
        config_path = str(Path(config_path).expanduser())
    return Nanobot.from_config(config_path, workspace=args.workspace)


def _configure_webui_gateway(config: Any, *, port: int | None) -> int:
    """Ensure the browser WebUI always has a local websocket channel to talk to."""
    resolved_port = int(port if port is not None else config.gateway.port)
    config.gateway.host = "127.0.0.1"
    config.gateway.port = resolved_port

    extras = dict(getattr(config.channels, "__pydantic_extra__", None) or {})
    websocket_cfg = extras.get("websocket")
    if not isinstance(websocket_cfg, dict):
        websocket_cfg = {}
    websocket_cfg["enabled"] = True
    websocket_cfg["host"] = "127.0.0.1"
    websocket_cfg["port"] = resolved_port
    websocket_cfg.setdefault("path", "/")
    websocket_cfg.setdefault("allow_from", ["*"])
    websocket_cfg.setdefault("streaming", True)
    extras["websocket"] = websocket_cfg
    config.channels.__pydantic_extra__ = extras
    return resolved_port


def _enable_gateway_verbose_logging() -> None:
    from loguru import logger

    from nanobot.cli.commands import _log_handler_id

    logger.remove(_log_handler_id)
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <5}</level> | "
            "<cyan>{extra[channel]}</cyan> | "
            "<level>{message}</level>"
        ),
        level="DEBUG",
        colorize=None,
        filter=lambda record: record["extra"].setdefault("channel", "-") or True,
    )


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the OpenAI-compatible HTTP API with CoLearn attached."""
    try:
        from aiohttp import web
    except ImportError:
        print(
            "aiohttp is required for `serve`. Install with: pip install 'nanobot-ai[api]'",
            file=sys.stderr,
        )
        return 1

    from nanobot.agent.loop import AgentLoop
    from nanobot.api.server import create_app
    from nanobot.bus.queue import MessageBus
    from nanobot.providers.image_generation import image_gen_provider_configs
    from nanobot.session.manager import SessionManager
    from nanobot.utils.helpers import sync_workspace_templates

    from nanobot.config.loader import load_config, resolve_config_env_vars, set_config_path

    config_path = None
    if args.config:
        config_path = Path(args.config).expanduser().resolve()
        if not config_path.exists():
            print(f"Config not found: {config_path}", file=sys.stderr)
            return 1
        set_config_path(config_path)
    runtime_config = resolve_config_env_vars(load_config(config_path))
    if args.workspace:
        runtime_config.agents.defaults.workspace = args.workspace

    sync_workspace_templates(runtime_config.workspace_path)
    bus = MessageBus()
    session_manager = SessionManager(runtime_config.workspace_path)

    agent_loop = AgentLoop.from_config(
        runtime_config,
        bus,
        session_manager=session_manager,
        image_generation_provider_configs=image_gen_provider_configs(runtime_config),
    )
    setattr(bus, "_agent_loop", agent_loop)

    install_colearn(agent_loop, plugin=_build_plugin(args))

    api_cfg = runtime_config.api
    host = args.host or api_cfg.host
    port = args.port or api_cfg.port
    timeout = args.timeout if args.timeout is not None else api_cfg.timeout
    resolved = runtime_config.resolve_preset()
    api_app = create_app(agent_loop, model_name=resolved.model, request_timeout=timeout)

    async def _on_startup(_):
        await agent_loop._connect_mcp()

    async def _on_cleanup(_):
        await agent_loop.close_mcp()

    api_app.on_startup.append(_on_startup)
    api_app.on_cleanup.append(_on_cleanup)

    print(f"CoLearn + NanoBot listening on http://{host}:{port}/v1/chat/completions")
    print(f"  model:   {resolved.model}")
    print(f"  session: api:default")
    print(f"  timeout: {timeout}s")
    web.run_app(api_app, host=host, port=port, print=lambda _msg: None)
    return 0


def cmd_webui(args: argparse.Namespace) -> int:
    """Start the NanoBot WebUI gateway with CoLearn auto-installed.

    Uses NanoBot's shared gateway runtime after forcing a local websocket
    channel on the selected port. This keeps the upstream WebUI HTTP surface,
    cron service, and channel routing while making `run_colearn.py webui`
    genuinely turnkey.
    """
    enable_for_nanobot(_build_plugin(args))
    from nanobot.cli.commands import _load_runtime_config, _run_gateway

    try:
        if args.verbose:
            _enable_gateway_verbose_logging()
        config = _load_runtime_config(args.config, args.workspace)
        resolved_port = _configure_webui_gateway(config, port=args.port)
        _run_gateway(
            config,
            port=resolved_port,
            health_server_enabled=False,
        )
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run a single SDK turn and print the result."""
    bot = _build_bot(args)
    plugin = _build_plugin(args)
    install_colearn(bot, plugin=plugin)
    if args.session:
        plugin.setup_session(args.session)
    result = asyncio.run(bot.run(args.message, session_key=args.session or "sdk:default"))
    print(result.content)
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    """Run a tiny interactive REPL bound to one CoLearn session."""
    bot = _build_bot(args)
    plugin = _build_plugin(args)
    install_colearn(bot, plugin=plugin)
    session_key = args.session or "chat:default"
    plugin.setup_session(session_key)
    print(f"CoLearn chat ready. session={session_key}. Empty line or Ctrl-D to exit.")
    try:
        while True:
            try:
                message = input("> ").strip()
            except EOFError:
                print()
                break
            if not message:
                break
            result = asyncio.run(bot.run(message, session_key=session_key))
            print(result.content)
    except KeyboardInterrupt:
        print()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_colearn",
        description="Launch NanoBot with the CoLearn plugin attached.",
    )
    parser.add_argument("--config", help="Path to nanobot config (~/.nanobot/config.json by default)")
    parser.add_argument("--workspace", help="Override workspace directory")
    parser.add_argument("--state-root", default=DEFAULT_STATE_ROOT, help="CoLearn session state root")
    parser.add_argument("--wiki-index-dir", default=DEFAULT_WIKI_INDEX, help="Wiki generated index dir")

    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the HTTP API server (default)")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--timeout", type=float, default=None)
    serve.set_defaults(func=cmd_serve)

    webui = subparsers.add_parser("webui", help="Run the NanoBot WebUI gateway")
    webui.add_argument("--port", type=int, default=None)
    webui.add_argument("--verbose", action="store_true")
    webui.set_defaults(func=cmd_webui)

    run = subparsers.add_parser("run", help="Run a single SDK turn")
    run.add_argument("--message", required=True)
    run.add_argument("--session", default=None)
    run.set_defaults(func=cmd_run)

    chat = subparsers.add_parser("chat", help="Tiny interactive REPL")
    chat.add_argument("--session", default=None)
    chat.set_defaults(func=cmd_chat)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # Default to serve when no subcommand is given.
        args = parser.parse_args(["serve", *(argv or [])])
    os.makedirs(args.state_root, exist_ok=True)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
