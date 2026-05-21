"""Tests for colearn.retrieval.cache — LRU + TTL retrieval cache."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any

from colearn.retrieval.cache import RetrievalCache
from colearn.retrieval.service import RetrievalService


def test_cache_hit_and_miss():
    cache = RetrievalCache(max_entries=10, ttl_seconds=60)
    cache.put(project_id="p1", query="what is X", source_refs=["a.md"], value="result-1")

    assert cache.get(project_id="p1", query="what is X", source_refs=["a.md"]) == "result-1"
    assert cache.get(project_id="p1", query="what is Y", source_refs=["a.md"]) is None
    assert cache.stats["hits"] == 1
    assert cache.stats["misses"] == 1


def test_cache_ttl_expiry():
    cache = RetrievalCache(max_entries=10, ttl_seconds=1)
    cache.put(project_id="p1", query="q", source_refs=["a"], value="val")

    assert cache.get(project_id="p1", query="q", source_refs=["a"]) == "val"
    time.sleep(1.1)
    assert cache.get(project_id="p1", query="q", source_refs=["a"]) is None


def test_cache_lru_eviction():
    cache = RetrievalCache(max_entries=3, ttl_seconds=60)
    cache.put(project_id="p1", query="q1", source_refs=["a"], value="v1")
    cache.put(project_id="p1", query="q2", source_refs=["a"], value="v2")
    cache.put(project_id="p1", query="q3", source_refs=["a"], value="v3")
    cache.put(project_id="p1", query="q4", source_refs=["a"], value="v4")

    assert cache.get(project_id="p1", query="q1", source_refs=["a"]) is None
    assert cache.get(project_id="p1", query="q4", source_refs=["a"]) == "v4"
    assert cache.stats["size"] == 3


def test_cache_invalidate_project():
    cache = RetrievalCache(max_entries=10, ttl_seconds=60)
    cache.put(project_id="p1", query="q1", source_refs=["a"], value="v1")
    cache.put(project_id="p2", query="q1", source_refs=["a"], value="v2")

    removed = cache.invalidate_project("p1")
    assert removed == 1
    assert cache.get(project_id="p1", query="q1", source_refs=["a"]) is None
    assert cache.get(project_id="p2", query="q1", source_refs=["a"]) == "v2"


def test_cache_source_refs_order_independent():
    cache = RetrievalCache(max_entries=10, ttl_seconds=60)
    cache.put(project_id="p1", query="q", source_refs=["b.md", "a.md"], value="val")

    assert cache.get(project_id="p1", query="q", source_refs=["a.md", "b.md"]) == "val"


# --- integration with RetrievalService -----------------------------------


def _ready_result():
    return SimpleNamespace(
        query="q",
        text="hit",
        references=[{"source_ref": "a.md"}],
        chunks=[{"text": "ck", "reference": {"source_ref": "a.md"}, "source": "a.md", "score": 0.9}],
        warnings=[],
        retrieval_status="ready",
        fallback_reason=None,
        metadata={},
    )


class _CountingLightRAG:
    def __init__(self):
        self.calls = 0
        self.async_calls = 0

    def retrieve_project_context(self, *, project_id, query, source_refs, top_k=5):
        self.calls += 1
        return _ready_result()

    async def async_retrieve_project_context(self, *, project_id, query, source_refs, top_k=5):
        self.async_calls += 1
        return _ready_result()

    def sync_project_sources(self, project_id, normalized_refs):
        return {"synced": True, "source_count": len(normalized_refs)}


def test_service_caches_repeated_sync_query():
    client = _CountingLightRAG()
    service = RetrievalService(lightrag_client=client)
    service.build_bundle_for_source_refs(project_id="p1", query="q", source_refs=["a.md"])
    service.build_bundle_for_source_refs(project_id="p1", query="q", source_refs=["a.md"])
    service.build_bundle_for_source_refs(project_id="p1", query="q", source_refs=["a.md"])
    assert client.calls == 1
    assert service._cache.stats["hits"] == 2
    assert service._cache.stats["misses"] == 1


def test_service_caches_repeated_async_query():
    client = _CountingLightRAG()
    service = RetrievalService(lightrag_client=client)

    async def driver():
        await service.async_build_bundle_for_source_refs(project_id="p1", query="q", source_refs=["a.md"])
        await service.async_build_bundle_for_source_refs(project_id="p1", query="q", source_refs=["a.md"])

    asyncio.run(driver())
    assert client.async_calls == 1
    assert service._cache.stats["hits"] == 1


def test_service_invalidates_cache_on_sync():
    client = _CountingLightRAG()
    service = RetrievalService(lightrag_client=client)
    service.build_bundle_for_source_refs(project_id="p1", query="q", source_refs=["a.md"])
    service.sync_source_refs(project_id="p1", source_refs=["a.md"])
    service.build_bundle_for_source_refs(project_id="p1", query="q", source_refs=["a.md"])
    assert client.calls == 2  # cache cleared after sync, second call hits backend
