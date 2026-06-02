"""Tests for ContextBuilder - learning context generation."""
import pytest
from pathlib import Path

from colearn.colearn_board.colearn_context_builder import ContextBuilder
from colearn.colearn_state.colearn_models import (
    Blackboard,
    BlackboardLearning,
    BlackboardRuntime,
    LearningSession,
)
from colearn.colearn_wiki.colearn_query import WikiQueryService


@pytest.fixture
def wiki_service():
    """Create WikiQueryService with test data."""
    # Use the real wiki index from knowledge/generated/
    index_dir = Path(__file__).parent.parent / "knowledge" / "generated"
    if not index_dir.exists():
        pytest.skip("Wiki index not generated yet")
    return WikiQueryService(index_dir=index_dir)


@pytest.fixture
def session_with_active_node():
    """Create a session with an active learning node."""
    return LearningSession(
        session_id="test-session",
        blackboard=Blackboard(
            learning=BlackboardLearning(
                goal="学习机器学习基础",
                active_node_id="ml.model.basic",
                current_progress="已学习数据和模式识别",
                blockers=["需要更多例子"],
            ),
            runtime=BlackboardRuntime(),
        ),
    )


@pytest.fixture
def session_no_active_node():
    """Create a session without an active node."""
    return LearningSession(
        session_id="test-session-2",
        blackboard=Blackboard(
            learning=BlackboardLearning(goal="学习物理"),
            runtime=BlackboardRuntime(),
        ),
    )


def test_build_context_with_valid_node(wiki_service, session_with_active_node):
    """ContextBuilder should generate context when active node exists."""
    builder = ContextBuilder(wiki_service=wiki_service)
    context = builder.build_learning_context(session_with_active_node)

    # Should contain the title
    assert "什么是模型" in context
    # Should contain learning goal from blackboard
    assert "学习机器学习基础" in context
    # Should contain current progress
    assert "已学习数据和模式识别" in context
    # Should contain blockers
    assert "需要更多例子" in context
    # Should contain prerequisites section
    assert "Prerequisites" in context or "先修知识" in context


def test_build_context_with_no_active_node(wiki_service, session_no_active_node):
    """ContextBuilder should return empty string when no active node."""
    builder = ContextBuilder(wiki_service=wiki_service)
    context = builder.build_learning_context(session_no_active_node)

    assert context == ""


def test_build_context_with_invalid_node(wiki_service):
    """ContextBuilder should handle invalid node gracefully."""
    session = LearningSession(
        session_id="test-session-3",
        blackboard=Blackboard(
            learning=BlackboardLearning(
                goal="测试",
                active_node_id="invalid.node.id",
            ),
            runtime=BlackboardRuntime(),
        ),
    )

    builder = ContextBuilder(wiki_service=wiki_service)
    context = builder.build_learning_context(session)

    assert "invalid.node.id" in context
    assert "[Node not found in Wiki]" in context
