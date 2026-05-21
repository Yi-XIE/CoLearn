"""Helpers for CoLearn websocket turn lifecycle and protocol handling."""

from .frames import (
    colearn_frame,
    done_frame,
    error_frame,
    final_turn_state_frame,
    message_event,
    metadata,
    stream_event_to_frame,
)
from .registry import (
    ActiveTurn,
    EventSender,
    clear_active_turn,
    get_active_turn,
    get_session_turn,
    remember_active_turn,
    unsubscribe_connection,
)
from .service import (
    TurnCancelledBeforeStart,
    broadcast_stream_event,
    broadcast_turn_frame,
    emit_session_updated,
    execute_turn,
    send_protocol_error,
    subscribe_turn_stream,
)

__all__ = [
    "ActiveTurn",
    "EventSender",
    "TurnCancelledBeforeStart",
    "broadcast_stream_event",
    "broadcast_turn_frame",
    "clear_active_turn",
    "colearn_frame",
    "done_frame",
    "emit_session_updated",
    "error_frame",
    "execute_turn",
    "final_turn_state_frame",
    "get_active_turn",
    "get_session_turn",
    "message_event",
    "metadata",
    "remember_active_turn",
    "send_protocol_error",
    "stream_event_to_frame",
    "subscribe_turn_stream",
    "unsubscribe_connection",
]
