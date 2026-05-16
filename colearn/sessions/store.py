"""Minimal in-memory session store for standalone CoLearn."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
    def __init__(self, state_store: JsonStateStore | None = None) -> None:
        self._sessions: dict[str, LearningSession] = {}
        self._state_store = state_store or JsonStateStore()
        self._load()

    def _load(self) -> None:
        raw = self._state_store.read_json("sessions.json", [])
        if not isinstance(raw, list):
            return
        for item in raw:
            if not isinstance(item, dict):
                continue
            session = session_from_record(item)
            if session.session_id:
                self._sessions[session.session_id] = session

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
        session = LearningSession(
            session_id=session_id,
            project_id=project_id,
            title=title,
            turn_mode=turn_mode,
        )
        self._sessions[session_id] = session
        self._dump()
        return session

    def get_session(self, session_id: str) -> LearningSession | None:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[LearningSession]:
        return list(self._sessions.values())

    def save_session(self, session: LearningSession) -> LearningSession:
        self._sessions[session.session_id] = session
        self._dump()
        return session
