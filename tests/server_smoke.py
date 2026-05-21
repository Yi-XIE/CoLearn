"""Minimal live smoke for the unified CoLearn server startup path.

Checks:
1. ``python -m colearn.server`` boots on localhost
2. ``GET /webui/bootstrap`` returns token + ws_path
3. ``WS /api/v1/ws`` accepts ``new_chat`` and returns ``ready`` + ``attached``
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_for_bootstrap(base_url: str, timeout_seconds: float = 20.0) -> dict[str, object]:
    started = time.time()
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.time() - started < timeout_seconds:
            try:
                response = await client.get(f"{base_url}/webui/bootstrap")
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    return payload
            except Exception as exc:  # pragma: no cover - smoke diagnostics only
                last_error = exc
                await asyncio.sleep(0.25)
        raise RuntimeError(f"bootstrap never became ready: {last_error}")


async def _run_smoke(port: int) -> None:
    base_url = f"http://127.0.0.1:{port}"
    payload = await _wait_for_bootstrap(base_url)
    token = str(payload.get("token") or "")
    ws_path = str(payload.get("ws_path") or "")
    if not token:
        raise RuntimeError("bootstrap payload missing token")
    if ws_path != "/api/v1/ws":
        raise RuntimeError(f"unexpected ws_path: {ws_path!r}")

    ws_url = f"ws://127.0.0.1:{port}{ws_path}"
    async with websockets.connect(ws_url) as websocket:
        await websocket.send(json.dumps({"type": "new_chat"}))
        first = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5.0))
        second = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5.0))
    if first.get("event") != "ready":
        raise RuntimeError(f"expected ready event, got: {first}")
    if not first.get("chat_id"):
        raise RuntimeError(f"ready event missing chat_id: {first}")
    if second.get("event") != "attached":
        raise RuntimeError(f"expected attached event, got: {second}")
    if second.get("chat_id") != first.get("chat_id"):
        raise RuntimeError(f"attached chat_id mismatch: {second} vs {first}")

    print(f"bootstrap token : OK ({token[:12]}...)")
    print(f"ws path         : OK ({ws_path})")
    print(f"new_chat ready  : OK ({first['chat_id']})")


def main() -> int:
    port = _pick_port()
    tmp_state = tempfile.mkdtemp(prefix="colearn-server-smoke-")
    env = os.environ.copy()
    env.setdefault("COLEARN_REPO_ROOT", str(ROOT))
    env["COLEARN_STATE_ROOT"] = tmp_state
    env.setdefault("COLEARN_NANOBOT_WORKSPACE", str(ROOT / ".colearn" / "nanobot-workspace"))
    env.setdefault("COLEARN_NANOBOT_TOKEN_ISSUE_SECRET", "")

    command = [
        sys.executable,
        "-m",
        "colearn.server",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    server = subprocess.Popen(
        command,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        asyncio.run(_run_smoke(port))
    except Exception:
        server.terminate()
        try:
            stdout, stderr = server.communicate(timeout=5.0)
        except subprocess.TimeoutExpired:
            server.kill()
            stdout, stderr = server.communicate()
        if stdout.strip():
            print(stdout.strip())
        if stderr.strip():
            print(stderr.strip(), file=sys.stderr)
        raise
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.communicate(timeout=5.0)
            except subprocess.TimeoutExpired:
                server.kill()
                server.communicate()
    print("server smoke    : OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
