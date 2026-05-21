from __future__ import annotations

import asyncio
import time
from threading import Thread
from typing import Any, Callable

import colearn.api.dependencies as _deps
from colearn.logging_config import get_logger

from .frames import (
    colearn_frame,
    done_frame,
    error_frame,
    final_turn_state_frame,
    message_event,
    stream_event_to_frame,
)
from .registry import ActiveTurn, EventSender, clear_active_turn

logger = get_logger(__name__)


class TurnCancelledBeforeStart(RuntimeError):
    """Raised when a turn is cancelled before the worker begins running."""


def _prepare_session_for_turn(
    *,
    turn: ActiveTurn,
    project_id: str,
    project_title: str,
) -> None:
    session = _deps.session_store.get_session(turn.session_id)
    if session is None:
        session = _deps.session_store.create_session(
            session_id=turn.session_id,
            project_id=project_id or "default-project",
            title=project_title or turn.session_id,
        )
    if project_id:
        session.project_id = project_id
    if not session.title:
        session.title = project_title or session.project_id or session.session_id
    session.active_turn_id = turn.turn_id
    session.active_turns = [{"turn_id": turn.turn_id, "status": "running", "started_at": int(turn.started_at)}]
    session.status = "running"
    _deps.session_store.save_session(session)


def _release_session_turn(session_id: str, turn_id: str) -> None:
    session = _deps.session_store.get_session(session_id)
    if session is None:
        return
    if session.active_turn_id == turn_id:
        session.active_turn_id = None
        session.active_turns = []
    if session.status == "running":
        session.status = "idle"
    _deps.session_store.save_session(session)


async def _fanout_to_subscribers(turn: ActiveTurn, payload: dict[str, Any]) -> None:
    subscribers = turn.snapshot_subscribers()
    if not subscribers:
        return
    await asyncio.gather(*(subscriber(dict(payload)) for subscriber in subscribers), return_exceptions=True)


async def emit_session_updated(turn: ActiveTurn) -> None:
    await _fanout_to_subscribers(turn, {"event": "session_updated", "chat_id": turn.session_id})


async def broadcast_turn_frame(turn: ActiveTurn, payload: dict[str, Any]) -> dict[str, Any]:
    stored = turn.append_replay(payload)
    await _fanout_to_subscribers(turn, stored)
    return stored


async def broadcast_stream_event(turn: ActiveTurn, payload: dict[str, Any]) -> dict[str, Any]:
    return await broadcast_turn_frame(turn, stream_event_to_frame(turn.session_id, turn.turn_id, payload))


def _run_orchestrator_turn(
    *,
    turn: ActiveTurn,
    user_message: str,
    project_id: str,
    project_title: str,
    language: str,
    attachments: list[dict[str, Any]],
    requested_skills: list[str],
    emit_stream_event: Callable[[dict[str, Any]], None],
    cancel_check: Callable[[], bool],
) -> Any:
    orchestrator = getattr(_deps, "orchestrator", None)
    if orchestrator is None:
        raise RuntimeError("orchestrator not initialized")
    _prepare_session_for_turn(turn=turn, project_id=project_id, project_title=project_title)
    return orchestrator.run_turn(
        session_id=turn.session_id,
        user_message=user_message,
        project_id=project_id,
        language=language,
        attachments=attachments,
        requested_skills=requested_skills,
        stream_emit=emit_stream_event,
        cancel_check=cancel_check,
    )


async def _finalize_turn(turn: ActiveTurn) -> None:
    clear_active_turn(turn.turn_id, turn.session_id)
    _release_session_turn(turn.session_id, turn.turn_id)


async def execute_turn(
    *,
    turn: ActiveTurn,
    user_message: str,
    project_id: str,
    project_title: str,
    language: str,
    attachments: list[dict[str, Any]],
    requested_skills: list[str],
) -> None:
    loop = asyncio.get_running_loop()
    wake_signal = asyncio.Event()

    def emit_stream_event(payload: dict[str, Any]) -> None:
        turn.enqueue_stream_event(payload)
        loop.call_soon_threadsafe(wake_signal.set)

    def cancel_check() -> bool:
        return turn.cancel_requested

    def worker() -> None:
        try:
            if turn.cancel_requested:
                raise TurnCancelledBeforeStart("turn cancelled before execution")
            turn.result = _run_orchestrator_turn(
                turn=turn,
                user_message=user_message,
                project_id=project_id,
                project_title=project_title,
                language=language,
                attachments=attachments,
                requested_skills=requested_skills,
                emit_stream_event=emit_stream_event,
                cancel_check=cancel_check,
            )
        except BaseException as exc:
            turn.error = exc
        finally:
            turn.done = True
            turn.finished_at = time.time()
            loop.call_soon_threadsafe(wake_signal.set)

    thread = Thread(target=worker, daemon=True, name=f"colearn-turn-{turn.turn_id[:8]}")
    thread.start()

    while True:
        for item in turn.drain_stream_events():
            await broadcast_stream_event(turn, item)
        if turn.done and not thread.is_alive():
            break
        try:
            await asyncio.wait_for(wake_signal.wait(), timeout=0.1)
        except TimeoutError:
            pass
        finally:
            wake_signal.clear()

    thread.join(timeout=0.2)
    for item in turn.drain_stream_events():
        await broadcast_stream_event(turn, item)
    latency_ms = int(((turn.finished_at or time.time()) - turn.started_at) * 1000)

    if isinstance(turn.error, TurnCancelledBeforeStart):
        await broadcast_turn_frame(turn, final_turn_state_frame(turn=turn, status="cancelled", latency_ms=latency_ms))
        await broadcast_turn_frame(turn, done_frame(turn=turn, status="cancelled", latency_ms=latency_ms))
        await emit_session_updated(turn)
        await _finalize_turn(turn)
        return

    if turn.error is not None:
        logger.exception("colearn websocket turn failed for %s", turn.session_id, exc_info=turn.error)
        await broadcast_turn_frame(turn, error_frame(turn, str(turn.error)))
        await emit_session_updated(turn)
        await _finalize_turn(turn)
        return

    result = turn.result
    final_text = str(getattr(result, "final_text", "") or "")
    tool_events = list(getattr(result, "tool_events", []) or [])
    if final_text:
        await broadcast_turn_frame(
            turn,
            colearn_frame(
                frame_type="content",
                session_id=turn.session_id,
                turn_id=turn.turn_id,
                content=final_text,
                metadata={
                    "status": "completed",
                    "phase": "final",
                    "latency_ms": latency_ms,
                    "tool_events": tool_events,
                },
            ),
        )
    final_status = "cancelled" if turn.cancel_requested and not final_text else "completed"
    await broadcast_turn_frame(
        turn,
        final_turn_state_frame(
            turn=turn,
            status=final_status,
            latency_ms=latency_ms,
            final_text=final_text,
            tool_events=tool_events,
        ),
    )
    await broadcast_turn_frame(turn, done_frame(turn=turn, status=final_status, latency_ms=latency_ms, tool_events=tool_events))
    await emit_session_updated(turn)
    await _finalize_turn(turn)


async def send_protocol_error(
    send_event: EventSender,
    *,
    detail: str,
    session_id: str = "",
    turn_id: str = "",
) -> None:
    if session_id:
        await send_event(
            colearn_frame(
                frame_type="error",
                session_id=session_id,
                turn_id=turn_id,
                content=detail,
                metadata={"status": "failed", "phase": "error"},
            )
        )
        return
    await send_event(message_event(detail))


async def subscribe_turn_stream(
    *,
    turn: ActiveTurn,
    connection_id: str,
    send_event: EventSender,
    after_seq: int,
) -> None:
    next_seq = max(after_seq, 0)
    while True:
        replay = turn.replay_after(next_seq)
        for item in replay:
            await send_event(dict(item))
        if replay:
            next_seq = int(replay[-1].get("seq") or 0) + 1
        if turn.done:
            return
        if turn.try_add_subscriber(connection_id, send_event, expected_next_seq=next_seq):
            return
