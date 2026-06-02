"""Tests for blackboard writeback logic."""
import pytest

from colearn.colearn_board.colearn_writeback import BlackboardWriter
from colearn.colearn_state.colearn_models import (
    Blackboard,
    BlackboardLearning,
    BlackboardRuntime,
    LearningSession,
)


@pytest.fixture
def session():
    """Create a fresh learning session for testing."""
    return LearningSession(
        session_id="test-session",
        blackboard=Blackboard(
            learning=BlackboardLearning(),
            runtime=BlackboardRuntime(),
        ),
    )


def test_update_progress(session):
    """BlackboardWriter should update current_progress."""
    writer = BlackboardWriter()
    turn_result = {"current_progress": "已学习数据概念"}

    writer.update_learning_state(session, turn_result)

    assert session.blackboard.learning.current_progress == "已学习数据概念"


def test_append_blockers_with_dedup(session):
    """BlackboardWriter should append blockers with deduplication."""
    session.blackboard.learning.blockers = ["旧blocker"]

    writer = BlackboardWriter()
    turn_result = {"blockers": ["新blocker", "旧blocker", "另一个blocker"]}

    writer.update_learning_state(session, turn_result)

    assert session.blackboard.learning.blockers == [
        "旧blocker",
        "新blocker",
        "另一个blocker",
    ]


def test_append_objections_with_dedup(session):
    """BlackboardWriter should append objections with deduplication."""
    session.blackboard.learning.objections = ["旧objection"]

    writer = BlackboardWriter()
    turn_result = {"objections": ["新objection", "旧objection"]}

    writer.update_learning_state(session, turn_result)

    assert session.blackboard.learning.objections == [
        "旧objection",
        "新objection",
    ]


def test_replace_pending_checks(session):
    """BlackboardWriter should replace pending_checks (not append)."""
    session.blackboard.learning.pending_checks = ["旧check"]

    writer = BlackboardWriter()
    turn_result = {"pending_checks": ["新check1", "新check2"]}

    writer.update_learning_state(session, turn_result)

    assert session.blackboard.learning.pending_checks == ["新check1", "新check2"]


def test_update_continuation(session):
    """BlackboardWriter should update continuation."""
    writer = BlackboardWriter()
    turn_result = {"continuation": "下一步：学习模型概念"}

    writer.update_learning_state(session, turn_result)

    assert session.blackboard.learning.continuation == "下一步：学习模型概念"


def test_update_active_node_id(session):
    """BlackboardWriter should update active_node_id."""
    writer = BlackboardWriter()
    turn_result = {"active_node_id": "ml.model.basic"}

    writer.update_learning_state(session, turn_result)

    assert session.blackboard.learning.active_node_id == "ml.model.basic"


def test_append_completed_nodes(session):
    """BlackboardWriter should append completed_nodes with deduplication."""
    session.blackboard.learning.completed_nodes = ["ml.data.basic"]

    writer = BlackboardWriter()
    turn_result = {"completed_nodes": ["ml.pattern.basic", "ml.data.basic"]}

    writer.update_learning_state(session, turn_result)

    assert session.blackboard.learning.completed_nodes == [
        "ml.data.basic",
        "ml.pattern.basic",
    ]


def test_update_goal(session):
    """BlackboardWriter should update learning goal."""
    writer = BlackboardWriter()
    turn_result = {"goal": "学习机器学习基础"}

    writer.update_learning_state(session, turn_result)

    assert session.blackboard.learning.goal == "学习机器学习基础"


def test_update_timestamp(session):
    """BlackboardWriter should update session timestamp."""
    writer = BlackboardWriter()
    turn_result = {"current_progress": "测试"}

    old_timestamp = session.updated_at
    writer.update_learning_state(session, turn_result)

    assert session.updated_at != old_timestamp
