"""Integration tests for board snapshot consolidation cycle inside the orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

from colearn.app.learning_orchestrator import LearningOrchestrator
from colearn.learning.board_deriver import BoardSnapshotDeriver
from colearn.memory.store import EventMemoryStore, MemoryEvent
from colearn.projects.service import LearningProjectService
from colearn.sessions.store import SessionStore
from colearn.storage.json_store import JsonStateStore

from tests.test_learning_orchestrator import (
    FakeExecutor,
    FakeRetrievalService,
)


def _make_orchestrator(tmp_path: Path, *, llm_responses: list[str], deriver_kwargs: dict | None = None):
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    session_store = SessionStore(state_store=JsonStateStore(root))
    memory_store = EventMemoryStore(state_store=JsonStateStore(root))

    project_service.create_project("proj-1", "Linear Algebra")
    source_file = tmp_path / "src.md"
    source_file.write_text("Some content.", encoding="utf-8")
    project = project_service.get_project("proj-1")
    project.source_refs = [str(source_file)]
    project.anchor = {"topic": "matrix"}
    project.anchor_status = "ready"
    project_service.save_project(project)

    session = session_store.create_session(session_id="sess-1", project_id="proj-1")
    session.source_refs = [str(source_file)]
    session_store.save_session(session)

    response_iter = iter(llm_responses)

    def fake_llm(*, system, user):
        return next(response_iter)

    deriver = BoardSnapshotDeriver(llm_call=fake_llm, **(deriver_kwargs or {}))

    orchestrator = LearningOrchestrator(
        project_service=project_service,
        session_store=session_store,
        executor=FakeExecutor(),
        memory_store=memory_store,
        retrieval_service=FakeRetrievalService(),
        board_deriver=deriver,
    )
    # Trigger derivation more aggressively for tests
    orchestrator.BOARD_DERIVATION_EVENT_INTERVAL = 1
    return orchestrator


def test_board_snapshot_event_appended_after_turn(tmp_path: Path):
    valid_response = json.dumps({
        "current_turn_mode": "VERIFY",
        "mastery_level": 0.6,
        "cognitive_load": "LOW",
        "active_node_id": "x",
        "active_node_label": "X",
        "critical_blockers": [],
        "unverified_gaps": [],
        "next_prompt_hint": "go deeper",
    })
    orchestrator = _make_orchestrator(tmp_path, llm_responses=[valid_response] * 5)
    orchestrator.run_turn(
        session_id="sess-1",
        project_id="proj-1",
        user_message="explain matrices",
    )
    events = orchestrator.memory_store.list_events_for_session("sess-1")
    derived = [e for e in events if e.kind == "board_snapshot_derived"]
    assert len(derived) >= 1, f"expected at least one board_snapshot_derived event, got kinds={[e.kind for e in events]}"
    assert derived[0].payload["board_version"] >= 1


def test_board_snapshot_failed_when_llm_returns_garbage(tmp_path: Path):
    orchestrator = _make_orchestrator(tmp_path, llm_responses=["not json at all"] * 3)
    orchestrator.run_turn(
        session_id="sess-1",
        project_id="proj-1",
        user_message="hi",
    )
    events = orchestrator.memory_store.list_events_for_session("sess-1")
    failed = [e for e in events if e.kind == "board_snapshot_failed"]
    assert len(failed) >= 1


def test_no_deriver_means_no_board_snapshot_events(tmp_path: Path):
    """Backward-compat: without board_deriver, behavior is unchanged."""
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    session_store = SessionStore(state_store=JsonStateStore(root))
    memory_store = EventMemoryStore(state_store=JsonStateStore(root))
    project_service.create_project("proj-1", "Test")
    project = project_service.get_project("proj-1")
    project.anchor = {"topic": "x"}
    project.anchor_status = "ready"
    project_service.save_project(project)
    session = session_store.create_session(session_id="sess-1", project_id="proj-1")
    session_store.save_session(session)

    orchestrator = LearningOrchestrator(
        project_service=project_service,
        session_store=session_store,
        executor=FakeExecutor(),
        memory_store=memory_store,
        retrieval_service=FakeRetrievalService(),
        # board_deriver explicitly omitted
    )
    orchestrator.run_turn(session_id="sess-1", project_id="proj-1", user_message="hi")
    events = orchestrator.memory_store.list_events_for_session("sess-1")
    assert not [e for e in events if e.kind.startswith("board_snapshot_")]
