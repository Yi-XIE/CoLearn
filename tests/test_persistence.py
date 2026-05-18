from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import colearn.devtools as devtools
from colearn.memory.store import EventMemoryStore, MemoryEvent
from colearn.devtools import reset_state
from colearn.projects.service import LearningProjectService
from colearn.storage.records import (
    memory_event_from_record,
    memory_event_to_record,
    project_from_record,
    project_to_record,
    session_from_record,
    session_to_record,
)
from colearn.sessions.store import SessionStore
from colearn.storage.json_store import JsonStateStore


def test_json_state_store_roundtrip(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path)
    store.write_json("sample.json", {"ok": True})
    assert store.read_json("sample.json", {}) == {"ok": True}
    assert not (tmp_path / ".sample.json.tmp").exists()


def test_json_state_store_default_uses_env_state_root(monkeypatch, tmp_path: Path) -> None:
    state_root = tmp_path / ".colearn" / "state"
    monkeypatch.setenv("COLEARN_STATE_ROOT", str(state_root))
    store = JsonStateStore()
    assert store.root == state_root.resolve()


def test_project_session_memory_persist(tmp_path: Path) -> None:
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    session_store = SessionStore(state_store=JsonStateStore(root))
    memory_store = EventMemoryStore(state_store=JsonStateStore(root))

    project_service.create_project("proj-1", "Project 1")
    session = session_store.create_session(session_id="sess-1", project_id="proj-1")
    session.title = "Session 1"
    session.created_at = 111
    session.updated_at = 222
    session_store.save_session(session)
    memory_store.append(
        MemoryEvent(event_id="event-1", kind="review_written", payload={"session_id": "sess-1"})
    )

    project_service2 = LearningProjectService(state_store=JsonStateStore(root))
    session_store2 = SessionStore(state_store=JsonStateStore(root))
    memory_store2 = EventMemoryStore(state_store=JsonStateStore(root))

    assert project_service2.get_project("proj-1") is not None
    loaded_session = session_store2.get_session("sess-1")
    assert loaded_session is not None
    assert loaded_session.created_at == 111
    assert loaded_session.updated_at == 222
    assert memory_store2.list_events_for_session("sess-1")


def test_record_codecs_roundtrip_and_legacy_session_compatibility(tmp_path: Path) -> None:
    session = session_from_record(
        {
            "session_id": "legacy-session",
            "project_id": "proj-legacy",
            "title": "Legacy",
            "unknown": "ignored",
        }
    )
    assert session.created_at == 0
    assert session.updated_at == 0
    session.created_at = 10
    session.updated_at = 20
    session_record = session_to_record(session)
    assert session_from_record(session_record).updated_at == 20

    project_service = LearningProjectService(state_store=JsonStateStore(tmp_path / "state"))
    project = project_service.create_project("proj-codec", "Codec")
    project.retrieval_profile = {"readiness": "ready"}
    assert project_from_record(project_to_record(project)).retrieval_profile["readiness"] == "ready"

    event = MemoryEvent(event_id="event-codec", kind="turn_completed", payload={"session_id": "legacy-session"})
    assert memory_event_from_record(memory_event_to_record(event)).payload["session_id"] == "legacy-session"


def test_reset_state_dry_run_and_default_env_behavior(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    (root / ".colearn" / "state").mkdir(parents=True)
    (root / ".colearn" / "test-state").mkdir(parents=True)
    (root / ".colearn" / "test-results").mkdir(parents=True)
    env_path = root / ".env"
    env_path.write_text("OPENAI_API_KEY=test\n", encoding="utf-8")

    preview = reset_state(root=root, dry_run=True)
    assert ".colearn/state" in preview
    assert ".colearn/test-results" in preview
    assert env_path.exists()

    removed = reset_state(root=root)
    assert ".colearn/state" in removed
    assert not (root / ".colearn" / "state").exists()
    assert not (root / ".colearn" / "test-results").exists()
    assert env_path.exists()


def test_reset_state_include_env_and_workspace_boundary(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    env_path = root / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("OPENAI_API_KEY=test\n", encoding="utf-8")

    reset_state(root=root, include_env=True)
    assert not env_path.exists()

    outside = tmp_path / "outside"
    outside.mkdir()
    original_paths = list(devtools.DEFAULT_RESET_PATHS)
    try:
        devtools.DEFAULT_RESET_PATHS[:] = ["../outside"]
        try:
            reset_state(root=root, dry_run=True)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected workspace boundary validation to reject outside path usage")
    finally:
        devtools.DEFAULT_RESET_PATHS[:] = original_paths
