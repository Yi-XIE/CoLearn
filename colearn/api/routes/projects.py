"""Project routes."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from colearn.api.dependencies import project_service, session_store
from colearn.api.schemas import ProjectCreatePayload, ProjectUpdatePayload, ProjectSourcesPayload, ProjectAnchorPayload
from colearn.projects.models import LearningProject

router = APIRouter()


def _serialize_project(project: LearningProject) -> dict[str, Any]:
    source_refs = list(project.source_refs or [])
    memory_refs = list(project.memory_refs or [])
    board_facts = dict(project.board_facts or {})
    latest_review = dict(project.latest_review or {})
    latest_review_status = str(latest_review.get("status") or ("ready" if latest_review.get("summary") else "empty"))
    source_count = len(source_refs)
    session_count = len([item for item in session_store.list_sessions() if item.project_id == project.project_id])
    return {
        "project_id": project.project_id,
        "slug": project.project_id,
        "title": project.title,
        "goal": project.goal,
        "status": "active",
        "created_at": "",
        "updated_at": "",
        "last_active_at": "",
        "source_count": source_count,
        "session_count": session_count,
        "memory_ref_count": len(memory_refs),
        "turn_mode": project.turn_mode,
        "board_facts": board_facts,
        "board_version": int(project.board_version or 1),
        "board_updated_at": str(board_facts.get("updated_at") or ""),
        "latest_review_status": latest_review_status,
        "latest_review": latest_review,
        "source_refs": source_refs,
        "source_references": [],
        "memory_refs": memory_refs,
        "anchor": dict(project.anchor) if project.anchor else None,
    }


@router.get("/api/v1/projects")
def list_projects() -> dict[str, Any]:
    projects = []
    for project in project_service.list_projects():
        projects.append(_serialize_project(project))
    return {"projects": projects}


@router.post("/api/v1/projects")
def create_project(payload: ProjectCreatePayload) -> dict[str, Any]:
    project_id = payload.slug.strip() or str(uuid4())
    project = project_service.create_project(project_id, title=payload.title, goal=payload.goal)
    return {"project": _serialize_project(project)}


@router.get("/api/v1/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    project = project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": _serialize_project(project)}


@router.patch("/api/v1/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdatePayload) -> dict[str, Any]:
    project = project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.title is not None:
        project.title = payload.title
    if payload.goal is not None:
        project.goal = payload.goal
    if payload.source_refs is not None:
        project.source_refs = list(payload.source_refs)
    project_service.save_project(project)
    return {"project": _serialize_project(project)}


@router.put("/api/v1/projects/{project_id}/sources")
def save_project_sources(project_id: str, payload: ProjectSourcesPayload) -> dict[str, Any]:
    project = project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.source_refs = list(payload.source_refs)
    project.source_subset = list(payload.source_refs)
    project_service.save_project(project)
    return {
        "project": _serialize_project(project),
        "source_refs": list(project.source_refs),
        "source_references": list(payload.source_references),
    }


@router.post("/api/v1/projects/{project_id}/anchor")
def save_project_anchor(project_id: str, payload: ProjectAnchorPayload) -> dict[str, Any]:
    project = project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.anchor = {
        "topic": payload.topic,
        "source_refs": list(payload.source_refs),
        "prior_knowledge": payload.prior_knowledge,
        "target_depth": payload.target_depth,
        "preferred_method": payload.preferred_method,
    }
    project.anchor_status = "ready"
    if payload.source_refs:
        project.source_refs = list(payload.source_refs)
    project_service.save_project(project)
    return {"project": _serialize_project(project), "anchor": dict(project.anchor)}


@router.get("/api/v1/projects/{project_id}/latest-review")
def get_latest_project_review(project_id: str) -> dict[str, Any]:
    project = project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    latest = project.latest_review or None
    review_payload = None
    if latest:
        review_payload = {
            "project_id": project.project_id,
            "project_slug": project.project_id,
            "project_title": project.title,
            "session_id": "",
            "timestamp": "",
            "review_path": "",
            "review_summary": str(latest.get("summary") or ""),
            "mastery_points": list(latest.get("points") or []),
            "confusion_points": list(latest.get("confusion_points") or []),
            "next_steps": [],
            "understanding_alignment": {
                "learner_claim": "",
                "target_concept": "",
                "gap": "",
            },
            "references": [],
        }
    return {"project": _serialize_project(project), "latest_review": review_payload}