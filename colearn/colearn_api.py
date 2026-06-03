"""Read-only CoLearn API payload helpers for NanoBot host routes."""
from __future__ import annotations

from typing import Any

from colearn.colearn_context import (
    bind_latest_session,
    get_current_session_id,
    get_session_store,
)
from colearn.colearn_graph import colearn_graph_snapshot
from colearn.colearn_tools.colearn_command import colearn_snapshot
from colearn.colearn_wiki.colearn_query import WikiQueryService


def resolve_current_session_id(prefer_learning: bool = True) -> str | None:
    """Resolve the current session id, falling back to the latest persisted session."""
    session_id = get_current_session_id()
    if session_id:
        return session_id
    session = bind_latest_session(prefer_learning=prefer_learning)
    return session.session_id if session is not None else None


def blackboard_payload(*, prefer_learning: bool = True) -> dict[str, Any]:
    """Return the JSON payload for the current blackboard snapshot."""
    resolve_current_session_id(prefer_learning=prefer_learning)
    return colearn_snapshot()


def graph_payload(
    wiki_service: WikiQueryService | None = None,
    *,
    prefer_learning: bool = True,
) -> dict[str, Any]:
    """Return the JSON payload for the current knowledge graph snapshot."""
    resolve_current_session_id(prefer_learning=prefer_learning)
    return colearn_graph_snapshot(wiki_service=wiki_service)


def current_session_payload(*, prefer_learning: bool = True) -> dict[str, Any]:
    """Return a lightweight JSON snapshot for the current CoLearn session."""
    session_id = resolve_current_session_id(prefer_learning=prefer_learning)
    if not session_id:
        return {
            "ok": True,
            "session_id": None,
            "has_session": False,
            "session_mode": "CHAT",
            "state_root": str(get_session_store().state_root),
        }

    snapshot = blackboard_payload(prefer_learning=prefer_learning)
    if not snapshot.get("ok"):
        return {
            "ok": False,
            "session_id": session_id,
            "has_session": False,
            "state_root": str(get_session_store().state_root),
            "error": snapshot.get("error", "Unknown CoLearn error"),
        }

    return {
        "ok": True,
        "session_id": session_id,
        "has_session": True,
        "session_mode": snapshot.get("session_mode", "CHAT"),
        "turn_mode": snapshot.get("turn_mode"),
        "goal": (snapshot.get("learning") or {}).get("goal"),
        "active_node_id": (snapshot.get("learning") or {}).get("active_node_id"),
        "updated_at": snapshot.get("updated_at"),
        "state_root": str(get_session_store().state_root),
    }
