"""Session-facing serialization helpers for the CoLearn backend."""

from __future__ import annotations

import time
from typing import Any

from colearn.projects.service import LearningProjectService
from colearn.sessions.store import LearningSession
from colearn.sessions.titles import derive_session_title, first_user_message


def serialize_session_summary(
    session: LearningSession,
    *,
    project_service: LearningProjectService,
) -> dict[str, Any]:
    project = project_service.get_project(session.project_id) if session.project_id else None
    messages = list(session.messages)
    preview_message = first_user_message(messages)
    title = str(session.title or "").strip()
    if not title and preview_message:
        title = derive_session_title(preview_message)
    board_facts = dict(session.board_facts or {})
    latest_review = dict(getattr(session, "pending_review", {}) or {})
    latest_review_status = str(latest_review.get("status") or ("ready" if latest_review.get("summary") else "empty"))
    return {
        "id": session.session_id,
        "session_id": session.session_id,
        "title": title,
        "title_is_custom": bool(getattr(session, "title_is_custom", False)),
        "project_id": session.project_id,
        "project_title": project.title if project else session.project_id,
        "turn_mode": session.turn_mode,
        "board_facts": board_facts,
        "board_version": int(session.board_version or 1),
        "board_updated_at": str(board_facts.get("updated_at") or ""),
        "latest_review_status": latest_review_status,
        "source_refs": list(session.source_refs),
        "memory_refs": list(session.memory_refs),
        "anchor": project.anchor if project else {},
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "message_count": len(messages),
        "last_message": preview_message,
        "status": session.status,
        "active_turn_id": session.active_turn_id,
        "preferences": {
            "tools": [],
            "knowledge_bases": [],
            "language": "zh",
            "source_references": [],
        },
    }


def serialize_session_detail(
    session: LearningSession,
    *,
    project_service: LearningProjectService,
) -> dict[str, Any]:
    summary = serialize_session_summary(session, project_service=project_service)
    summary["messages"] = [
        {
            "id": index + 1,
            "session_id": session.session_id,
            "role": item.get("role") or "assistant",
            "content": item.get("content") or "",
            "events": [],
            "attachments": [],
            "metadata": {},
            "created_at": item.get("created_at", session.created_at),
        }
        for index, item in enumerate(session.messages)
    ]
    summary["active_turns"] = list(session.active_turns)
    summary["last_turn_result"] = dict(session.last_turn_result or {})
    return summary


def touch_session(session: LearningSession) -> LearningSession:
    now = int(time.time())
    if not session.created_at:
        session.created_at = now
    session.updated_at = now
    return session
