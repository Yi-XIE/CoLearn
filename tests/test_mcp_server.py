from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from colearn.memory.store import EventMemoryStore, MemoryEvent
from colearn.projects.service import LearningProjectService
from colearn.sessions.store import SessionStore
from colearn.storage import JsonStateStore


def test_mcp_server_readonly_tools(monkeypatch, tmp_path) -> None:
    repo_root = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    monkeypatch.setenv("COLEARN_REPO_ROOT", str(repo_root))
    monkeypatch.chdir(outside)
    import colearn.mcp_server as mcp_server

    state_root = repo_root / ".colearn" / "state"
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


def test_mcp_server_stdio_lists_readonly_tools(monkeypatch, tmp_path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    repo_root = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    monkeypatch.chdir(outside)
    python_path = str(Path(__file__).resolve().parents[1])
    existing_python_path = os.environ.get("PYTHONPATH")
    if existing_python_path:
        python_path = f"{python_path}{os.pathsep}{existing_python_path}"

    async def run_client() -> list[str]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "colearn.mcp_server"],
            env={
                **os.environ,
                "PYTHONPATH": python_path,
                "COLEARN_REPO_ROOT": str(repo_root),
            },
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return sorted(tool.name for tool in tools.tools)

    assert asyncio.run(run_client()) == [
        "get_project",
        "list_projects",
        "list_sessions",
        "retrieve_project_context",
        "search_memory",
    ]
