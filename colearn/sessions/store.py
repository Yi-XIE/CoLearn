"""Minimal in-memory session store for standalone CoLearn."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from colearn.config.defaults import Defaults
from colearn.storage import JsonStateStore
from colearn.storage.records import session_from_record, session_to_record


@dataclass
class LearningSession:
    session_id: str
    project_id: str = ""
    title: str = ""
    created_at: int = 0
    updated_at: int = 0
    turn_mode: str = "EXPLORE"
    board_facts: dict[str, Any] = field(default_factory=dict)
    board_version: int = 1
    status: str = "idle"
    source_refs: list[str] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    continuation_prompt: str = ""
    last_turn_result: dict[str, Any] = field(default_factory=dict)
    pending_review: dict[str, Any] = field(default_factory=dict)
    active_turn_id: str | None = None
    active_turns: list[dict[str, Any]] = field(default_factory=list)


class SessionStore:
    def __init__(
        self,
        state_store: JsonStateStore | None = None,
        *,
        max_idle_seconds: int | None = None,
    ) -> None:
        self._sessions: dict[str, LearningSession] = {}
        self._last_accessed: dict[str, float] = {}
        self._state_store = state_store or JsonStateStore()
        self._max_idle_seconds = max_idle_seconds or Defaults.SESSION_MAX_IDLE_SECONDS
        self._load()

    def _load(self) -> None:
        raw = self._state_store.read_json("sessions.json", [])
        if not isinstance(raw, list):
            return
        now = time.time()
        for item in raw:
            if not isinstance(item, dict):
                continue
            session = session_from_record(item)
            if session.session_id:
                self._sessions[session.session_id] = session
                self._last_accessed[session.session_id] = now

    def _dump(self) -> None:
        payload = [session_to_record(session) for session in self._sessions.values()]
        self._state_store.write_json("sessions.json", payload)

    def create_session(
        self,
        *,
        session_id: str,
        project_id: str = "",
        title: str = "",
        turn_mode: str = "EXPLORE",
    ) -> LearningSession:
        self._evict_idle()
        session = LearningSession(
            session_id=session_id,
            project_id=project_id,
            title=title,
            turn_mode=turn_mode,
        )
        self._sessions[session_id] = session
        self._last_accessed[session_id] = time.time()
        self._dump()
        return session

    def get_session(self, session_id: str) -> LearningSession | None:
        session = self._sessions.get(session_id)
        if session is not None:
            self._last_accessed[session_id] = time.time()
        return session

    def list_sessions(self) -> list[LearningSession]:
        return list(self._sessions.values())

    def save_session(self, session: LearningSession) -> LearningSession:
        self._sessions[session.session_id] = session
        self._last_accessed[session.session_id] = time.time()
        self._dump()
        return session

    def _evict_idle(self) -> int:
        """Remove sessions idle longer than max_idle_seconds from RAM. Returns count evicted."""
        now = time.time()
        threshold = now - self._max_idle_seconds
        to_evict = [
            sid for sid, last in self._last_accessed.items()
            if last < threshold and self._sessions.get(sid) is not None
            and self._sessions[sid].active_turn_id is None
        ]
        for sid in to_evict:
            del self._sessions[sid]
            del self._last_accessed[sid]
        return len(to_evict)
