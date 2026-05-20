"""Bounded replay cache for completed WebSocket turn event streams."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from colearn.config.defaults import Defaults


class RecentTurnReplayCache:
    """LRU buffer for completed WebSocket turn events, separate from session storage.

    Lives in-process so clients reconnecting mid-turn can replay events via
    `subscribe_turn`. Independent of `session_store` because turns finish faster
    than sessions persist; bounded to `max_turns` to prevent unbounded growth.
    """

    def __init__(self, max_turns: int = Defaults.TURN_CACHE_MAX_TURNS) -> None:
        self._max_turns = max_turns
        self._store: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._index: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def start_turn(self, turn_id: str, *, session_id: str, project_id: str) -> None:
        self._store.setdefault(turn_id, [])
        self._index[turn_id] = {"session_id": session_id, "project_id": project_id}
        self._evict()

    def append(self, turn_id: str, event: dict[str, Any]) -> None:
        self._store.setdefault(turn_id, []).append(event)

    def finish_turn(self, turn_id: str) -> None:
        if turn_id in self._store:
            self._store.move_to_end(turn_id)
        self._evict()

    def get_events(self, turn_id: str) -> list[dict[str, Any]]:
        return list(self._store.get(turn_id) or [])

    def get_index(self, turn_id: str) -> dict[str, Any] | None:
        return self._index.get(turn_id)

    def remove(self, turn_id: str) -> None:
        self._store.pop(turn_id, None)
        self._index.pop(turn_id, None)

    def clear(self) -> None:
        self._store.clear()
        self._index.clear()

    def _evict(self) -> None:
        while len(self._store) > self._max_turns:
            oldest_key, _ = self._store.popitem(last=False)
            self._index.pop(oldest_key, None)
