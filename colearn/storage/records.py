"""Record codecs for JSON-backed CoLearn state."""

from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from typing import Any


def _record_from_dataclass(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return dict(asdict(value))
    return dict(value or {})


def _pick_record_fields(record: dict[str, Any], model: type[Any]) -> dict[str, Any]:
    allowed = {field.name for field in fields(model)}
    return {key: value for key, value in record.items() if key in allowed}


def session_to_record(session: Any) -> dict[str, Any]:
    return _record_from_dataclass(session)


def session_from_record(record: dict[str, Any]) -> Any:
    from colearn.sessions.store import LearningSession

    payload = _pick_record_fields(dict(record or {}), LearningSession)
    payload["session_id"] = str(payload.get("session_id") or "")
    payload["project_id"] = str(payload.get("project_id") or "")
    payload["title"] = str(payload.get("title") or "")
    payload["created_at"] = int(payload.get("created_at") or 0)
    payload["updated_at"] = int(payload.get("updated_at") or 0)
    payload["turn_mode"] = str(payload.get("turn_mode") or "EXPLORE")
    payload["board_facts"] = dict(payload.get("board_facts") or {})
    payload["board_version"] = int(payload.get("board_version") or 1)
    payload["status"] = str(payload.get("status") or "idle")
    payload["source_refs"] = list(payload.get("source_refs") or [])
    payload["memory_refs"] = list(payload.get("memory_refs") or [])
    payload["messages"] = list(payload.get("messages") or [])
    payload["continuation_prompt"] = str(payload.get("continuation_prompt") or "")
    payload["last_turn_result"] = dict(payload.get("last_turn_result") or {})
    payload["pending_review"] = dict(payload.get("pending_review") or {})
    payload["active_turn_id"] = payload.get("active_turn_id")
    payload["active_turns"] = list(payload.get("active_turns") or [])
    return LearningSession(**payload)


def project_to_record(project: Any) -> dict[str, Any]:
    return _record_from_dataclass(project)


def project_from_record(record: dict[str, Any]) -> Any:
    from colearn.projects.models import LearningProject

    payload = _pick_record_fields(dict(record or {}), LearningProject)
    payload["project_id"] = str(payload.get("project_id") or "")
    payload["title"] = str(payload.get("title") or "")
    payload["goal"] = str(payload.get("goal") or "")
    payload["source_refs"] = list(payload.get("source_refs") or [])
    payload["memory_refs"] = list(payload.get("memory_refs") or [])
    payload["turn_mode"] = str(payload.get("turn_mode") or "EXPLORE")
    payload["board_facts"] = dict(payload.get("board_facts") or {})
    payload["board_version"] = int(payload.get("board_version") or 1)
    payload["anchor"] = dict(payload.get("anchor") or {})
    payload["anchor_status"] = str(payload.get("anchor_status") or "missing")
    payload["source_subset"] = list(payload.get("source_subset") or [])
    payload["latest_review"] = dict(payload.get("latest_review") or {})
    payload["current_main_goal"] = str(payload.get("current_main_goal") or "")
    payload["retrieval_profile"] = dict(payload.get("retrieval_profile") or {})
    return LearningProject(**payload)


def memory_event_to_record(event: Any) -> dict[str, Any]:
    return _record_from_dataclass(event)


def memory_event_from_record(record: dict[str, Any]) -> Any:
    from colearn.memory.store import MemoryEvent

    payload = _pick_record_fields(dict(record or {}), MemoryEvent)
    payload["event_id"] = str(payload.get("event_id") or "")
    payload["kind"] = str(payload.get("kind") or "event")
    payload["payload"] = dict(payload.get("payload") or {})
    return MemoryEvent(**payload)
