"""Source readiness preflight for learning turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
        sync_result = self.retrieval_service.sync_source_refs(
            project_id=project_id,
            source_refs=source_refs,
        )
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
