from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from colearn.memory.store import EventMemoryStore, MemoryEvent
from colearn.projects.service import LearningProjectService
from colearn.sessions.store import SessionStore
from colearn.storage import JsonStateStore


def test_mcp_server_readonly_tools(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    import colearn.mcp_server as mcp_server

    state_root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(state_root))
    project = project_service.create_project("proj-mcp", "MCP Project")
    session_store = SessionStore(state_store=JsonStateStore(state_root))
    session_store.create_session(session_id="sess-mcp", project_id="proj-mcp")
    memory_store = EventMemoryStore(state_store=JsonStateStore(state_root))
    memory_store.append(
        MemoryEvent(
            event_id="evt-mcp",
            kind="review_written",
            payload={"session_id": "sess-mcp", "project_id": "proj-mcp", "summary": "matrix fact"},
        )
    )

    class FakeRetrievalService:
        def build_bundle(self, *, project, session, query: str, libraries=None):
            _ = (project, session, libraries)
            return SimpleNamespace(
                query=query,
                text="retrieved context",
                references=[{"source_ref": "note.md"}],
                chunks=[],
                warnings=[],
                retrieval_status="ready",
                fallback_reason="",
                metadata={},
            )

    monkeypatch.setattr(mcp_server, "_retrieval_service", lambda: FakeRetrievalService())

    assert mcp_server.list_projects()["count"] == 1
    assert mcp_server.get_project("proj-mcp")["project"]["title"] == "MCP Project"
    assert mcp_server.list_sessions(project_id="proj-mcp")["count"] == 1
    assert mcp_server.search_memory("matrix")["events"][0]["event_id"] == "evt-mcp"
    retrieved = mcp_server.retrieve_project_context("proj-mcp", "matrix", session_id="sess-mcp")
    assert retrieved["retrieval_status"] == "ready"
    assert retrieved["text"] == "retrieved context"
