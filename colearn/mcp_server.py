"""Read-only MCP tools for the local CoLearn workspace."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP

from colearn.memory.store import EventMemoryStore
from colearn.paths import colearn_repo_root, colearn_state_root
from colearn.projects.models import LearningProject
from colearn.projects.service import LearningProjectService
from colearn.retrieval.service import RetrievalService
from colearn.sessions.store import LearningSession, SessionStore
from colearn.storage import JsonStateStore
from colearn.storage.records import memory_event_to_record, project_to_record, session_to_record


mcp = FastMCP("colearn-ext")


def _state_store() -> JsonStateStore:
    return JsonStateStore(colearn_state_root())


def _project_service() -> LearningProjectService:
    return LearningProjectService(state_store=_state_store())


def _session_store() -> SessionStore:
    return SessionStore(state_store=_state_store())


def _memory_store() -> EventMemoryStore:
    return EventMemoryStore(state_store=_state_store())


def _retrieval_service() -> RetrievalService:
    return RetrievalService(workspace=colearn_repo_root())


def _session_payload(session: LearningSession) -> dict[str, Any]:
    return session_to_record(session)


def _project_payload(project: LearningProject) -> dict[str, Any]:
    return project_to_record(project)


def _bundle_payload(bundle) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = []
    for chunk in list(getattr(bundle, "chunks", []) or []):
        if is_dataclass(chunk):
            chunks.append(asdict(chunk))
        else:
            chunks.append(dict(chunk))
    return {
        "query": str(getattr(bundle, "query", "") or ""),
        "text": str(getattr(bundle, "text", "") or ""),
        "references": list(getattr(bundle, "references", []) or []),
        "chunks": chunks,
        "warnings": list(getattr(bundle, "warnings", []) or []),
        "retrieval_status": str(getattr(bundle, "retrieval_status", "") or ""),
        "fallback_reason": str(getattr(bundle, "fallback_reason", "") or ""),
        "metadata": dict(getattr(bundle, "metadata", {}) or {}),
    }


def list_projects() -> dict[str, Any]:
    """List local CoLearn projects."""
    projects = [_project_payload(project) for project in _project_service().list_projects()]
    return {"projects": projects, "count": len(projects)}


def get_project(project_id: str) -> dict[str, Any]:
    """Return one local CoLearn project by id."""
    project = _project_service().get_project(project_id)
    return {"project": _project_payload(project) if project else None}


def list_sessions(project_id: str = "") -> dict[str, Any]:
    """List local CoLearn sessions, optionally filtered by project id."""
    sessions = [
        _session_payload(session)
        for session in _session_store().list_sessions()
        if not project_id or session.project_id == project_id
    ]
    return {"sessions": sessions, "count": len(sessions)}


def search_memory(query: str, session_id: str = "", project_id: str = "", limit: int = 5) -> dict[str, Any]:
    """Search CoLearn event memory."""
    events = _memory_store().search_events(
        query=query,
        session_id=session_id,
        project_id=project_id,
        limit=max(1, min(int(limit or 5), 20)),
    )
    return {"events": [memory_event_to_record(event) for event in events], "count": len(events)}


def retrieve_project_context(
    project_id: str,
    query: str,
    session_id: str = "",
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Retrieve read-only project context through CoLearn's retrieval service."""
    project = _project_service().get_project(project_id)
    if project is None:
        return {"error": "project_not_found", "project_id": project_id}
    session = _session_store().get_session(session_id) if session_id else None
    if session is None:
        session = LearningSession(
            session_id=session_id or "mcp-readonly",
            project_id=project_id,
            source_refs=list(source_refs or project.source_subset or project.source_refs),
        )
    elif source_refs is not None:
        session = LearningSession(
            **{
                **session.__dict__,
                "source_refs": list(source_refs),
            }
        )
    bundle = _retrieval_service().build_bundle(project=project, session=session, query=query, libraries=None)
    return _bundle_payload(bundle)


mcp.tool()(list_projects)
mcp.tool()(get_project)
mcp.tool()(list_sessions)
mcp.tool()(search_memory)
mcp.tool()(retrieve_project_context)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
