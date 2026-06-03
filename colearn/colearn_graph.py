"""Read-only graph snapshots derived from the current CoLearn session and Wiki."""
from __future__ import annotations

from typing import Any

from colearn.colearn_context import get_current_session_id, get_session
from colearn.colearn_wiki.colearn_query import WikiQueryService


def _label_for(page_id: str, wiki_service: WikiQueryService) -> str:
    page = wiki_service.get_by_id(page_id)
    if not page:
        return page_id
    return str(page.get("title") or page_id)


def colearn_graph_snapshot(
    wiki_service: WikiQueryService | None = None,
) -> dict[str, Any]:
    """Return a graph-focused view for the active CoLearn session."""
    session_id = get_current_session_id()
    if not session_id:
        return {
            "ok": False,
            "session_id": None,
            "focus_node_id": None,
            "nodes": [],
            "edges": [],
            "error": "No active CoLearn session found.",
        }

    session = get_session()
    if not session:
        return {
            "ok": False,
            "session_id": session_id,
            "focus_node_id": None,
            "nodes": [],
            "edges": [],
            "error": f"Session `{session_id}` not found in state store.",
        }

    service = wiki_service or WikiQueryService()
    learning = session.blackboard.learning
    focus_node_id = learning.active_node_id
    if not focus_node_id:
        return {
            "ok": True,
            "session_id": session_id,
            "focus_node_id": None,
            "nodes": [],
            "edges": [],
            "learning_goal": learning.goal,
        }

    focus_page = service.get_by_id(focus_node_id)
    if not focus_page:
        return {
            "ok": True,
            "session_id": session_id,
            "focus_node_id": focus_node_id,
            "nodes": [
                {
                    "id": focus_node_id,
                    "label": focus_node_id,
                    "kind": "concept",
                    "state": "missing",
                }
            ],
            "edges": [],
            "learning_goal": learning.goal,
        }

    nodes: dict[str, dict[str, Any]] = {
        focus_node_id: {
            "id": focus_node_id,
            "label": str(focus_page.get("title") or focus_node_id),
            "kind": str(focus_page.get("page_type") or "concept"),
            "state": "active",
        }
    }
    edges: list[dict[str, str]] = []

    prerequisites = list(focus_page.get("prerequisites", []))
    for prereq_id in prerequisites:
        nodes[prereq_id] = {
            "id": prereq_id,
            "label": _label_for(prereq_id, service),
            "kind": "concept",
            "state": "prerequisite",
        }
        edges.append(
            {
                "source": prereq_id,
                "target": focus_node_id,
                "kind": "prerequisite",
            }
        )

    for completed_id in learning.completed_nodes:
        state = "completed"
        if completed_id == focus_node_id:
            state = "active"
        nodes[completed_id] = {
            "id": completed_id,
            "label": _label_for(completed_id, service),
            "kind": "concept",
            "state": state,
        }

    for planned_id in learning.planned_nodes:
        nodes.setdefault(
            planned_id,
            {
                "id": planned_id,
                "label": _label_for(planned_id, service),
                "kind": "concept",
                "state": "planned",
            },
        )

    return {
        "ok": True,
        "session_id": session_id,
        "focus_node_id": focus_node_id,
        "learning_goal": learning.goal,
        "nodes": list(nodes.values()),
        "edges": edges,
    }
