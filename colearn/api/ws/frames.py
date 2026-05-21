from __future__ import annotations

import time
from typing import Any

from .registry import ActiveTurn


def metadata(frame: dict[str, Any]) -> dict[str, Any]:
    return dict(frame.get("metadata") or {})


def colearn_frame(
    *,
    frame_type: str,
    session_id: str,
    turn_id: str,
    content: str = "",
    timestamp: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": frame_type,
        "session_id": session_id,
        "turn_id": turn_id,
        "content": content,
        "timestamp": timestamp if timestamp is not None else time.time(),
        "metadata": metadata or {},
    }


def stream_event_to_frame(
    session_id: str,
    turn_id: str,
    stream_event: dict[str, Any],
) -> dict[str, Any]:
    timestamp = stream_event.get("timestamp")
    resolved_timestamp = float(timestamp) if isinstance(timestamp, (int, float)) else None
    return colearn_frame(
        frame_type=str(stream_event.get("type") or "turn_state"),
        session_id=session_id,
        turn_id=turn_id,
        content=str(stream_event.get("content") or ""),
        timestamp=resolved_timestamp,
        metadata=metadata(stream_event),
    )


def final_turn_state_frame(
    *,
    turn: ActiveTurn,
    status: str,
    latency_ms: int,
    final_text: str = "",
    tool_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return colearn_frame(
        frame_type="turn_state",
        session_id=turn.session_id,
        turn_id=turn.turn_id,
        content=final_text,
        metadata={
            "status": status,
            "phase": "finalize",
            "latency_ms": latency_ms,
            "tool_events": list(tool_events or []),
        },
    )


def done_frame(
    *,
    turn: ActiveTurn,
    status: str,
    latency_ms: int,
    tool_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return colearn_frame(
        frame_type="done",
        session_id=turn.session_id,
        turn_id=turn.turn_id,
        metadata={
            "status": status,
            "phase": "done",
            "latency_ms": latency_ms,
            "tool_events": list(tool_events or []),
        },
    )


def error_frame(turn: ActiveTurn, detail: str) -> dict[str, Any]:
    return colearn_frame(
        frame_type="error",
        session_id=turn.session_id,
        turn_id=turn.turn_id,
        content=detail,
        metadata={"status": "failed", "phase": "error"},
    )


def message_event(detail: str, *, chat_id: str | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {"event": "error", "detail": detail}
    if chat_id:
        event["chat_id"] = chat_id
    return event
