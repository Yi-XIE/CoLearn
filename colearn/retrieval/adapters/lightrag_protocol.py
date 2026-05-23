"""LightRAG protocol definitions, constants, and shared types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from colearn.logging_config import get_logger

logger = get_logger(__name__)


DEFAULT_TOP_K = 5
DEFAULT_BASE_URL = "http://127.0.0.1:9621"


class LightRAGConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class LightRAGRetrievalResult:
    query: str = ""
    text: str = ""
    references: list[dict[str, Any]] | None = None
    chunks: list[dict[str, Any]] | None = None
    warnings: list[str] | None = None
    retrieval_status: str = "unavailable"
    fallback_reason: str = ""
    metadata: dict[str, Any] | None = None


@runtime_checkable
class LightRAGBackendProtocol(Protocol):
    async def initialize(self, kb_name: str, file_paths: list[str], **kwargs: Any) -> Any: ...

    async def delete(self, kb_name: str) -> Any: ...

    async def search(self, **kwargs: Any) -> dict[str, Any]: ...


@runtime_checkable
class LightRAGClientProtocol(Protocol):
    enabled: bool

    def reload(self, *, env: Mapping[str, str] | None = None) -> Any: ...

    def save(self) -> Path: ...

    def sync_project_sources(
        self,
        project_id: str,
        source_refs: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    async def async_sync_project_sources(
        self,
        project_id: str,
        source_refs: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    def retrieve_project_context(
        self,
        *,
        project_id: str,
        query: str,
        source_refs: list[dict[str, Any]],
        top_k: int = DEFAULT_TOP_K,
    ) -> LightRAGRetrievalResult: ...

    async def async_retrieve_project_context(
        self,
        *,
        project_id: str,
        query: str,
        source_refs: list[dict[str, Any]],
        top_k: int = DEFAULT_TOP_K,
    ) -> LightRAGRetrievalResult: ...
