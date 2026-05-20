"""Minimal event-memory placeholder store for standalone CoLearn."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from colearn.learning.events import MemoryEventKind
from colearn.storage import JsonStateStore
from colearn.storage.records import memory_event_from_record, memory_event_to_record


@dataclass
class MemoryEvent:
    event_id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


class EventMemoryStore:
    def __init__(self, state_store: JsonStateStore | None = None) -> None:
        self._events: list[MemoryEvent] = []
        self._state_store = state_store or JsonStateStore()
        self._load()

    def _load(self) -> None:
        raw = self._state_store.read_json("memory.json", [])
        if not isinstance(raw, list):
            return
        for item in raw:
            if not isinstance(item, dict):
                continue
            event = memory_event_from_record(item)
            if event.event_id:
                self._events.append(event)

    def _dump(self) -> None:
        self._state_store.write_json(
            "memory.json",
            [memory_event_to_record(event) for event in self._events],
        )

    def append(self, event: MemoryEvent) -> None:
        self._events.append(event)
        self._dump()

    def list_events(self) -> list[MemoryEvent]:
        return list(self._events)

    def list_events_for_session(self, session_id: str) -> list[MemoryEvent]:
        return [
            event
            for event in self._events
            if str(event.payload.get("session_id") or "") == session_id
        ]

    def list_events_for_project(self, project_id: str) -> list[MemoryEvent]:
        return [
            event
            for event in self._events
            if str(event.payload.get("project_id") or "") == project_id
        ]

    def search_events(
        self,
        *,
        query: str,
        session_id: str = "",
        project_id: str = "",
        limit: int = 5,
    ) -> list[MemoryEvent]:
        scope = self._events
        if session_id:
            scope = self.list_events_for_session(session_id)
        elif project_id:
            scope = self.list_events_for_project(project_id)

        terms = [item for item in str(query or "").lower().split() if item]
        if not terms:
            return scope[-limit:]

        scored: list[tuple[int, int, MemoryEvent]] = []
        for event in scope:
            haystack = f"{event.kind} {json.dumps(event.payload, ensure_ascii=False)}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score > 0:
                kind_bonus = 1 if event.kind == MemoryEventKind.REVIEW_WRITTEN else 0
                scored.append((score, kind_bonus, event))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

        seen_signatures: set[str] = set()
        deduped: list[MemoryEvent] = []
        for _, _, event in scored:
            signature = str(event.payload.get("summary") or "").strip().lower()
            if signature and signature in seen_signatures:
                continue
            if signature:
                seen_signatures.add(signature)
            deduped.append(event)
            if len(deduped) >= limit:
                break
        return deduped
