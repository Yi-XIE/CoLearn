"""Minimal local knowledge workspace service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .library import SourceLibrary


class KnowledgeWorkspaceService:
    def __init__(self) -> None:
        self._libraries: dict[str, SourceLibrary] = {}

    def create_library(self, library_id: str, name: str) -> SourceLibrary:
        library = SourceLibrary(library_id=library_id, name=name)
        self._libraries[library_id] = library
        return library

    def get_library(self, library_id: str) -> SourceLibrary | None:
        return self._libraries.get(library_id)

    def list_libraries(self) -> list[SourceLibrary]:
        return list(self._libraries.values())

    def attach_source(self, *, library_id: str, source_path: str) -> SourceLibrary:
        library = self._require_library(library_id)
        resolved = self._normalize_path(source_path)
        if resolved not in library.source_paths:
            library.source_paths.append(resolved)
        library.source_status[resolved] = self._build_source_status(resolved)
        return library

    def detach_source(self, *, library_id: str, source_path: str) -> SourceLibrary:
        library = self._require_library(library_id)
        resolved = self._normalize_path(source_path)
        library.source_paths = [item for item in library.source_paths if item != resolved]
        library.indexed_paths = [item for item in library.indexed_paths if item != resolved]
        library.source_status.pop(resolved, None)
        return library

    def set_index_status(
        self,
        *,
        library_id: str,
        indexed_paths: list[str],
        retrieval_status: str,
        warnings: list[str] | None = None,
    ) -> SourceLibrary:
        library = self._require_library(library_id)
        normalized_indexed = [self._normalize_path(item) for item in indexed_paths if str(item).strip()]
        library.indexed_paths = normalized_indexed
        library.retrieval_status = retrieval_status
        library.warnings = list(warnings or [])
        statuses: dict[str, dict[str, Any]] = {}
        for source_path in library.source_paths:
            source_key = self._normalize_path(source_path)
            state = "ready" if source_key in normalized_indexed else self._build_source_status(source_key)["state"]
            statuses[source_key] = {
                "path": source_key,
                "state": state,
                "indexed": source_key in normalized_indexed,
                "exists": Path(source_key).exists(),
            }
        library.source_status = statuses
        return library

    def build_project_source_profile(
        self,
        *,
        source_refs: list[str],
        indexed_paths: list[str] | None = None,
        sync_status: str = "unavailable",
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_indexed = {self._normalize_path(item) for item in (indexed_paths or []) if str(item).strip()}
        items: list[dict[str, Any]] = []
        ready_count = 0
        for raw_ref in source_refs:
            source_path = self._normalize_path(raw_ref)
            exists = Path(source_path).exists()
            indexed = source_path in normalized_indexed
            if indexed:
                state = "ready"
                ready_count += 1
            elif exists:
                state = "attached"
            else:
                state = "missing"
            items.append(
                {
                    "source_ref": raw_ref,
                    "source_path": source_path,
                    "state": state,
                    "indexed": indexed,
                    "exists": exists,
                }
            )
        if not source_refs:
            readiness = "empty"
        elif ready_count == len(source_refs):
            readiness = "ready"
        elif ready_count > 0:
            readiness = "partial"
        elif sync_status == "error":
            readiness = "error"
        elif sync_status in {"synced", "success", "submitted"}:
            readiness = "indexing"
        else:
            readiness = "unavailable"
        return {
            "readiness": readiness,
            "sync_status": sync_status,
            "indexed_paths": sorted(normalized_indexed),
            "warnings": list(warnings or []),
            "sources": items,
        }

    def _require_library(self, library_id: str) -> SourceLibrary:
        library = self.get_library(library_id)
        if library is None:
            raise KeyError(f"Library not found: {library_id}")
        return library

    def _normalize_path(self, source_path: str) -> str:
        candidate = Path(str(source_path or "").strip())
        try:
            return str(candidate.resolve()) if candidate.exists() else str(candidate)
        except OSError:
            return str(candidate)

    def _build_source_status(self, source_path: str) -> dict[str, Any]:
        exists = Path(source_path).exists()
        return {
            "path": source_path,
            "state": "attached" if exists else "missing",
            "indexed": False,
            "exists": exists,
        }
