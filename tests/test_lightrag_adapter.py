from __future__ import annotations

from pathlib import Path
import sys

import anyio
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from colearn.retrieval.adapters.lightrag import (  # noqa: E402
    HttpLightRAGBackend,
    LightRAGClient,
    LightRAGConfig,
    LightRAGConfigurationError,
    LightRAGRetrievalResult,
    get_lightrag_client,
)
from colearn.retrieval.service import RetrievalService  # noqa: E402
from colearn.projects.service import LearningProjectService  # noqa: E402
from colearn.sessions.store import SessionStore  # noqa: E402


class FakeBackend:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.calls: list[tuple[str, object]] = []

    async def initialize(self, kb_name: str, file_paths: list[str], **kwargs):
        self.calls.append(("initialize", (kb_name, tuple(file_paths), dict(kwargs))))
        return True

    async def delete(self, kb_name: str):
        self.calls.append(("delete", kb_name))
        return True

    async def search(self, **kwargs):
        self.calls.append(("search", dict(kwargs)))
        return {
            "chunks": [
                {
                    "source": str(self.tmp_path / "note.md"),
                    "text": "Project chunk",
                    "score": 0.9,
                },
                {
                    "source": str(self.tmp_path / "other.md"),
                    "text": "Other chunk",
                    "score": 0.1,
                },
            ]
        }


def test_get_lightrag_client_requires_enabled_config(tmp_path: Path) -> None:
    with pytest.raises(LightRAGConfigurationError, match="LightRAG is required"):
        get_lightrag_client(workspace=tmp_path)


def test_get_lightrag_client_builds_http_backend_from_config(tmp_path: Path) -> None:
    config_path = tmp_path / ".colearn" / "lightrag.json"
    LightRAGConfig(enabled=True, provider="server", base_url="http://127.0.0.1:9621").save(config_path)
    client = get_lightrag_client(workspace=tmp_path, path=config_path)
    assert isinstance(client, LightRAGClient)
    assert isinstance(client._backend, HttpLightRAGBackend)


def test_lightrag_client_sync_and_retrieve_subset(tmp_path: Path) -> None:
    config_path = tmp_path / ".colearn" / "lightrag.json"
    LightRAGConfig(enabled=True).save(config_path)
    source_file = tmp_path / "note.md"
    source_file.write_text("hello", encoding="utf-8")
    (tmp_path / "other.md").write_text("other", encoding="utf-8")
    backend = FakeBackend(tmp_path)
    client = LightRAGClient(
        config=LightRAGConfig(enabled=True),
        path=config_path,
        workspace=tmp_path,
        backend=backend,
    )
    sync_result = client.sync_project_sources(
        "project-1",
        [{"source_id": str(source_file), "source_path": str(source_file), "title": "note.md"}],
    )
    assert sync_result["synced"] is True

    result = client.retrieve_project_context(
        project_id="project-1",
        query="fractions",
        source_refs=[{"source_id": str(source_file), "source_path": str(source_file), "title": "note.md"}],
    )
    assert isinstance(result, LightRAGRetrievalResult)
    assert result.retrieval_status == "ready"
    assert result.text == "Project chunk"
    assert len(result.references or []) == 1
    assert backend.calls[0][0] == "initialize"
    assert any(call[0] == "search" for call in backend.calls)


async def _run_lightrag_async_checks(tmp_path: Path) -> None:
    config_path = tmp_path / ".colearn" / "lightrag.json"
    LightRAGConfig(enabled=True).save(config_path)
    source_file = tmp_path / "note.md"
    source_file.write_text("hello", encoding="utf-8")
    backend = FakeBackend(tmp_path)
    client = LightRAGClient(
        config=LightRAGConfig(enabled=True),
        path=config_path,
        workspace=tmp_path,
        backend=backend,
    )
    result = await client.async_retrieve_project_context(
        project_id="project-async",
        query="fractions",
        source_refs=[{"source_id": str(source_file), "source_path": str(source_file), "title": "note.md"}],
    )
    assert result.retrieval_status == "ready"
    with pytest.raises(RuntimeError, match="async_retrieve_project_context"):
        client.retrieve_project_context(
            project_id="project-async",
            query="fractions",
            source_refs=[{"source_id": str(source_file), "source_path": str(source_file), "title": "note.md"}],
        )


def test_lightrag_async_methods_work_and_sync_rejects_event_loop(tmp_path: Path) -> None:
    anyio.run(_run_lightrag_async_checks, tmp_path)


def test_retrieval_service_uses_lightrag_adapter_when_available(tmp_path: Path) -> None:
    config_path = tmp_path / ".colearn" / "lightrag.json"
    LightRAGConfig(enabled=True).save(config_path)
    source_file = tmp_path / "note.md"
    source_file.write_text("hello", encoding="utf-8")
    backend = FakeBackend(tmp_path)
    client = LightRAGClient(
        config=LightRAGConfig(enabled=True),
        path=config_path,
        workspace=tmp_path,
        backend=backend,
    )
    retrieval_service = RetrievalService(
        workspace=tmp_path,
        lightrag_client=client,
    )
    project_service = LearningProjectService()
    project = project_service.create_project("proj-1", "Topic")
    project.anchor = {"topic": "fractions"}
    project.source_refs = [str(source_file)]
    session_store = SessionStore()
    session = session_store.create_session(session_id="sess-1", project_id="proj-1")
    session.source_refs = [str(source_file)]

    bundle = retrieval_service.build_bundle(
        project=project,
        session=session,
        query="fractions",
    )
    assert bundle.retrieval_status == "ready"
    assert bundle.text == "Project chunk"


def test_retrieval_service_build_bundle_for_source_refs(tmp_path: Path) -> None:
    config_path = tmp_path / ".colearn" / "lightrag.json"
    LightRAGConfig(enabled=True).save(config_path)
    source_file = tmp_path / "note.md"
    source_file.write_text("hello", encoding="utf-8")
    backend = FakeBackend(tmp_path)
    client = LightRAGClient(
        config=LightRAGConfig(enabled=True),
        path=config_path,
        workspace=tmp_path,
        backend=backend,
    )
    retrieval_service = RetrievalService(
        workspace=tmp_path,
        lightrag_client=client,
    )
    bundle = retrieval_service.build_bundle_for_source_refs(
        project_id="proj-1",
        query="fractions",
        source_refs=[str(source_file)],
    )
    assert bundle.retrieval_status == "ready"
    assert bundle.text == "Project chunk"


def test_lightrag_client_gracefully_reports_search_failure(tmp_path: Path) -> None:
    class FailingBackend(FakeBackend):
        async def search(self, **kwargs):
            raise RuntimeError("backend down")

    config_path = tmp_path / ".colearn" / "lightrag.json"
    LightRAGConfig(enabled=True).save(config_path)
    source_file = tmp_path / "note.md"
    source_file.write_text("hello", encoding="utf-8")
    client = LightRAGClient(
        config=LightRAGConfig(enabled=True),
        path=config_path,
        workspace=tmp_path,
        backend=FailingBackend(tmp_path),
    )
    result = client.retrieve_project_context(
        project_id="project-1",
        query="fractions",
        source_refs=[{"source_id": str(source_file), "source_path": str(source_file), "title": "note.md"}],
    )
    assert result.retrieval_status == "unavailable"
    assert result.fallback_reason == "lightrag_search_failed"
