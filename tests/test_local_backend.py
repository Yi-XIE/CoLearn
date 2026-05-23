"""Tests for LocalLightRAGBackend — keyword-scored in-process retrieval."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from colearn.retrieval.adapters.local_backend import LocalLightRAGBackend


def _write(p: Path, body: str) -> str:
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_initialize_and_search_returns_relevant_chunks():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = _write(root / "a.md", "Photosynthesis converts sunlight into glucose.\n\nMitochondria produce ATP.")
        b = _write(root / "b.md", "Transformers use self-attention. The query, key, value mechanism is core.")

        backend = LocalLightRAGBackend()
        init = asyncio.run(backend.initialize("kb1", [a, b]))
        assert init["status"] == "synced"
        assert sorted(init["indexed_paths"]) == sorted([a, b])

        out = asyncio.run(backend.search(query="self-attention transformers", kb_name="kb1", top_k=3))
        chunks = out["chunks"]
        assert len(chunks) >= 1
        assert "self-attention" in chunks[0]["text"].lower()
        assert chunks[0]["source"] == b


def test_search_scope_filter_by_file_paths():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a = _write(root / "a.md", "machine learning is awesome")
        b = _write(root / "b.md", "machine learning fundamentals")

        backend = LocalLightRAGBackend()
        asyncio.run(backend.initialize("kb1", [a, b]))

        out = asyncio.run(backend.search(query="machine learning", kb_name="kb1", file_paths=[a]))
        assert all(ch["source"] == a for ch in out["chunks"])


def test_search_no_match_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        a = _write(Path(tmp) / "a.md", "hello world")
        backend = LocalLightRAGBackend()
        asyncio.run(backend.initialize("kb1", [a]))

        out = asyncio.run(backend.search(query="完全不相关的查询zzzqqq", kb_name="kb1"))
        assert out["chunks"] == []


def test_chinese_tokenization():
    with tempfile.TemporaryDirectory() as tmp:
        a = _write(Path(tmp) / "zh.md", "监督学习是机器学习的一种范式。\n\n强化学习靠奖励信号学习。")
        backend = LocalLightRAGBackend()
        asyncio.run(backend.initialize("kb1", [a]))

        out = asyncio.run(backend.search(query="监督", kb_name="kb1", top_k=2))
        assert len(out["chunks"]) >= 1
        assert "监督" in out["chunks"][0]["text"]


def test_missing_file_skipped_not_crashed():
    backend = LocalLightRAGBackend()
    init = asyncio.run(backend.initialize("kb1", ["/nonexistent/path.md"]))
    assert init["indexed_paths"] == []
