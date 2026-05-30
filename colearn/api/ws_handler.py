"""Unified WebSocket endpoints for the local CoLearn WebUI."""

from __future__ import annotations

import json
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
    normalize_attachments,
    normalize_turn_frame,
    mode_from_frame,
    project_id_from_frame,
    project_title_from_frame,
    ready_event,
    remember_active_turn,
    send_protocol_error,
    skills_from_frame,
    subscribe_turn_stream,
    unsubscribe_connection,
)
from colearn.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


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
    return getattr(getattr(_deps, "agent_loop", None), "model", "") or ""


@router.get("/webui/bootstrap")
async def bootstrap():
    """Return local WebUI connection details for the unified CoLearn server."""
    return {
        "token": "local-dev",
        "ws_path": "/api/v1/ws",
        "expires_in": 3600,
        "model_name": _current_model_name(),
    }


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
        project_id=project_id_from_frame(frame),
        project_title=project_title_from_frame(frame),
        language=str(frame.get("language") or "zh"),
        attachments=normalize_attachments(frame),
        requested_skills=skills_from_frame(frame),
        requested_mode=mode_from_frame(frame),
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
    complete_goal = getattr(executor, "complete_sustained_goal", None)
    if callable(complete_goal):
        complete_goal(session_id=turn.session_id, recap="Learning turn cancelled.")


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
        await send_protocol_error(send_event, detail="missing session_id")
        return

    await send_event({"event": "attached", "chat_id": session_id, "session_id": session_id})

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
        event = ready_event()
        await send_event(event)
        session_id = str(event["session_id"])
        await send_event({"event": "attached", "chat_id": session_id, "session_id": session_id})
        return

    if msg_type == "attach":
        await _handle_attach(connection_id=connection_id, frame=frame, send_event=send_event)
        return

    if msg_type in {"message", "start_turn"}:
        content = str(frame.get("content") or "").strip()
        if content == "/stop":
            await _handle_cancel_turn(frame=frame, send_event=send_event)
            return
        normalized = normalize_turn_frame(frame)
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
        except WebSocketDisconnect:
            pass
        except (RuntimeError, ConnectionError) as exc:
            logger.warning("ws send_event failed: %s", exc)

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
    except (json.JSONDecodeError, RuntimeError, ConnectionError) as exc:
        logger.warning("ws error: %s", exc)
    finally:
        unsubscribe_connection(connection_id)


@router.websocket("/")
async def unified_ws_legacy(websocket: WebSocket):
    await _serve_ws(websocket)


@router.websocket("/api/v1/ws")
async def unified_ws_api(websocket: WebSocket):
    await _serve_ws(websocket)
