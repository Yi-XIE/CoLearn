"""Session routes."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from colearn.api.dependencies import orchestrator, project_service, session_store
from colearn.api.schemas import SessionCreatePayload, SessionUpdatePayload
from colearn.api.session_api import serialize_session_detail, serialize_session_summary, touch_session

router = APIRouter()


@router.get("/api/v1/sessions")
def list_sessions(limit: int = 50, offset: int = 0, project_id: str | None = None) -> dict[str, Any]:
    sessions = session_store.list_sessions()
    if project_id:
        sessions = [item for item in sessions if item.project_id == project_id]
    sliced = sessions[offset : offset + limit]
    return {
        "sessions": [
            serialize_session_summary(item, project_service=project_service)
            for item in sliced
        ]
    }


@router.post("/api/v1/sessions")
def create_session(payload: SessionCreatePayload) -> dict[str, Any]:
    session = session_store.create_session(
        session_id=str(uuid4()),
        project_id=payload.project_id,
        title=payload.title or payload.project_title or payload.project_id,
        turn_mode=payload.turn_mode,
    )
    session.source_refs = list(payload.source_refs)
    session.memory_refs = list(payload.memory_refs)
    touch_session(session)
    session_store.save_session(session)
    project = project_service.get_project(payload.project_id)
    if project is None:
        project = project_service.create_project(
            payload.project_id,
            title=payload.project_title or payload.project_id,
        )
    if payload.source_refs:
        project.source_refs = list(payload.source_refs)
    if payload.memory_refs:
        project.memory_refs = list(payload.memory_refs)
    project_service.save_project(project)
    return {"session": serialize_session_detail(session, project_service=project_service)}


@router.get("/api/v1/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return serialize_session_detail(session, project_service=project_service)


@router.patch("/api/v1/sessions/{session_id}")
def update_session(session_id: str, payload: SessionUpdatePayload) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session.title = payload.title or session.title
    touch_session(session)
    session_store.save_session(session)
    return {"session": serialize_session_detail(session, project_service=project_service)}


@router.delete("/api/v1/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    del session_store._sessions[session_id]
    return {"deleted": True}


@router.post("/api/v1/sessions/{session_id}/pause")
def pause_session(session_id: str) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session.turn_mode = "PAUSED"
    session.board_facts = {
        **dict(session.board_facts or {}),
        "current_turn_mode": "PAUSED",
    }
    touch_session(session)
    session_store.save_session(session)
    return {"session": serialize_session_detail(session, project_service=project_service)}


@router.post("/api/v1/sessions/{session_id}/resume")
def resume_session(session_id: str) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.turn_mode == "PAUSED":
        session.turn_mode = "EXPLORE"
        session.board_facts = {
            **dict(session.board_facts or {}),
            "current_turn_mode": "EXPLORE",
        }
    touch_session(session)
    session_store.save_session(session)
    return {"session": serialize_session_detail(session, project_service=project_service)}

@router.get("/api/v1/sessions/{session_id}/board_history")
def session_board_history(session_id: str) -> dict[str, Any]:
    """Return the audit trail of board snapshot derivations for this session.

    Lets the frontend show 'how the system's understanding of the student
    evolved over time' — derived BoardFacts changes (S1 diff entries).
    """
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    events = orchestrator.memory_store.list_events_for_session(session_id)
    history = [
        {
            "event_id": e.event_id,
            "kind": e.kind,
            "payload": e.payload,
        }
        for e in events
        if e.kind in ("board_snapshot_derived", "board_snapshot_failed", "board_patch_applied")
    ]
    return {"session_id": session_id, "history": history}
