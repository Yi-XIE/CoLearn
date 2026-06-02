"""Tests for /colearn command snapshot and Markdown rendering."""
from colearn.colearn_context import set_current_session_id, set_session_store
from colearn.colearn_state.colearn_store import SessionStore
from colearn.colearn_tools.colearn_command import colearn_command, colearn_snapshot


def test_colearn_snapshot_and_markdown(tmp_path):
    """The command should expose both structured snapshot and Markdown output."""
    store = SessionStore(tmp_path / "sessions")
    session = store.create_session("cmd-session")
    session.blackboard.learning.goal = "学习机器学习"
    session.blackboard.learning.active_node_id = "ml.model.basic"
    session.blackboard.learning.pending_checks = ["检查模型概念"]
    store.save(session)

    set_current_session_id("cmd-session")
    set_session_store(store)

    snapshot = colearn_snapshot()
    markdown = colearn_command()

    assert snapshot["ok"] is True
    assert snapshot["session_mode"] == "LEARNING"
    assert snapshot["turn_mode"] == "CHECK"
    assert snapshot["learning"]["goal"] == "学习机器学习"
    assert "CoLearn Dashboard" in markdown
    assert "检查模型概念" in markdown
