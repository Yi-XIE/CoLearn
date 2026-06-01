"""Instrumentation test: confirm normalize_learning_turn_result is called 1× per turn.

This is the POST-refactor state after eliminating redundant normalize calls.
The function is now called only once in FinalizeStage.run, which has full
retrieval metadata and produces the final persisted result.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from colearn.app.learning_orchestrator import LearningOrchestrator
from colearn.memory.store import EventMemoryStore
from colearn.projects.service import LearningProjectService
from colearn.sessions.store import SessionStore
from colearn.storage.json_store import JsonStateStore
from tests.conftest import FakeExecutor


@pytest.mark.anyio
async def test_normalize_called_once_per_turn(tmp_path):
    """POST-refactor: normalize_learning_turn_result is called 1× per turn (optimized).

    After refactoring, normalize is called only once in FinalizeStage.run (finalize.py),
    which has full retrieval metadata and produces the final persisted result.

    The previous redundant calls in executor.run_turn_async and execute._execute_turn_async
    have been eliminated, reducing unnecessary computation and improving performance.
    """
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    project = project_service.create_project("proj-count", "Count Test")
    session_store = SessionStore(state_store=JsonStateStore(root))
    session_store.create_session(session_id="sess-count", project_id="proj-count")
    executor = FakeExecutor()
    orchestrator = LearningOrchestrator(
        project_service=project_service,
        session_store=session_store,
        executor=executor,
        memory_store=EventMemoryStore(state_store=JsonStateStore(root)),
    )

    # Import the real function once to avoid recursion.
    from colearn.runtime_v2.result_bridge import normalize_learning_turn_result as real_normalize

    call_count = 0

    def counting_wrapper(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return real_normalize(*args, **kwargs)

    # Patch all three import sites so every call is counted.
    with patch("colearn.runtime_v2.result_bridge.normalize_learning_turn_result", wraps=counting_wrapper):
        with patch("colearn.runtime_v2.executor.normalize_learning_turn_result", new=counting_wrapper):
            with patch("colearn.app.stages.finalize.normalize_learning_turn_result", new=counting_wrapper):
                await orchestrator.run_turn_async(
                    session_id="sess-count",
                    project_id="proj-count",
                    user_message="hello",
                )

    # Post-refactor: 1 call per turn (only FinalizeStage.run).
    assert call_count == 1, f"Expected 1 normalize call (post-refactor), got {call_count}"
