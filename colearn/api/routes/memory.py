"""Memory routes."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from colearn.api.dependencies import memory_doc_service, project_service, session_store, orchestrator
from colearn.api.schemas import MemoryFilePayload, MemoryRefreshPayload, MemoryUpdatePayload

router = APIRouter()


def _latest_session() -> Any | None:
    sessions = session_store.list_sessions()
    if not sessions:
        return None
    for session in reversed(sessions):
        if str(getattr(session, "continuation_prompt", "") or "").strip():
            return session
    return sessions[-1]


def _extract_blocker_summaries(board_facts: dict[str, Any] | None) -> list[dict[str, str]]:
    blockers = list(dict(board_facts or {}).get("gaps_and_blockers", {}).get("critical_blockers", []) or [])
    results: list[dict[str, str]] = []
    for item in blockers[:6]:
        if isinstance(item, dict):
            label = str(item.get("desc") or item.get("id") or "").strip()
            detail = str(item.get("status") or "critical").strip()
        else:
            label = str(item).strip()
            detail = "critical"
        if label:
            results.append({"label": label, "detail": detail})
    return results


@router.get("/api/v1/memory")
def get_memory() -> dict[str, Any]:
    return memory_doc_service.snapshot()


@router.get("/api/v1/memory/summary")
def get_memory_summary() -> dict[str, Any]:
    snapshot = memory_doc_service.snapshot()
    session = _latest_session()
    board_facts = dict((session.board_facts if session else {}) or {})
    continuity = str(session.continuation_prompt or "").strip() if session is not None else ""
    if not continuity:
        continuity = str(board_facts.get("continuation", {}).get("next_prompt_hint") or "").strip()

    long_term_facts: list[dict[str, str]] = []
    for ref in list(board_facts.get("evidence_refs", []) or [])[:6]:
        if not isinstance(ref, dict):
            continue
        source_ref = str(ref.get("source_ref") or ref.get("source_path") or "").strip()
        tool_name = str(ref.get("tool_name") or "source").strip()
        if source_ref:
            long_term_facts.append({"label": source_ref, "detail": tool_name})

    recent_events = []
    for event in reversed(orchestrator.memory_store.list_events()[-8:]):
        summary = str(event.payload.get("summary") or event.payload.get("review_summary") or event.payload or "").strip()
        recent_events.append(
            {
                "event_id": event.event_id,
                "kind": event.kind,
                "summary": summary,
                "recorded_at": str(event.payload.get("recorded_at") or event.payload.get("timestamp") or ""),
            }
        )

    return {
        **snapshot,
        "current_continuity": continuity,
        "long_term_facts": long_term_facts,
        "blockers": _extract_blocker_summaries(board_facts),
        "recent_events": recent_events,
    }


@router.get("/api/v1/memory/projection")
def memory_projection() -> dict[str, Any]:
    latest_steps: list[dict[str, Any]] = []
    for session in reversed(session_store.list_sessions()):
        project = project_service.get_project(session.project_id) if session.project_id else None
        continuation = str((session.board_facts or {}).get("continuation", {}).get("next_prompt_hint") or "").strip()
        if not continuation:
            continuation = str(session.continuation_prompt or "").strip()
        if not continuation:
            continue
        latest_steps.append(
            {
                "project_id": session.project_id,
                "project_title": project.title if project else session.project_id,
                "step": continuation,
                "recorded_at": getattr(session, "updated_at", int(time.time())),
            }
        )
        if len(latest_steps) >= 10:
            break
    return {
        "profile_projection": {
            "recent_next_steps": latest_steps,
        },
        "mastery_projection": {},
        "recent_events": [],
    }


@router.put("/api/v1/memory")
def update_memory(payload: MemoryUpdatePayload) -> dict[str, Any]:
    file_name = payload.file
    return memory_doc_service.update(file_name, payload.content)


@router.post("/api/v1/memory/refresh")
def refresh_memory(payload: MemoryRefreshPayload | None = None) -> dict[str, Any]:
    _ = payload
    latest_review = ""
    if session_store.list_sessions():
        latest_session = session_store.list_sessions()[-1]
        latest_review = str((latest_session.pending_review or {}).get("summary") or "")
    changed = False
    changed = memory_doc_service.refresh_summary(latest_review)
    return {**get_memory(), "changed": changed}


@router.post("/api/v1/memory/clear")
def clear_memory(payload: MemoryFilePayload) -> dict[str, Any]:
    file_name = payload.file
    return memory_doc_service.update(file_name, "")