"""Local in-process LightRAG backend — no external service required.

Implements `LightRAGBackendProtocol` using simple keyword/TF scoring.
Useful for: local dev, integration tests, environments without LightRAG server.
NOT a replacement for production LightRAG (no embeddings, no graph) — this is
a baseline that keeps the retrieval pipeline live so callers can be exercised.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from colearn.logging_config import get_logger

logger = get_logger(__name__)


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-鿿]")
_CHUNK_TARGET_CHARS = 600
_CHUNK_OVERLAP_CHARS = 80


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _chunk_text(text: str, *, target: int = _CHUNK_TARGET_CHARS, overlap: int = _CHUNK_OVERLAP_CHARS) -> list[str]:
    """Split on paragraph boundaries, then pack to ~target chars with small overlap."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 <= target or not buf:
            buf = f"{buf}\n\n{para}".strip() if buf else para
        else:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap and len(buf) > overlap else ""
            buf = f"{tail}\n\n{para}".strip() if tail else para
    if buf:
        chunks.append(buf)
    return chunks


@dataclass
class _IndexedChunk:
    chunk_id: str
    source: str
    text: str
    tokens: Counter[str] = field(default_factory=Counter)


class LocalLightRAGBackend:
    """In-memory keyword-scored backend, file-system source of truth.

    Compatible with `LightRAGBackendProtocol`: initialize / search / delete.
    """

    def __init__(self) -> None:
        self._kbs: dict[str, dict[str, list[_IndexedChunk]]] = {}

    async def initialize(self, kb_name: str, file_paths: list[str], **_: Any) -> dict[str, Any]:
        kb = self._kbs.setdefault(kb_name, {})
        indexed: list[str] = []
        for raw in file_paths:
            path = Path(raw)
            if not path.exists() or not path.is_file():
                logger.warning("LocalLightRAGBackend: missing path %s", raw)
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                logger.warning("LocalLightRAGBackend: read failed %s: %s", raw, exc)
                continue
            chunks: list[_IndexedChunk] = []
            for i, body in enumerate(_chunk_text(text)):
                tokens = Counter(_tokenize(body))
                chunks.append(
                    _IndexedChunk(
                        chunk_id=f"{path.name}::{i}",
                        source=str(path),
                        text=body,
                        tokens=tokens,
                    )
                )
            kb[str(path)] = chunks
            indexed.append(str(path))
        return {"status": "synced", "track_id": "", "indexed_paths": indexed}

    async def search(
        self,
        *,
        query: str,
        kb_name: str,
        top_k: int = 5,
        file_paths: list[str] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        kb = self._kbs.get(kb_name) or {}
        scope = file_paths or list(kb.keys())
        q_tokens = Counter(_tokenize(query))
        if not q_tokens:
            return {"chunks": []}
        scored: list[tuple[float, _IndexedChunk]] = []
        for path in scope:
            for chunk in kb.get(path) or []:
                score = sum(chunk.tokens.get(tok, 0) * cnt for tok, cnt in q_tokens.items())
                if score > 0:
                    norm = score / (sum(chunk.tokens.values()) ** 0.5 or 1.0)
                    scored.append((norm, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, chunk in scored[: max(top_k, 1)]:
            out.append(
                {
                    "text": chunk.text,
                    "source": chunk.source,
                    "source_path": chunk.source,
                    "chunk_id": chunk.chunk_id,
                    "score": float(round(score, 4)),
                }
            )
        return {"chunks": out}

    async def delete(self, kb_name: str) -> dict[str, Any]:
        self._kbs.pop(kb_name, None)
        return {"status": "deleted"}
