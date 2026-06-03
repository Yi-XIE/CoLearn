"""Tests for CoLearn read-only API payload helpers."""
from pathlib import Path

import pytest

from colearn.colearn_api import blackboard_payload, current_session_payload, graph_payload
from colearn.colearn_context import set_current_session_id, set_session_store
from colearn.colearn_state.colearn_store import SessionStore
from colearn.colearn_wiki.colearn_query import WikiQueryService


@pytest.fixture
def wiki_service():
    index_dir = Path(__file__).parent.parent / "knowledge" / "generated"
    if not index_dir.exists():
        pytest.skip("Wiki index not generated yet")
    return WikiQueryService(index_dir=index_dir)


def test_blackboard_payload_without_active_session():
    """blackboard payload should return a stable empty-state error shape."""
    set_current_session_id("missing-session")
    payload = blackboard_payload()

    assert payload["ok"] is False
    assert "error" in payload


def test_graph_payload_empty_state(tmp_path, wiki_service):
    """graph payload should stay stable when there is no active node."""
    store = SessionStore(tmp_path / "sessions")
    session = store.create_session("graph-empty")
    store.save(session)
    set_current_session_id("graph-empty")
    set_session_store(store)

    payload = graph_payload(wiki_service=wiki_service)

    assert payload["ok"] is True
    assert payload["focus_node_id"] is None
    assert payload["nodes"] == []
    assert payload["edges"] == []


def test_graph_payload_with_active_node(tmp_path, wiki_service):
    """graph payload should expose focus node, prerequisite nodes, and edges."""
    store = SessionStore(tmp_path / "sessions")
    session = store.create_session("graph-active")
    session.blackboard.learning.goal = "学习机器学习基础"
    session.blackboard.learning.active_node_id = "ml.model.basic"
    session.blackboard.learning.completed_nodes = ["ml.data.basic"]
    session.blackboard.learning.planned_nodes = ["ml.training.basic"]
    store.save(session)
    set_current_session_id("graph-active")
    set_session_store(store)

    payload = graph_payload(wiki_service=wiki_service)

    assert payload["ok"] is True
    assert payload["focus_node_id"] == "ml.model.basic"
    assert any(node["id"] == "ml.model.basic" and node["state"] == "active" for node in payload["nodes"])
    assert any(edge["target"] == "ml.model.basic" for edge in payload["edges"])


def test_blackboard_payload_falls_back_to_latest_learning_session(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    plain = store.create_session("plain")
    store.save(plain)

    learning = store.create_session("learning")
    learning.blackboard.learning.goal = "Learn linear algebra"
    store.save(learning)

    set_current_session_id("")
    set_session_store(store)

    payload = blackboard_payload()

    assert payload["ok"] is True
    assert payload["session_id"] == "learning"
    assert payload["learning"]["goal"] == "Learn linear algebra"


def test_current_session_payload_reports_empty_state(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    set_current_session_id("")
    set_session_store(store)

    payload = current_session_payload()

    assert payload["ok"] is True
    assert payload["has_session"] is False
    assert payload["session_id"] is None
    assert payload["session_mode"] == "CHAT"


def test_current_session_payload_uses_bound_or_latest_session(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    session = store.create_session("learning")
    session.blackboard.learning.goal = "Learn Bayes"
    session.blackboard.learning.active_node_id = "ml.probability.basic"
    store.save(session)

    set_current_session_id("")
    set_session_store(store)

    payload = current_session_payload()

    assert payload["ok"] is True
    assert payload["has_session"] is True
    assert payload["session_id"] == "learning"
    assert payload["goal"] == "Learn Bayes"
    assert payload["active_node_id"] == "ml.probability.basic"
