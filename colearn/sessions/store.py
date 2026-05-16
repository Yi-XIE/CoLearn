"""Minimal in-memory session store for standalone CoLearn."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from colearn.storage import JsonStateStore


@dataclass
class LearningSession:
    session_id: str
    project_id: str = ""
    title: str = ""
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
            session = LearningSession(
                session_id=str(item.get("session_id") or ""),
                project_id=str(item.get("project_id") or ""),
                title=str(item.get("title") or ""),
                turn_mode=str(item.get("turn_mode") or "EXPLORE"),
                board_facts=dict(item.get("board_facts") or {}),
                board_version=int(item.get("board_version") or 1),
                status=str(item.get("status") or "idle"),
                source_refs=list(item.get("source_refs") or []),
                memory_refs=list(item.get("memory_refs") or []),
                messages=list(item.get("messages") or []),
                continuation_prompt=str(item.get("continuation_prompt") or ""),
                last_turn_result=dict(item.get("last_turn_result") or {}),
                pending_review=dict(item.get("pending_review") or {}),
                active_turn_id=item.get("active_turn_id"),
                active_turns=list(item.get("active_turns") or []),
            )
            if session.session_id:
                self._sessions[session.session_id] = session

    def _dump(self) -> None:
        payload = []
        for session in self._sessions.values():
            payload.append(
                {
                    "session_id": session.session_id,
                    "project_id": session.project_id,
                    "title": session.title,
                    "turn_mode": session.turn_mode,
                    "board_facts": dict(session.board_facts),
                    "board_version": session.board_version,
                    "status": session.status,
                    "source_refs": list(session.source_refs),
                    "memory_refs": list(session.memory_refs),
                    "messages": list(session.messages),
                    "continuation_prompt": session.continuation_prompt,
                    "last_turn_result": dict(session.last_turn_result),
                    "pending_review": dict(session.pending_review),
                    "active_turn_id": session.active_turn_id,
                    "active_turns": list(session.active_turns),
                }
            )
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
