"""WebSocket routes."""

from __future__ import annotations

import anyio
import json
from queue import Empty, Queue
import time
from typing import Any
from uuid import uuid4

from anyio import to_thread
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from colearn.api import dependencies as deps
from colearn.api.schemas import (
    CancelTurnPayload,
    PingPayload,
    RegeneratePayload,
    StartTurnPayload,
    SubscribeTurnPayload,
)
from colearn.api.session_api import touch_session, serialize_session_detail

router = APIRouter()


def _ws_event(
    *,
    type: str,
    source: str = "server",
    stage: str = "turn",
    content: str = "",
    metadata: dict[str, Any] | None = None,
    session_id: str = "",
    turn_id: str = "",
    seq: int = 0,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload.setdefault("phase", type)
    payload.setdefault("warnings", [])
    payload.setdefault("tool_events", [])
    return {
        "type": type,
        "source": source,
        "stage": stage,
        "content": content,
        "metadata": payload,
        "session_id": session_id,
        "turn_id": turn_id,
        "seq": seq,
        "timestamp": time.time(),
    }


async def _send_ws_event(websocket: WebSocket, event: dict[str, Any]) -> None:
    turn_id = str(event.get("turn_id") or "")
    if turn_id:
        deps.turn_cache.append(turn_id, event)
    await websocket.send_json(event)


async def handle_ping(websocket: WebSocket) -> None:
    await websocket.send_json(
        {
            "type": "progress",
            "source": "server",
            "stage": "",
            "content": "",
            "metadata": {"pong": True},
            "timestamp": 0,
        }
    )


def _coerce_subscribe_turn_payload(payload: SubscribeTurnPayload | dict[str, Any]) -> SubscribeTurnPayload:
    if isinstance(payload, SubscribeTurnPayload):
        return payload
    return SubscribeTurnPayload.model_validate(payload)


def _coerce_cancel_turn_payload(payload: CancelTurnPayload | dict[str, Any]) -> CancelTurnPayload:
    if isinstance(payload, CancelTurnPayload):
        return payload
    return CancelTurnPayload.model_validate(payload)


def _coerce_ping_payload(payload: PingPayload | dict[str, Any] | None) -> PingPayload:
    if isinstance(payload, PingPayload):
        return payload
    return PingPayload.model_validate(payload or {"type": "ping"})


async def handle_subscribe_turn(websocket: WebSocket, payload: SubscribeTurnPayload | dict[str, Any]) -> None:
    resolved = _coerce_subscribe_turn_payload(payload)
    turn_id = str(resolved.turn_id or "").strip()
    after_seq = int(resolved.after_seq or 0)
    events = deps.turn_cache.get_events(turn_id)
    if not events:
        record = deps.turn_cache.get_index(turn_id) or {}
        await websocket.send_json(
            _ws_event(
                type="turn_state",
                content="",
                metadata={"phase": "subscribe", "status": "missing", "warnings": ["turn_not_found"]},
                session_id=str(record.get("session_id") or ""),
                turn_id=turn_id,
            )
        )
        return
    for event in events:
        if int(event.get("seq") or 0) > after_seq:
            await websocket.send_json(event)


async def handle_cancel_turn(websocket: WebSocket, payload: CancelTurnPayload | dict[str, Any]) -> None:
    resolved = _coerce_cancel_turn_payload(payload)
    turn_id = str(resolved.turn_id or "").strip()
    record = deps.turn_cache.get_index(turn_id) or {}
    session_id = str(record.get("session_id") or "")
    if session_id:
        session = deps.session_store.get_session(session_id)
        if session is not None:
            session.status = "cancelled"
            session.active_turn_id = None
            session.active_turns = []
            touch_session(session)
            deps.session_store.save_session(session)
    await _send_ws_event(
        websocket,
        _ws_event(
            type="done",
            content="",
            metadata={"phase": "cancelled", "status": "cancelled"},
            session_id=session_id,
            turn_id=turn_id,
            seq=9999,
        ),
    )


async def _send_regenerate_rejected(websocket: WebSocket, session_id: str) -> None:
    await websocket.send_json(
        _ws_event(
            type="error",
            stage="",
            content="Nothing to regenerate.",
            metadata={"turn_terminal": True, "status": "rejected", "reason": "nothing_to_regenerate"},
            session_id=session_id,
            seq=1,
        )
    )


async def _handle_ping_message(websocket: WebSocket, payload: PingPayload | dict[str, Any] | None) -> None:
    _ = _coerce_ping_payload(payload)
    await handle_ping(websocket)


WS_HANDLERS = {
    "ping": _handle_ping_message,
    "subscribe_turn": handle_subscribe_turn,
    "resume_from": handle_subscribe_turn,
    "cancel_turn": handle_cancel_turn,
}


def _prepare_runtime_stream_events(
    *,
    stream_events: list[dict[str, Any]],
    result: Any | None,
    session_id: str,
    turn_id: str,
    seq: int,
) -> tuple[list[dict[str, Any]], int]:
    prepared: list[dict[str, Any]] = []
    for item in stream_events:
        event = dict(item)
        metadata = dict(event.get("metadata") or {})
        metadata.setdefault("phase", str(event.get("type") or "event"))
        metadata.setdefault("warnings", list(getattr(result, "warnings", []) or []))
        metadata.setdefault("tool_events", list(getattr(result, "tool_events", []) or []))
        event["metadata"] = metadata
        event.setdefault("session_id", session_id)
        event.setdefault("turn_id", turn_id)
        event.setdefault("seq", seq)
        event.setdefault("timestamp", time.time())
        prepared.append(event)
        seq = int(event.get("seq") or seq) + 1
    return prepared, seq


def _runtime_stream_signature(event: dict[str, Any]) -> str:
    metadata = {
        key: value
        for key, value in dict(event.get("metadata") or {}).items()
        if key not in {"warnings", "tool_events"}
    }
    return json.dumps(
        {
            "type": event.get("type"),
            "content": event.get("content"),
            "metadata": metadata,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _append_ws_stream_events(
    *,
    turn_id: str,
    session_id: str,
    result: Any,
    seq: int,
    skip_signatures: set[str] | None = None,
) -> list[dict[str, Any]]:
    skip_signatures = skip_signatures or set()
    stream_events = [
        item
        for item in list(result.stream_events or [])
        if _runtime_stream_signature(dict(item)) not in skip_signatures
    ]
    prepared_stream_events, seq = _prepare_runtime_stream_events(
        stream_events=stream_events,
        result=result,
        session_id=session_id,
        turn_id=turn_id,
        seq=seq,
    )
    for item in prepared_stream_events:
        deps.turn_cache.append(turn_id, item)
    return prepared_stream_events


async def _run_turn_with_live_stream(
    *,
    websocket: WebSocket,
    session_id: str,
    project_id: str,
    content: str,
    language: str,
    attachments: list[dict[str, Any]],
    requested_skills: list[str],
    turn_id: str,
    seq: int,
) -> tuple[Any, int, set[str]]:
    queue: Queue[dict[str, Any]] = Queue()
    result_box: dict[str, Any] = {}
    error_box: dict[str, BaseException] = {}
    emitted_signatures: set[str] = set()
    worker_done = False

    def stream_emit(event: dict[str, Any]) -> None:
        queue.put(dict(event))

    async def run_worker() -> None:
        nonlocal worker_done
        try:
            result_box["result"] = await to_thread.run_sync(
                lambda: deps.orchestrator.run_turn(
                    session_id=session_id,
                    project_id=project_id,
                    user_message=content,
                    language=language,
                    attachments=attachments,
                    requested_skills=requested_skills,
                    stream_emit=stream_emit,
                )
            )
        except BaseException as exc:
            error_box["error"] = exc
        finally:
            worker_done = True

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(run_worker)
        while not worker_done or not queue.empty():
            try:
                raw_event = queue.get_nowait()
            except Empty:
                await anyio.sleep(0.01)
                continue
            signature = _runtime_stream_signature(raw_event)
            prepared, seq = _prepare_runtime_stream_events(
                stream_events=[raw_event],
                result=None,
                session_id=session_id,
                turn_id=turn_id,
                seq=seq,
            )
            if not prepared:
                continue
            emitted_signatures.add(signature)
            event = prepared[0]
            deps.turn_cache.append(turn_id, event)
            await websocket.send_json(event)

    if error_box:
        raise error_box["error"]
    return result_box["result"], seq, emitted_signatures


@router.websocket("/api/v1/ws")
async def unified_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                await websocket.send_json(
                    {
                        "type": "error",
                        "source": "server",
                        "stage": "",
                        "content": "WebSocket payload must be a JSON object.",
                        "metadata": {"turn_terminal": True, "status": "failed"},
                        "timestamp": 0,
                    }
                )
                continue
            msg_type = str(payload.get("type") or "")
            try:
                if msg_type == "ping":
                    await _handle_ping_message(websocket, PingPayload.model_validate(payload))
                    continue
                if msg_type in {"subscribe_turn", "resume_from"}:
                    await handle_subscribe_turn(websocket, SubscribeTurnPayload.model_validate(payload))
                    continue
                if msg_type == "cancel_turn":
                    await handle_cancel_turn(websocket, CancelTurnPayload.model_validate(payload))
                    continue
            except Exception as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "source": "server",
                        "stage": "",
                        "content": str(exc),
                        "metadata": {"turn_terminal": True, "status": "failed"},
                        "timestamp": 0,
                    }
                )
                continue
            if msg_type == "regenerate":
                try:
                    regenerate = RegeneratePayload.model_validate(payload)
                except Exception as exc:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "source": "server",
                            "stage": "",
                            "content": str(exc),
                            "metadata": {"turn_terminal": True, "status": "failed"},
                            "timestamp": 0,
                        }
                    )
                    continue
                session_id = str(regenerate.session_id or "").strip()
                session = deps.session_store.get_session(session_id)
                if session is None or not session.messages:
                    await _send_regenerate_rejected(websocket, session_id)
                    continue
                last_user = next(
                    (item for item in reversed(session.messages) if item.get("role") == "user"),
                    None,
                )
                if last_user is None:
                    await _send_regenerate_rejected(websocket, session_id)
                    continue
                payload = {
                    "type": "start_turn",
                    "content": str(last_user.get("content") or ""),
                    "session_id": session_id,
                    "project_id": session.project_id,
                    "project_title": session.title,
                    "language": "zh",
                }
                msg_type = "start_turn"
            if msg_type not in {"message", "start_turn"}:
                await websocket.send_json(
                    {
                        "type": "error",
                        "source": "server",
                        "stage": "",
                        "content": f"Unsupported message type: {msg_type}",
                        "metadata": {"turn_terminal": True, "status": "failed"},
                        "timestamp": 0,
                    }
                )
                continue
            try:
                message = StartTurnPayload.model_validate(payload)
            except Exception as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "source": "server",
                        "stage": "",
                        "content": str(exc),
                        "metadata": {"turn_terminal": True, "status": "failed"},
                        "timestamp": 0,
                    }
                )
                continue
            session_id = message.session_id or str(uuid4())
            project_id = message.project_id or "default-project"
            project_title = message.project_title or project_id
            turn_id = str(uuid4())
            if deps.session_store.get_session(session_id) is None:
                session = deps.session_store.create_session(
                    session_id=session_id,
                    project_id=project_id,
                    title=project_title,
                )
                touch_session(session)
                deps.session_store.save_session(session)
            session = deps.session_store.get_session(session_id)
            if session is None:
                raise HTTPException(status_code=500, detail="Failed to initialize session")
            session.status = "running"
            session.active_turn_id = turn_id
            session.active_turns = [
                {
                    "id": turn_id,
                    "turn_id": turn_id,
                    "session_id": session_id,
                    "status": "running",
                    "error": "",
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                    "finished_at": None,
                    "last_seq": 0,
                }
            ]
            touch_session(session)
            deps.session_store.save_session(session)
            deps.turn_cache.start_turn(turn_id, session_id=session_id, project_id=project_id)
            seq = 1
            session_event = {
                "type": "session",
                "source": "server",
                "stage": "session",
                "content": "",
                "metadata": {
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "phase": "session",
                    "warnings": [],
                    "tool_events": [],
                },
                "session_id": session_id,
                "turn_id": turn_id,
                "seq": seq,
                "timestamp": time.time(),
            }
            # PLACEHOLDER_WS_CONTINUE
            deps.turn_cache.append(turn_id, session_event)
            await websocket.send_json(session_event)
            seq += 1
            stage_event = {
                "type": "stage_start",
                "source": "server",
                "stage": "turn",
                "content": "",
                "metadata": {"phase": "started", "warnings": [], "tool_events": []},
                "session_id": session_id,
                "turn_id": turn_id,
                "seq": seq,
                "timestamp": time.time(),
            }
            deps.turn_cache.append(turn_id, stage_event)
            await websocket.send_json(stage_event)
            seq += 1
            try:
                result, seq, emitted_stream_signatures = await _run_turn_with_live_stream(
                    websocket=websocket,
                    session_id=session_id,
                    project_id=project_id,
                    content=message.content,
                    language=message.language,
                    attachments=message.attachments,
                    requested_skills=message.skills,
                    turn_id=turn_id,
                    seq=seq,
                )
            except Exception as exc:
                session = deps.session_store.get_session(session_id)
                if session is not None:
                    session.status = "failed"
                    session.active_turn_id = None
                    session.active_turns = []
                    touch_session(session)
                    deps.session_store.save_session(session)
                error_event = {
                    "type": "error",
                    "source": "server",
                    "stage": "turn",
                    "content": str(exc),
                    "metadata": {
                        "phase": "error",
                        "status": "failed",
                        "turn_terminal": True,
                        "warnings": [str(exc)],
                        "tool_events": [],
                    },
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "seq": seq,
                    "timestamp": time.time(),
                }
                deps.turn_cache.append(turn_id, error_event)
                await websocket.send_json(error_event)
                continue
            prepared_stream_events = _append_ws_stream_events(
                turn_id=turn_id,
                session_id=session_id,
                result=result,
                seq=seq,
                skip_signatures=emitted_stream_signatures,
            )
            if prepared_stream_events:
                seq = int(prepared_stream_events[-1].get("seq") or seq) + 1
            for item in prepared_stream_events:
                await websocket.send_json(item)
            learning_support = dict((result.raw_learning_result or {}).get("runtime_v2", {}).get("retrieval", {}) or {})
            content_event = {
                "type": "content",
                "source": "assistant",
                "stage": "turn",
                "content": result.final_text,
                "metadata": {
                    "phase": "content",
                    "turn_mode": result.turn_mode_after,
                    "board_patch": result.board_patch,
                    "learning_support": learning_support,
                    "warnings": list(result.warnings),
                    "tool_events": list(result.tool_events),
                    "call_id": f"{turn_id}-final",
                    "call_kind": "llm_final_response",
                    "trace_role": "response",
                },
                "session_id": session_id,
                "turn_id": turn_id,
                "seq": seq,
                "timestamp": time.time(),
            }
            seq += 1
            deps.turn_cache.append(turn_id, content_event)
            await websocket.send_json(content_event)
            done_event = {
                "type": "done",
                "source": "server",
                "stage": "turn",
                "content": "",
                "metadata": {
                    "phase": "done",
                    "status": "completed",
                    "warnings": list(result.warnings),
                    "tool_events": list(result.tool_events),
                },
                "session_id": session_id,
                "turn_id": turn_id,
                "seq": seq,
                "timestamp": time.time(),
            }
            deps.turn_cache.append(turn_id, done_event)
            deps.turn_cache.finish_turn(turn_id)
            session = deps.session_store.get_session(session_id)
            if session is not None:
                session.status = "completed"
                session.active_turn_id = None
                session.active_turns = []
                touch_session(session)
                deps.session_store.save_session(session)
            await websocket.send_json(done_event)
    except WebSocketDisconnect:
        return