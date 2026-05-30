"""Source readiness preflight for learning turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from colearn.knowledge import KnowledgeWorkspaceService
from colearn.retrieval.service import RetrievalService


@dataclass
class SourceReadinessPreflight:
    retrieval_service: RetrievalService
    knowledge_service: KnowledgeWorkspaceService

    def run(
        self,
        *,
        project_id: str,
        source_refs: list[str],
    ) -> dict[str, Any]:
        return self._finalize_source_profile(
            source_refs=source_refs,
            sync_result=self._safe_sync_result(
                lambda: self.retrieval_service.sync_source_refs(
                    project_id=project_id,
                    source_refs=source_refs,
                )
            ),
        )

    async def run_async(
        self,
        *,
        project_id: str,
        source_refs: list[str],
    ) -> dict[str, Any]:
        return self._finalize_source_profile(
            source_refs=source_refs,
            sync_result=await self._safe_async_sync_result(
                lambda: self.retrieval_service.async_sync_source_refs(
                    project_id=project_id,
                    source_refs=source_refs,
                )
            ),
        )

    def _finalize_source_profile(
        self,
        *,
        source_refs: list[str],
        sync_result: dict[str, Any],
    ) -> dict[str, Any]:
        source_profile = self.knowledge_service.build_project_source_profile(
            source_refs=source_refs,
            indexed_paths=list(sync_result.get("indexed_paths") or []),
            sync_status=str(sync_result.get("sync_status") or "unavailable"),
            warnings=list(sync_result.get("warnings") or []),
        )
        return {
            **source_profile,
            "sync": dict(sync_result),
        }

    def _safe_sync_result(
        self,
        getter: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return getter()
        except (RuntimeError, ValueError, OSError, ConnectionError) as exc:
            return self._unavailable_sync_result(exc)

    async def _safe_async_sync_result(
        self,
        getter: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        try:
            return await getter()
        except (RuntimeError, ValueError, OSError, ConnectionError) as exc:
            return self._unavailable_sync_result(exc)

    def _unavailable_sync_result(self, exc: Exception) -> dict[str, Any]:
        return {
            "indexed_paths": [],
            "sync_status": "unavailable",
            "warnings": [f"sync_unavailable:{type(exc).__name__}: {str(exc)[:200]}"],
        }
