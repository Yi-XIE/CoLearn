"""JSON-backed project/session/memory store glue for CoLearn."""

from __future__ import annotations

from pathlib import Path

from colearn.memory.store import EventMemoryStore
from colearn.projects.service import LearningProjectService
from colearn.sessions.store import SessionStore
from colearn.storage.json_store import JsonStateStore


def build_stateful_project_service(root: Path | None = None) -> LearningProjectService:
    return LearningProjectService(state_store=JsonStateStore(root))


def build_stateful_session_store(root: Path | None = None) -> SessionStore:
    return SessionStore(state_store=JsonStateStore(root))


def build_stateful_memory_store(root: Path | None = None) -> EventMemoryStore:
    return EventMemoryStore(state_store=JsonStateStore(root))
