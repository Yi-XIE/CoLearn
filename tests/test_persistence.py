from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from colearn.memory.store import EventMemoryStore, MemoryEvent
from colearn.projects.service import LearningProjectService
from colearn.sessions.store import SessionStore
from colearn.storage.json_store import JsonStateStore


def test_json_state_store_roundtrip(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path)
    store.write_json("sample.json", {"ok": True})
    assert store.read_json("sample.json", {}) == {"ok": True}
    assert not (tmp_path / ".sample.json.tmp").exists()


def test_project_session_memory_persist(tmp_path: Path) -> None:
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    session_store = SessionStore(state_store=JsonStateStore(root))
    memory_store = EventMemoryStore(state_store=JsonStateStore(root))

    project_service.create_project("proj-1", "Project 1")
    session = session_store.create_session(session_id="sess-1", project_id="proj-1")
    session.title = "Session 1"
    session_store.save_session(session)
    memory_store.append(
        MemoryEvent(event_id="event-1", kind="review_written", payload={"session_id": "sess-1"})
    )

    project_service2 = LearningProjectService(state_store=JsonStateStore(root))
    session_store2 = SessionStore(state_store=JsonStateStore(root))
    memory_store2 = EventMemoryStore(state_store=JsonStateStore(root))

    assert project_service2.get_project("proj-1") is not None
    assert session_store2.get_session("sess-1") is not None
    assert memory_store2.list_events_for_session("sess-1")
