"""Unified WebSocket endpoint — speaks nanobot's frontend protocol.

Replaces the standalone nanobot gateway. CoLearn serves everything:
REST routes + this WS endpoint. nanobot runs as a library (AgentLoop).
"""

from __future__ import annotations

import asyncio
import time
import secrets
from typing import Any, Callable, Awaitable
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from colearn.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

_agent_loop = None
_session_manager = None


def set_agent_loop(loop, session_manager=None):
    """Called at startup to inject the initialized AgentLoop."""
    global _agent_loop, _session_manager
    _agent_loop = loop
    _session_manager = session_manager


@router.get("/webui/bootstrap")
async def bootstrap():
    """Issue a short-lived token (no auth for localhost dev)."""
    token = f"nbwt_{secrets.token_urlsafe(16)}"
    return {
        "token": token,
        "ws_path": "/",
        "expires_in": 3600,
        "model_name": getattr(_agent_loop, "model", None),
    }


@router.websocket("/")
async def unified_ws(websocket: WebSocket):
    await websocket.accept()
    client_id = str(uuid4())[:8]
    chat_sessions: dict[str, str] = {}

    async def send_event(event: dict[str, Any]):
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    try:
        while True:
            raw = await websocket.receive_text()
            import json
            frame = json.loads(raw)
            msg_type = frame.get("type")

            if msg_type == "new_chat":
                chat_id = f"colearn:{uuid4().hex[:12]}"
                chat_sessions[chat_id] = chat_id
                await send_event({"event": "ready", "chat_id": chat_id, "client_id": client_id})

            elif msg_type == "attach":
                chat_id = frame.get("chat_id", "")
                chat_sessions[chat_id] = chat_id
                await send_event({"event": "attached", "chat_id": chat_id})

            elif msg_type == "message":
                chat_id = frame.get("chat_id", "")
                content = frame.get("content", "")
                await _handle_message(websocket, chat_id, content, send_event)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws error: %s", exc)


async def _handle_message(
    websocket: WebSocket,
    chat_id: str,
    content: str,
    send_event: Callable[[dict[str, Any]], Awaitable[None]],
):
    """Run agent loop and stream events back."""
    if _agent_loop is None:
        await send_event({"event": "error", "chat_id": chat_id, "detail": "agent not initialized"})
        return

    await send_event({"event": "goal_status", "chat_id": chat_id, "status": "running", "started_at": time.time()})

    session_key = chat_id
    start = time.time()

    async def on_stream(text: str):
        await send_event({"event": "delta", "chat_id": chat_id, "text": text})

    async def on_stream_end(**kwargs):
        await send_event({"event": "stream_end", "chat_id": chat_id})

    async def on_progress(content: str = "", **kwargs):
        if content:
            await send_event({
                "event": "message",
                "chat_id": chat_id,
                "text": content,
                "kind": "progress",
            })

    try:
        resp = await _agent_loop.process_direct(
            content,
            session_key=session_key,
            channel="websocket",
            chat_id=chat_id,
            on_progress=on_progress,
            on_stream=on_stream,
            on_stream_end=on_stream_end,
        )
        final_text = resp.content if resp else ""
        latency_ms = int((time.time() - start) * 1000)

        if final_text:
            await send_event({
                "event": "message",
                "chat_id": chat_id,
                "text": final_text,
            })

        await send_event({
            "event": "turn_end",
            "chat_id": chat_id,
            "latency_ms": latency_ms,
        })
    except Exception as exc:
        logger.exception("agent loop error for %s", chat_id)
        await send_event({"event": "error", "chat_id": chat_id, "detail": str(exc)})
    finally:
        await send_event({"event": "goal_status", "chat_id": chat_id, "status": "idle"})
