"""LRU + TTL cache for retrieval results."""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from colearn.config.defaults import Defaults
from colearn.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class _CacheKey:
    project_id: str
    query_hash: str
    source_refs_hash: str


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class RetrievalCache:
    """In-memory LRU cache with TTL for retrieval results."""

    def __init__(
        self,
        *,
        max_entries: int | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self._max_entries = max_entries or Defaults.RETRIEVAL_CACHE_MAX_ENTRIES
        self._ttl = ttl_seconds or Defaults.RETRIEVAL_CACHE_TTL_SECONDS
        self._store: OrderedDict[_CacheKey, _CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(
        self,
        *,
        project_id: str,
        query: str,
        source_refs: list[str],
    ) -> Any | None:
        key = self._make_key(project_id, query, source_refs)
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        if time.time() > entry.expires_at:
            del self._store[key]
            self._misses += 1
            return None
        self._store.move_to_end(key)
        self._hits += 1
        return entry.value

    def put(
        self,
        *,
        project_id: str,
        query: str,
        source_refs: list[str],
        value: Any,
    ) -> None:
        key = self._make_key(project_id, query, source_refs)
        self._store[key] = _CacheEntry(
            value=value,
            expires_at=time.time() + self._ttl,
        )
        self._store.move_to_end(key)
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def invalidate_project(self, project_id: str) -> int:
        """Remove all entries for a given project. Returns count removed."""
        keys_to_remove = [k for k in self._store if k.project_id == project_id]
        for k in keys_to_remove:
            del self._store[k]
        return len(keys_to_remove)

    def clear(self) -> None:
        self._store.clear()

    @property
    def stats(self) -> dict[str, int]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": int(self._hits * 100 / total) if total > 0 else 0,
            "size": len(self._store),
        }

    def _make_key(self, project_id: str, query: str, source_refs: list[str]) -> _CacheKey:
        query_hash = hashlib.md5(query.encode(), usedforsecurity=False).hexdigest()[:12]
        refs_str = "|".join(sorted(source_refs))
        refs_hash = hashlib.md5(refs_str.encode(), usedforsecurity=False).hexdigest()[:12]
        return _CacheKey(project_id=project_id, query_hash=query_hash, source_refs_hash=refs_hash)
