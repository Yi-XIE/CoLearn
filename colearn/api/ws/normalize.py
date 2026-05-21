from __future__ import annotations

from typing import Any
from uuid import uuid4


def normalize_attachments(frame: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in list(frame.get("attachments") or frame.get("media") or []):
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "name": str(item.get("name") or ""),
                "content_type": str(item.get("content_type") or item.get("kind") or "image"),
                "data": str(item.get("data") or item.get("data_url") or ""),
                "size": int(item.get("size") or 0),
            }
        )
    return normalized


def project_id_from_frame(frame: dict[str, Any]) -> str:
    return str(frame.get("project_id") or "default-project")


def project_title_from_frame(frame: dict[str, Any]) -> str:
    return str(frame.get("project_title") or project_id_from_frame(frame) or "CoLearn")


def skills_from_frame(frame: dict[str, Any]) -> list[str]:
    skills: list[str] = []
    for item in list(frame.get("skills") or []):
        value = str(item or "").strip()
        if value:
            skills.append(value)
    return skills


def ready_event() -> dict[str, Any]:
    session_id = str(uuid4())
    return {
        "event": "ready",
        "chat_id": session_id,
        "client_id": str(uuid4())[:8],
    }


def normalize_turn_frame(frame: dict[str, Any]) -> dict[str, Any]:
    msg_type = str(frame.get("type") or "").strip()
    if msg_type != "message":
        return dict(frame)
    return {
        "type": "start_turn",
        "session_id": str(frame.get("chat_id") or frame.get("session_id") or ""),
        "project_id": project_id_from_frame(frame),
        "project_title": project_title_from_frame(frame),
        "content": str(frame.get("content") or ""),
        "attachments": list(frame.get("media") or []),
        "language": str(frame.get("language") or "zh"),
        "skills": list(frame.get("skills") or []),
    }
