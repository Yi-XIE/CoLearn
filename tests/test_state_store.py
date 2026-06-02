"""Tests for SessionStore."""
import tempfile
from pathlib import Path

import pytest

from colearn.colearn_state.colearn_store import SessionStore


@pytest.fixture
def temp_store():
    """Create a SessionStore with temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionStore(Path(tmpdir) / "sessions")
        yield store


def test_create_session(temp_store):
    """Test create_session method."""
    session = temp_store.create_session("test_001")
    assert session.session_id == "test_001"
    assert session.blackboard.learning.goal is None
    assert session.blackboard.runtime.current_task_status == "IDLE"


def test_save_and_load(temp_store):
    """Test save and load methods."""
    session = temp_store.create_session("test_002")
    session.blackboard.learning.goal = "Learn ML basics"
    session.blackboard.runtime.current_task_status = "RUNNING"

    temp_store.save(session)

    loaded = temp_store.load("test_002")
    assert loaded is not None
    assert loaded.session_id == "test_002"
    assert loaded.blackboard.learning.goal == "Learn ML basics"
    assert loaded.blackboard.runtime.current_task_status == "RUNNING"


def test_load_nonexistent(temp_store):
    """Test load with non-existent session."""
    loaded = temp_store.load("nonexistent")
    assert loaded is None


def test_atomic_write(temp_store):
    """Test atomic write behavior."""
    session = temp_store.create_session("test_003")
    temp_store.save(session)

    session_file = temp_store._session_file("test_003")
    assert session_file.exists()

    temp_file = temp_store._temp_file("test_003")
    assert not temp_file.exists()


def test_list_sessions(temp_store):
    """Test list_sessions method."""
    temp_store.save(temp_store.create_session("test_004"))
    temp_store.save(temp_store.create_session("test_005"))

    sessions = temp_store.list_sessions()
    assert len(sessions) == 2
    assert "test_004" in sessions
    assert "test_005" in sessions


def test_blackboard_dual_domain(temp_store):
    """Test blackboard dual-domain structure."""
    session = temp_store.create_session("test_006")

    session.blackboard.learning.active_node_id = "ml.model.basic"
    session.blackboard.learning.planned_nodes = ["ml.data.basic", "ml.pattern.basic"]
    session.blackboard.runtime.last_observed_ip = "127.0.0.1"
    session.blackboard.runtime.active_blind_spots = ["misconception_1"]

    temp_store.save(session)
    loaded = temp_store.load("test_006")

    assert loaded.blackboard.learning.active_node_id == "ml.model.basic"
    assert len(loaded.blackboard.learning.planned_nodes) == 2
    assert loaded.blackboard.runtime.last_observed_ip == "127.0.0.1"
    assert len(loaded.blackboard.runtime.active_blind_spots) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
