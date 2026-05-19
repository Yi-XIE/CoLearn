"""Tests for RetrievalService bundle building and source resolution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
import pytest

from colearn.learning.retrieval_bundle import RetrievalBundle
from colearn.projects.models import LearningProject
from colearn.retrieval.service import RetrievalService
from colearn.sessions.store import LearningSession


@dataclass
class _FakeRetrievalResult:
    query: str = ""
    text: str = ""
    references: list[dict[str, Any]] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    retrieval_status: str = "unavailable"
    fallback_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class _FakeLightRAGClient:
    def __init__(self, *, ready_result: _FakeRetrievalResult | None = None, async_supported: bool = True):
        self.ready_result = ready_result or _FakeRetrievalResult()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._async_supported = async_supported

    def retrieve_project_context(self, *, project_id, query, source_refs, top_k=5):
        self.calls.append(("retrieve_project_context", {"project_id": project_id, "query": query, "source_refs": list(source_refs), "top_k": top_k}))
        return self.ready_result

    def sync_project_sources(self, project_id, normalized_refs):
        self.calls.append(("sync_project_sources", {"project_id": project_id, "refs": list(normalized_refs)}))
        return {"synced": True, "source_count": len(normalized_refs)}

    if True:  # placeholder so we can conditionally add async method below
        pass


class _AsyncLightRAGClient(_FakeLightRAGClient):
    async def async_retrieve_project_context(self, *, project_id, query, source_refs, top_k=5):
        self.calls.append(("async_retrieve_project_context", {"project_id": project_id, "query": query, "source_refs": list(source_refs)}))
        return self.ready_result


def _make_project(**kwargs) -> LearningProject:
    defaults = {"project_id": "p1", "title": "T"}
    defaults.update(kwargs)
    return LearningProject(**defaults)


def _make_session(**kwargs) -> LearningSession:
    defaults = {"session_id": "s1", "project_id": "p1"}
    defaults.update(kwargs)
    return LearningSession(**defaults)


def test_build_bundle_with_lightrag_ready_returns_chunks(tmp_path: Path):
    client = _FakeLightRAGClient(
        ready_result=_FakeRetrievalResult(
            query="q",
            text="ready text",
            references=[{"source_ref": "a.md"}],
            chunks=[{"text": "chunk-text", "reference": {"source_ref": "a.md"}, "source": "a.md", "score": 0.8}],
            retrieval_status="ready",
        )
    )
    service = RetrievalService(lightrag_client=client)
    bundle = service.build_bundle(
        project=_make_project(source_refs=["a.md"]),
        session=_make_session(),
        query="q",
    )
    assert isinstance(bundle, RetrievalBundle)
    assert bundle.retrieval_status == "ready"
    assert bundle.text == "ready text"
    assert len(bundle.chunks) == 1
    assert bundle.chunks[0].text == "chunk-text"
    assert bundle.chunks[0].score == 0.8


def test_build_bundle_no_source_refs_returns_empty():
    client = _FakeLightRAGClient()
    service = RetrievalService(lightrag_client=client)
    bundle = service.build_bundle(
        project=_make_project(source_refs=[]),
        session=_make_session(),
        query="anything",
    )
    assert bundle.retrieval_status == "empty"
    assert bundle.fallback_reason == "no_source_refs"
    assert "No project sources" in bundle.warnings[0]


def test_build_bundle_falls_back_to_file_preview(tmp_path: Path):
    file_path = tmp_path / "note.md"
    file_path.write_text("Some preview text for the bundle.", encoding="utf-8")

    client = _FakeLightRAGClient(
        ready_result=_FakeRetrievalResult(retrieval_status="empty", fallback_reason="no_lightrag_hits"),
    )
    service = RetrievalService(lightrag_client=client)
    bundle = service.build_bundle_for_source_refs(
        project_id="p1",
        query="what",
        source_refs=[str(file_path)],
    )
    assert bundle.retrieval_status == "ready"
    assert "Some preview text" in bundle.text
    assert bundle.metadata["fallback_from_lightrag"] == "empty"


def test_build_bundle_missing_source_files_warns(tmp_path: Path):
    client = _FakeLightRAGClient(
        ready_result=_FakeRetrievalResult(retrieval_status="empty"),
    )
    service = RetrievalService(lightrag_client=client)
    bundle = service.build_bundle_for_source_refs(
        project_id="p1",
        query="q",
        source_refs=[str(tmp_path / "does_not_exist.md")],
    )
    assert bundle.retrieval_status == "error"
    assert any("Missing source" in w for w in bundle.warnings)


def test_async_build_bundle_with_async_client(tmp_path: Path):
    client = _AsyncLightRAGClient(
        ready_result=_FakeRetrievalResult(
            text="async ready",
            retrieval_status="ready",
        )
    )
    service = RetrievalService(lightrag_client=client)

    async def run():
        return await service.async_build_bundle_for_source_refs(
            project_id="p1",
            query="q",
            source_refs=["a.md"],
        )

    bundle = anyio.run(run)
    assert bundle.retrieval_status == "ready"
    assert bundle.text == "async ready"
    assert client.calls[0][0] == "async_retrieve_project_context"


def test_async_build_bundle_without_async_client_uses_to_thread(tmp_path: Path):
    client = _FakeLightRAGClient(
        ready_result=_FakeRetrievalResult(
            text="sync via thread",
            retrieval_status="ready",
        )
    )
    service = RetrievalService(lightrag_client=client)

    async def run():
        return await service.async_build_bundle_for_source_refs(
            project_id="p1",
            query="q",
            source_refs=["a.md"],
        )

    bundle = anyio.run(run)
    assert bundle.text == "sync via thread"
    assert client.calls[0][0] == "retrieve_project_context"


def test_async_build_bundle_no_source_refs_short_circuits():
    client = _FakeLightRAGClient()
    service = RetrievalService(lightrag_client=client)

    async def run():
        return await service.async_build_bundle_for_source_refs(
            project_id="p1",
            query="q",
            source_refs=[],
        )

    bundle = anyio.run(run)
    assert bundle.retrieval_status == "empty"
    assert client.calls == []


def test_normalize_source_refs_resolves_existing_paths(tmp_path: Path):
    real = tmp_path / "real.md"
    real.write_text("hi", encoding="utf-8")

    client = _FakeLightRAGClient()
    service = RetrievalService(lightrag_client=client)
    refs = service._normalize_source_refs([str(real), "missing.md"], libraries=[])
    assert refs[0]["source_path"] == str(real.resolve())
    assert refs[0]["title"] == "real.md"
    assert "source_path" not in refs[1]
    assert refs[1]["title"] == "missing.md"


def test_require_lightrag_client_raises_when_unavailable():
    service = RetrievalService(lightrag_client=None)
    service._lightrag_client = None
    service._lightrag_error = None
    with pytest.raises(RuntimeError, match="LightRAG client is unavailable"):
        service._require_lightrag_client()
