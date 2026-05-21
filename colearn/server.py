"""Unified CoLearn server — single process, single port.

Starts FastAPI with REST + WebSocket, using nanobot AgentLoop as a library.
No separate nanobot gateway needed.

Usage:
    python -m colearn.server
    python -m colearn.server --port 8001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from colearn.paths import colearn_repo_root


def main():
    parser = argparse.ArgumentParser(description="CoLearn unified server")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--config", default=None, help="nanobot config path")
    parser.add_argument("--workspace", default=None, help="nanobot workspace path")
    args = parser.parse_args()

    repo_root = colearn_repo_root()
    config_path = args.config or str(repo_root / ".colearn" / "nanobot-v0.2-slim.config.json")
    workspace = args.workspace or str(repo_root / ".colearn" / "nanobot-workspace")

    # nanobot's config validator requires this env var (was for the old standalone
    # gateway's WS auth). We don't run the standalone gateway anymore — empty default.
    import os
    os.environ.setdefault("COLEARN_NANOBOT_TOKEN_ISSUE_SECRET", "")

    # Initialize nanobot AgentLoop
    try:
        import json
        import os
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

        # Inject into WS handler
        from colearn.api.ws_handler import set_agent_loop
        set_agent_loop(agent, session_manager)
        print(f"AgentLoop initialized: model={provider_snapshot.model}")

    except Exception as exc:
        print(f"Warning: AgentLoop init failed ({exc}). WS will return errors but REST works.", file=sys.stderr)

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
