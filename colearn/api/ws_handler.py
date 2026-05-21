"""Unified WebSocket endpoints for the CoLearn web UI."""

from __future__ import annotations

import json
import secrets
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import colearn.api.dependencies as _deps
from colearn.api.ws import (
    ActiveTurn,
    EventSender,
    broadcast_turn_frame,
    colearn_frame,
    execute_turn,
    get_active_turn,
    get_session_turn,
    message_event,
    remember_active_turn,
    send_protocol_error,
    subscribe_turn_stream,
    unsubscribe_connection,
)
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


def _current_model_name() -> str:
    catalog = _deps.settings_service.catalog()
    llm = dict((catalog.get("services") or {}).get("llm") or {})
    active_profile_id = str(llm.get("active_profile_id") or "")
    active_model_id = str(llm.get("active_model_id") or "")
    for profile in list(llm.get("profiles") or []):
        if active_profile_id and str(profile.get("id") or "") != active_profile_id:
            continue
        for model in list(profile.get("models") or []):
            if active_model_id and str(model.get("id") or "") != active_model_id:
                continue
            return str(model.get("model") or model.get("name") or "")
    return getattr(_agent_loop, "model", "") or ""


@router.get("/webui/bootstrap")
async def bootstrap():
    """Issue a short-lived token (no auth for localhost dev)."""
    token = f"nbwt_{secrets.token_urlsafe(16)}"
    return {
        "token": token,
        "ws_path": "/api/v1/ws",
        "expires_in": 3600,
        "model_name": _current_model_name(),
    }


def _normalize_attachments(frame: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in list(frame.get("attachments") or frame.get("media") or []):
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "name": str(item.get("name") or ""),
                "content_type": str(item.get("content_type") or item.get("kind") or "image"),
                "data": str(item.get("data") or item.get("data_url") or ""),
                "size": int(item.get("size") or 0),
            }
        )
    return normalized


def _project_id_from_frame(frame: dict[str, Any]) -> str:
    return str(frame.get("project_id") or "default-project")


def _project_title_from_frame(frame: dict[str, Any]) -> str:
    return str(frame.get("project_title") or _project_id_from_frame(frame) or "CoLearn")


def _skills_from_frame(frame: dict[str, Any]) -> list[str]:
    skills: list[str] = []
    for item in list(frame.get("skills") or []):
        value = str(item or "").strip()
        if value:
            skills.append(value)
    return skills


async def _handle_start_turn(
    *,
    connection_id: str,
    frame: dict[str, Any],
    send_event: EventSender,
) -> None:
    session_id = str(frame.get("session_id") or frame.get("chat_id") or "").strip()
    if not session_id:
        await send_protocol_error(send_event, detail="missing session_id")
        return

    existing = get_session_turn(session_id)
    if existing is not None and not existing.done:
        await send_protocol_error(
            send_event,
            detail="turn already running for session",
            session_id=session_id,
            turn_id=existing.turn_id,
        )
        return

    turn = ActiveTurn(turn_id=str(uuid4()), session_id=session_id, started_at=time.time())
    turn.add_subscriber(connection_id, send_event)
    remember_active_turn(turn)

    await broadcast_turn_frame(
        turn,
        colearn_frame(
            frame_type="session",
            session_id=session_id,
            turn_id=turn.turn_id,
        ),
    )

    await execute_turn(
        turn=turn,
        user_message=str(frame.get("content") or ""),
        project_id=_project_id_from_frame(frame),
        project_title=_project_title_from_frame(frame),
        language=str(frame.get("language") or "zh"),
        attachments=_normalize_attachments(frame),
        requested_skills=_skills_from_frame(frame),
    )


async def _handle_cancel_turn(
    *,
    frame: dict[str, Any],
    send_event: EventSender,
) -> None:
    turn_id = str(frame.get("turn_id") or "").strip()
    if not turn_id:
        await send_protocol_error(send_event, detail="missing turn_id")
        return
    turn = get_active_turn(turn_id)
    if turn is None:
        await send_protocol_error(send_event, detail="turn not found")
        return
    turn.cancel_requested = True
    orchestrator = getattr(_deps, "orchestrator", None)
    executor = getattr(orchestrator, "executor", None)
    if executor is not None and hasattr(executor, "cancel_session"):
        executor.cancel_session(turn.session_id)


async def _handle_subscribe_turn(
    *,
    connection_id: str,
    frame: dict[str, Any],
    send_event: EventSender,
) -> None:
    turn_id = str(frame.get("turn_id") or "").strip()
    if not turn_id:
        await send_protocol_error(send_event, detail="missing turn_id")
        return

    after_seq = int(frame.get("after_seq") or 0)
    turn = get_active_turn(turn_id)
    if turn is None:
        await send_protocol_error(send_event, detail="turn not found")
        return

    await subscribe_turn_stream(
        turn=turn,
        connection_id=connection_id,
        send_event=send_event,
        after_seq=after_seq,
    )


async def _handle_attach(
    *,
    connection_id: str,
    frame: dict[str, Any],
    send_event: EventSender,
) -> None:
    session_id = str(frame.get("chat_id") or frame.get("session_id") or "").strip()
    if not session_id:
        await send_protocol_error(send_event, detail="missing chat_id")
        return

    await send_event({"event": "attached", "chat_id": session_id})

    turn = get_session_turn(session_id)
    if turn is None:
        return

    await subscribe_turn_stream(
        turn=turn,
        connection_id=connection_id,
        send_event=send_event,
        after_seq=0,
    )


async def _dispatch_frame(
    *,
    connection_id: str,
    frame: dict[str, Any],
    send_event: EventSender,
) -> None:
    msg_type = str(frame.get("type") or "").strip()

    if msg_type == "new_chat":
        session_id = str(uuid4())
        await send_event(
            {
                "event": "ready",
                "chat_id": session_id,
                "client_id": str(uuid4())[:8],
            }
        )
        await send_event({"event": "attached", "chat_id": session_id})
        return

    if msg_type == "attach":
        await _handle_attach(connection_id=connection_id, frame=frame, send_event=send_event)
        return

    if msg_type in {"message", "start_turn"}:
        normalized = frame
        if msg_type == "message":
            normalized = {
                "type": "start_turn",
                "session_id": str(frame.get("chat_id") or frame.get("session_id") or ""),
                "project_id": _project_id_from_frame(frame),
                "project_title": _project_title_from_frame(frame),
                "content": str(frame.get("content") or ""),
                "attachments": list(frame.get("media") or []),
                "language": "zh",
                "skills": list(frame.get("skills") or []),
            }
        await _handle_start_turn(connection_id=connection_id, frame=normalized, send_event=send_event)
        return

    if msg_type == "cancel_turn":
        await _handle_cancel_turn(frame=frame, send_event=send_event)
        return

    if msg_type in {"subscribe_turn", "resume_from"}:
        await _handle_subscribe_turn(connection_id=connection_id, frame=frame, send_event=send_event)
        return

    if msg_type == "ping":
        await send_event({"type": "pong", "timestamp": time.time()})
        return

    await send_protocol_error(send_event, detail=f"unsupported frame type: {msg_type or '<empty>'}")


async def _serve_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    connection_id = str(uuid4())

    async def send_event(event: dict[str, Any]) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    try:
        while True:
            raw = await websocket.receive_text()
            frame = json.loads(raw)
            if not isinstance(frame, dict):
                await send_event(message_event("invalid frame"))
                continue
            await _dispatch_frame(
                connection_id=connection_id,
                frame=frame,
                send_event=send_event,
            )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws error: %s", exc)
    finally:
        unsubscribe_connection(connection_id)


@router.websocket("/")
async def unified_ws_legacy(websocket: WebSocket):
    await _serve_ws(websocket)


@router.websocket("/api/v1/ws")
async def unified_ws_api(websocket: WebSocket):
    await _serve_ws(websocket)
