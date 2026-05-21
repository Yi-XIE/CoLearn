"""Unified WebSocket endpoint — speaks nanobot's frontend protocol.

Routes messages through CoLearn's LearningOrchestrator (5-stage pipeline:
preflight → retrieval → execute → finalize → writeback). The Execute stage
internally drives nanobot's AgentLoop. This way the state machine, signal
extraction, and board derivation all run for every turn.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from typing import Any, Awaitable, Callable
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from colearn.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

_agent_loop = None
_session_manager = None


def set_agent_loop(loop, session_manager=None):
    """Called at startup to inject the initialized AgentLoop (model_name display only)."""
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
    chat_sessions: dict[str, dict[str, str]] = {}

    async def send_event(event: dict[str, Any]):
        try:
            await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.warning("ws send_event failed: %s", exc)

    try:
        while True:
            raw = await websocket.receive_text()
            frame = json.loads(raw)
            msg_type = frame.get("type")

            if msg_type == "new_chat":
                # session_id is the bare uuid; chat_id is the prefixed form for
                # frontend continuity. Both stable across this WS connection.
                session_id = uuid4().hex[:12]
                chat_id = f"colearn:{session_id}"
                project_id = _ensure_default_project(session_id)
                chat_sessions[chat_id] = {"session_id": session_id, "project_id": project_id}
                _ensure_session(session_id, project_id)
                await send_event({"event": "ready", "chat_id": chat_id, "client_id": client_id})

            elif msg_type == "attach":
                chat_id = frame.get("chat_id", "")
                if chat_id and chat_id not in chat_sessions:
                    session_id = chat_id.replace("colearn:", "")
                    project_id = _ensure_default_project(session_id)
                    chat_sessions[chat_id] = {"session_id": session_id, "project_id": project_id}
                    _ensure_session(session_id, project_id)
                await send_event({"event": "attached", "chat_id": chat_id})

            elif msg_type == "message":
                chat_id = frame.get("chat_id", "")
                content = frame.get("content", "")
                ctx = chat_sessions.get(chat_id)
                if ctx is None:
                    await send_event({"event": "error", "chat_id": chat_id, "detail": "unknown chat_id; send new_chat or attach first"})
                    continue
                await _handle_message(chat_id, ctx, content, send_event)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws error: %s", exc)


def _ensure_default_project(session_id: str) -> str:
    """Ensure a default learning project exists for this session."""
    from colearn.api.dependencies import project_service
    project_id = "default"
    if project_service.get_project(project_id) is None:
        project_service.create_project(project_id, "Default Learning Project")
    return project_id


def _ensure_session(session_id: str, project_id: str) -> None:
    """Ensure a LearningSession exists in the SessionStore for this id."""
    from colearn.api.dependencies import session_store
    if session_store.get_session(session_id) is None:
        session_store.create_session(
            session_id=session_id,
            project_id=project_id,
            title=f"WS chat {session_id[:8]}",
        )


async def _handle_message(
    chat_id: str,
    ctx: dict[str, str],
    content: str,
    send_event: Callable[[dict[str, Any]], Awaitable[None]],
):
    """Route message through LearningOrchestrator's 5-stage pipeline."""
    from colearn.api.dependencies import orchestrator

    if _agent_loop is None:
        await send_event({"event": "error", "chat_id": chat_id, "detail": "agent not initialized"})
        return

    session_id = ctx["session_id"]
    project_id = ctx["project_id"]
    start = time.time()

    await send_event({
        "event": "goal_status",
        "chat_id": chat_id,
        "status": "running",
        "started_at": start,
    })

    # Bridge stream events to async WS frames via a queue.
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def stream_emit(ev: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    async def pump_events(stop_event: asyncio.Event) -> None:
        """Translate executor's stream events into front-end WS protocol."""
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                if stop_event.is_set() and queue.empty():
                    return
                continue
            t = str(ev.get("type") or "")
            if t == "content_delta":
                await send_event({"event": "delta", "chat_id": chat_id, "text": ev.get("content", "")})
            elif t == "stream_end":
                await send_event({"event": "stream_end", "chat_id": chat_id})
            elif t == "reasoning_delta":
                await send_event({"event": "reasoning_delta", "chat_id": chat_id, "text": ev.get("content", "")})
            elif t == "reasoning_end":
                await send_event({"event": "reasoning_end", "chat_id": chat_id})
            elif t == "tool_call":
                meta = ev.get("metadata", {}) or {}
                await send_event({
                    "event": "message",
                    "chat_id": chat_id,
                    "text": "",
                    "kind": "tool_hint",
                    "tool_events": [{"tool_name": meta.get("tool_name", ""), "args": meta.get("args", {})}],
                })

    stop = asyncio.Event()
    pump_task = asyncio.create_task(pump_events(stop))

    try:
        result = await orchestrator.run_turn_async(
            session_id=session_id,
            user_message=content,
            project_id=project_id,
            stream_emit=stream_emit,
        )
        # Drain any remaining queued events before sending final message.
        stop.set()
        await pump_task

        final_text = getattr(result, "final_text", "") or ""
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
        logger.exception("orchestrator error for %s", chat_id)
        stop.set()
        try:
            await pump_task
        except Exception as pump_exc:
            logger.error("pump_task failed during error recovery: %s", pump_exc)
        await send_event({"event": "error", "chat_id": chat_id, "detail": str(exc)})
    finally:
        await send_event({"event": "goal_status", "chat_id": chat_id, "status": "idle"})
