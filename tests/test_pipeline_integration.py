"""Integration test — full 5-stage pipeline with fakes (async only)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from conftest import FakeExecutor, FakeRetrievalService

from colearn.app.learning_orchestrator import LearningOrchestrator
from colearn.compression import RuntimeCompressionBridge, ProductCompressionBridge
from colearn.knowledge import KnowledgeWorkspaceService
from colearn.memory.store import EventMemoryStore
from colearn.projects.service import LearningProjectService
from colearn.sessions.store import SessionStore
from colearn.storage.json_store import JsonStateStore


def _build_orchestrator(tmp: str):
    state = JsonStateStore(root=Path(tmp))
    return LearningOrchestrator(
        project_service=LearningProjectService(state_store=state),
        session_store=SessionStore(state_store=state),
        memory_store=EventMemoryStore(state_store=state),
        knowledge_service=KnowledgeWorkspaceService(),
        retrieval_service=FakeRetrievalService(),
        executor=FakeExecutor(),
        runtime_compression=RuntimeCompressionBridge(),
        product_compression=ProductCompressionBridge(),
    )


def _tmpdir():
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


async def test_pipeline_end_to_end():
    with _tmpdir() as tmp:
        orch = _build_orchestrator(tmp)
        result = await orch.run_turn_async(
            session_id="async-session",
            user_message="Explain gravity",
            project_id="async-project",
        )
        assert result is not None
        assert "gravity" in result.final_text.lower()
        session = orch.session_store.get_session("async-session")
        assert session is not None
        assert len(session.messages) == 2


async def test_multi_turn_session():
    with _tmpdir() as tmp:
        orch = _build_orchestrator(tmp)
        await orch.run_turn_async(session_id="multi", user_message="Turn 1", project_id="p")
        await orch.run_turn_async(session_id="multi", user_message="Turn 2", project_id="p")
        await orch.run_turn_async(session_id="multi", user_message="Turn 3", project_id="p")

        session = orch.session_store.get_session("multi")
        assert len(session.messages) == 6
