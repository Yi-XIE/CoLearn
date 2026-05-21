"""LightRAG (lightrag-hku) backend — real graph-augmented retrieval.

Wraps the upstream `lightrag-hku` package as a `LightRAGBackendProtocol`
implementation. LLM = DeepSeek (OpenAI-compatible), Embedding = SiliconFlow
(per the project's .env). One LightRAG instance per kb_name, persisted under
workspace/.colearn/lightrag-store/<kb_name>/.

Selected via `lightrag.json`:
    {"enabled": true, "provider": {"name": "lightrag_hku"}}
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import numpy as np

from colearn.logging_config import get_logger

logger = get_logger(__name__)

# Upstream symbols imported lazily so this module is importable without the
# heavy dependency installed (e.g. in CI environments that don't need it).
_LightRAG = None
_QueryParam = None
_EmbeddingFunc = None
_openai_complete_if_cache = None
_openai_embed = None
_initialize_pipeline_status = None


def _load_upstream() -> None:
    global _LightRAG, _QueryParam, _EmbeddingFunc
    global _openai_complete_if_cache, _openai_embed, _initialize_pipeline_status
    if _LightRAG is not None:
        return
    from lightrag import LightRAG, QueryParam
    from lightrag.kg.shared_storage import initialize_pipeline_status
    from lightrag.llm.openai import openai_complete_if_cache, openai_embed
    from lightrag.utils import EmbeddingFunc

    _LightRAG = LightRAG
    _QueryParam = QueryParam
    _EmbeddingFunc = EmbeddingFunc
    _openai_complete_if_cache = openai_complete_if_cache
    _openai_embed = openai_embed
    _initialize_pipeline_status = initialize_pipeline_status


def _make_llm_func():
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

    async def llm(prompt: str, system_prompt: str | None = None, history_messages=None, **kwargs) -> str:
        return await _openai_complete_if_cache(
            model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            api_key=api_key,
            base_url=f"{api_base.rstrip('/')}/v1",
            **kwargs,
        )

    return llm


def _make_embedding_func():
    api_key = os.environ.get("SILICONFLOW_API_KEY") or os.environ.get("EMBEDDING_API_KEY", "")
    base_url = os.environ.get("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1/embeddings").rstrip("/")
    if base_url.endswith("/embeddings"):
        base_url = base_url[: -len("/embeddings")]
    model = os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")
    dim = int(os.environ.get("EMBEDDING_DIM", "4096"))

    async def embed(texts: list[str]) -> np.ndarray:
        return await _openai_embed(
            texts,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )

    return _EmbeddingFunc(embedding_dim=dim, func=embed)


class LightRAGHKUBackend:
    """Adapter to lightrag-hku. One LightRAG instance per (kb_name, event_loop).

    LightRAG's internal PriorityQueue binds to the loop where the instance is
    first awaited; reusing across loops raises 'bound to a different event loop'.
    Cache by (kb, loop_id) so each `asyncio.run` gets a fresh-but-persistent
    instance (working_dir on disk preserves indexed state).
    """

    def __init__(self, *, working_root: Path) -> None:
        self._root = working_root
        self._root.mkdir(parents=True, exist_ok=True)
        self._instances: dict[tuple[str, int], Any] = {}
        self._indexed: dict[tuple[str, int], set[str]] = {}

    def _key(self, kb_name: str) -> tuple[str, int]:
        try:
            loop_id = id(asyncio.get_running_loop())
        except RuntimeError:
            loop_id = 0
        return (kb_name, loop_id)

    async def _get_or_create(self, kb_name: str) -> Any:
        key = self._key(kb_name)
        if key in self._instances:
            return self._instances[key]
        _load_upstream()
        kb_dir = self._root / kb_name
        kb_dir.mkdir(parents=True, exist_ok=True)
        rag = _LightRAG(
            working_dir=str(kb_dir),
            llm_model_func=_make_llm_func(),
            llm_model_name=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            embedding_func=_make_embedding_func(),
        )
        await rag.initialize_storages()
        await _initialize_pipeline_status()
        self._instances[key] = rag
        self._indexed[key] = set()
        return rag

    async def initialize(self, kb_name: str, file_paths: list[str], **_: Any) -> dict[str, Any]:
        rag = await self._get_or_create(kb_name)
        already = self._indexed.setdefault(self._key(kb_name), set())
        ingested: list[str] = []
        for raw in file_paths:
            path = Path(raw)
            if not path.exists() or not path.is_file():
                logger.warning("LightRAGHKU: missing path %s", raw)
                continue
            if str(path) in already:
                ingested.append(str(path))
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                logger.warning("LightRAGHKU: read failed %s: %s", path, exc)
                continue
            try:
                await rag.ainsert(text, ids=str(path), file_paths=str(path))
            except Exception as exc:
                logger.warning("LightRAGHKU: insert failed for %s: %s", path, exc)
                continue
            already.add(str(path))
            ingested.append(str(path))
        return {"status": "synced", "track_id": "", "indexed_paths": ingested}

    async def search(
        self,
        *,
        query: str,
        kb_name: str,
        top_k: int = 5,
        file_paths: list[str] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        rag = await self._get_or_create(kb_name)
        param = _QueryParam(
            mode="hybrid",
            chunk_top_k=max(int(top_k or 5), 5),
            only_need_context=True,
            include_references=True,
        )
        try:
            data = await rag.aquery_data(query, param=param)
        except Exception as exc:
            logger.warning("LightRAGHKU search failed: %s", exc)
            return {"chunks": [], "warning": f"search_failed:{type(exc).__name__}"}

        chunks_raw = data.get("chunks") if isinstance(data, dict) else None
        out: list[dict[str, Any]] = []
        scope = set(file_paths or [])
        for ch in chunks_raw or []:
            text = str(ch.get("content") or ch.get("text") or "").strip()
            source = str(
                ch.get("file_path") or ch.get("source_path") or ch.get("source") or ""
            ).strip()
            if not text or not source:
                continue
            if scope and source not in scope:
                continue
            out.append(
                {
                    "text": text,
                    "source": source,
                    "source_path": source,
                    "chunk_id": str(ch.get("id") or ch.get("chunk_id") or ""),
                    "score": float(ch.get("score") or 0.0),
                }
            )
            if len(out) >= top_k:
                break
        return {"chunks": out}

    async def delete(self, kb_name: str) -> dict[str, Any]:
        for key in list(self._instances.keys()):
            if key[0] == kb_name:
                rag = self._instances.pop(key, None)
                self._indexed.pop(key, None)
                if rag is not None:
                    try:
                        await rag.finalize_storages()
                    except Exception:
                        pass
        return {"status": "deleted"}
