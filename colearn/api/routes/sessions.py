"""Session routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from colearn.api.dependencies import orchestrator, project_service, session_store
from colearn.api.schemas import SessionCreatePayload, SessionUpdatePayload
from colearn.api.session_api import serialize_session_detail, serialize_session_summary, touch_session
from colearn.learning.constants import LearningEventType
from colearn.learning.events import MemoryEventKind
from colearn.learning.state import BoardFacts, LearningEvent

router = APIRouter()


@router.get("/api/v1/sessions")
def list_sessions(limit: int = 50, offset: int = 0, project_id: str | None = None) -> dict[str, Any]:
    sessions = session_store.list_sessions()
    if project_id:
        sessions = [item for item in sessions if item.project_id == project_id]
    sessions = sorted(
        sessions,
        key=lambda item: (
            int(getattr(item, "updated_at", 0) or getattr(item, "created_at", 0) or 0),
            int(getattr(item, "created_at", 0) or 0),
            str(getattr(item, "session_id", "") or ""),
        ),
        reverse=True,
    )
    sliced = sessions[offset : offset + limit]
    return {
        "sessions": [
            serialize_session_summary(item, project_service=project_service)
            for item in sliced
        ]
    }


@router.post("/api/v1/sessions")
def create_session(payload: SessionCreatePayload) -> dict[str, Any]:
    requested_turn_mode = str(payload.turn_mode or "").strip().upper()
    initial_turn_mode = requested_turn_mode or ("LEARN" if payload.mode == "learning" else "PAUSED")
    session = session_store.create_session(
        session_id=str(uuid4()),
        project_id=payload.project_id,
        title=(payload.title or "").strip(),
        turn_mode=initial_turn_mode,
    )
    session.mode = payload.mode
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
    next_title = payload.title.strip()
    if next_title:
        session.title = next_title
        session.title_is_custom = True
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
    executor = getattr(orchestrator, "executor", None)
    complete_goal = getattr(executor, "complete_sustained_goal", None)
    if callable(complete_goal):
        complete_goal(session_id=session_id, recap="Learning session paused.")
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
        session.mode = "learning"
        session.turn_mode = "LEARN"
        session.board_facts = {
            **dict(session.board_facts or {}),
            "current_turn_mode": "LEARN",
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
        if e.kind in (MemoryEventKind.BOARD_SNAPSHOT_DERIVED, MemoryEventKind.BOARD_SNAPSHOT_FAILED, MemoryEventKind.BOARD_PATCH_APPLIED)
    ]
    return {"session_id": session_id, "history": history}


class BoardCorrectionPayload(BaseModel):
    event_type: str  # "NODE_COMPLETED" or "BLOCKER_FOUND"
    node_id: str | None = None
    reason: str = ""


@router.post("/api/v1/sessions/{session_id}/board_corrections")
def apply_board_correction(
    session_id: str,
    payload: BoardCorrectionPayload,
) -> dict[str, Any]:
    """Apply user correction to board state (e.g., 'I still don't understand this')."""
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Construct LearningEvent with user_correction source
    event_payload: dict[str, Any] = {
        "source": "user_correction",
        "reason": payload.reason,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if payload.event_type == "NODE_COMPLETED":
        event_payload["node_id"] = payload.node_id or session.board_facts.get("current_progress", {}).get("active_node_id", "")
        event_payload["node_label"] = session.board_facts.get("current_progress", {}).get("active_node_label", "")
    elif payload.event_type == "BLOCKER_FOUND":
        event_payload["id"] = f"user_blk_{int(datetime.utcnow().timestamp())}"
        event_payload["type"] = "USER_REPORTED"
        event_payload["desc"] = payload.reason or "用户标记：还没理解这个概念"
        event_payload["node_id"] = payload.node_id or session.board_facts.get("current_progress", {}).get("active_node_id", "")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported event_type: {payload.event_type}")

    event = LearningEvent(
        type=LearningEventType(payload.event_type),
        payload=event_payload,
    )

    # Write audit log
    orchestrator.memory_store.append_event(
        session_id=session_id,
        kind=MemoryEventKind.USER_CORRECTION_APPLIED,
        payload={"event": {"type": event.type, "payload": event.payload}},
    )

    # Apply event to board
    from colearn.learning.board_hooks import apply_events
    board_facts = BoardFacts(**session.board_facts) if session.board_facts else BoardFacts(session_id=session_id)
    updated_board = apply_events(board_facts, [event])

    # Save updated board
    session.board_facts = {
        "project_id": updated_board.project_id,
        "session_id": updated_board.session_id,
        "current_turn_mode": updated_board.current_turn_mode,
        "learning_phase": updated_board.learning_phase,
        "board_version": updated_board.board_version,
        "updated_at": updated_board.updated_at,
        "current_progress": {
            "active_node_id": updated_board.current_progress.active_node_id,
            "active_node_label": updated_board.current_progress.active_node_label,
            "completed_node_ids": list(updated_board.current_progress.completed_node_ids),
            "path_node_ids": list(updated_board.current_progress.path_node_ids),
        },
        "student_snapshot": {
            "mastery_level": updated_board.student_snapshot.mastery_level,
            "cognitive_load": updated_board.student_snapshot.cognitive_load,
            "last_intent": updated_board.student_snapshot.last_intent,
        },
        "gaps_and_blockers": {
            "critical_blockers": [
                {"id": b.id, "type": b.type, "desc": b.desc}
                for b in updated_board.gaps_and_blockers.critical_blockers
            ],
            "unverified_gaps": list(updated_board.gaps_and_blockers.unverified_gaps),
        },
        "continuation": {
            "next_prompt_hint": updated_board.continuation.next_prompt_hint,
            "last_completed_turn_id": updated_board.continuation.last_completed_turn_id,
        },
        "evidence_refs": list(updated_board.evidence_refs),
        "learning_plan": {
            "goal": updated_board.learning_plan.goal,
            "plan_nodes": [
                {
                    "id": n.id,
                    "label": n.label,
                    "status": n.status,
                    "depth": n.depth,
                    "summary": n.summary,
                }
                for n in updated_board.learning_plan.plan_nodes
            ],
            "current_node_id": updated_board.learning_plan.current_node_id,
            "review_queue": list(updated_board.learning_plan.review_queue),
            "pending_checks": list(updated_board.learning_plan.pending_checks),
        },
        "learning_board": {
            "current_progress": updated_board.learning_board.current_progress,
            "completed_nodes": list(updated_board.learning_board.completed_nodes),
            "blockers": list(updated_board.learning_board.blockers),
            "objections": list(updated_board.learning_board.objections),
            "evidence_refs": list(updated_board.learning_board.evidence_refs),
            "continuation": updated_board.learning_board.continuation,
        },
        "check_mode_turns": updated_board.check_mode_turns,
    }
    touch_session(session)
    session_store.save_session(session)

    # Broadcast session update to trigger frontend refresh
    # (WS broadcast would go here if ws_handler is accessible)

    return {"board_version": updated_board.board_version, "status": "applied"}
