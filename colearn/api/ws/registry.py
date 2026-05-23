from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Awaitable, Callable

EventSender = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class ActiveTurn:
    turn_id: str
    session_id: str
    started_at: float
    replay: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    cancel_requested: bool = False
    result: Any = None
    error: BaseException | None = None
    finished_at: float | None = None
    _seq: int = 0
    _pending_stream_events: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _subscribers: dict[str, EventSender] = field(default_factory=dict, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def append_replay(self, frame: dict[str, Any]) -> dict[str, Any]:
        payload = dict(frame)
        with self._lock:
            payload["seq"] = self._seq
            self._seq += 1
            self.replay.append(payload)
        return dict(payload)

    def replay_after(self, after_seq: int) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self.replay if int(item.get("seq") or 0) >= after_seq]

    def enqueue_stream_event(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._pending_stream_events.append(dict(payload))

    def drain_stream_events(self) -> list[dict[str, Any]]:
        with self._lock:
            pending = list(self._pending_stream_events)
            self._pending_stream_events.clear()
        return pending

    def snapshot_subscribers(self) -> list[EventSender]:
        with self._lock:
            return list(self._subscribers.values())

    def try_add_subscriber(
        self,
        connection_id: str,
        send_event: EventSender,
        *,
        expected_next_seq: int,
    ) -> bool:
        with self._lock:
            if self._seq != expected_next_seq:
                return False
            self._subscribers[connection_id] = send_event
        return True

    def add_subscriber(self, connection_id: str, send_event: EventSender) -> None:
        with self._lock:
            self._subscribers[connection_id] = send_event

    def remove_subscriber(self, connection_id: str) -> None:
        with self._lock:
            self._subscribers.pop(connection_id, None)


_active_turns: dict[str, ActiveTurn] = {}
_session_to_turn: dict[str, str] = {}
_active_turns_lock = Lock()


def remember_active_turn(turn: ActiveTurn) -> None:
    with _active_turns_lock:
        _active_turns[turn.turn_id] = turn
        _session_to_turn[turn.session_id] = turn.turn_id


def get_active_turn(turn_id: str) -> ActiveTurn | None:
    with _active_turns_lock:
        return _active_turns.get(turn_id)


def get_session_turn(session_id: str) -> ActiveTurn | None:
    with _active_turns_lock:
        turn_id = _session_to_turn.get(session_id)
        return _active_turns.get(turn_id or "")


def clear_active_turn(turn_id: str, session_id: str) -> None:
    with _active_turns_lock:
        _active_turns.pop(turn_id, None)
        if _session_to_turn.get(session_id) == turn_id:
            _session_to_turn.pop(session_id, None)


def unsubscribe_connection(connection_id: str) -> None:
    with _active_turns_lock:
        turns = list(_active_turns.values())
    for turn in turns:
        turn.remove_subscriber(connection_id)
