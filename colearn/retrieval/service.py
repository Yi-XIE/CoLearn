"""Retrieval service that narrows project sources into a RetrievalBundle."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from colearn.config.defaults import Defaults
from colearn.knowledge.library import SourceLibrary
from colearn.learning.retrieval_bundle import (
    RetrievalBundle,
    RetrievalChunk,
    empty_retrieval_bundle,
)
from colearn.projects.models import LearningProject
from colearn.sessions.store import LearningSession
from .adapters import LightRAGClientProtocol, LightRAGConfigurationError, get_lightrag_client
from .cache import RetrievalCache


class RetrievalService:
    """Narrows project sources into a RetrievalBundle, with a fallback chain.

    Order: (1) LightRAG retrieval if ready → (2) raw file preview fallback if
    sources resolve on disk → (3) empty bundle with status='empty' or 'error'.
    The fallback is intentional: it keeps turns flowing when LightRAG is down.
    """

    def __init__(
        self,
        library_root: str | Path | None = None,
        *,
        lightrag_client: LightRAGClientProtocol | None = None,
        workspace: str | Path | None = None,
        cache: RetrievalCache | None = None,
    ) -> None:
        self._library_root = Path(library_root).resolve() if library_root else None
        self._workspace = Path(workspace).resolve() if workspace else Path.cwd()
        self._lightrag_client = lightrag_client
        self._lightrag_error: Exception | None = None
        self._cache = cache or RetrievalCache()
        if self._lightrag_client is None:
            try:
                self._lightrag_client = get_lightrag_client(workspace=self._workspace)
            except LightRAGConfigurationError as exc:
                self._lightrag_error = exc

    def build_bundle(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        query: str,
        libraries: list[SourceLibrary] | None = None,
    ) -> RetrievalBundle:
        source_refs = list(session.source_refs or project.source_subset or project.source_refs)
        return self.build_bundle_for_source_refs(
            project_id=project.project_id,
            query=query,
            source_refs=source_refs,
            libraries=libraries,
        )

    def build_bundle_for_source_refs(
        self,
        *,
        project_id: str,
        query: str,
        source_refs: list[str],
        libraries: list[SourceLibrary] | None = None,
    ) -> RetrievalBundle:
        if not source_refs:
            return empty_retrieval_bundle(
                query=query,
                status="empty",
                fallback_reason="no_source_refs",
                warning="No project sources attached yet.",
            )

        cached = self._cache.get(project_id=project_id, query=query, source_refs=source_refs)
        if cached is not None:
            return cached

        normalized_refs = self._normalize_source_refs(source_refs, libraries=libraries or [])
        lightrag_result = self._require_lightrag_client().retrieve_project_context(
            project_id=project_id,
            query=query,
            source_refs=normalized_refs,
            top_k=Defaults.RETRIEVAL_TOP_K,
        )
        bundle = self._bundle_from_lightrag_result(
            lightrag_result=lightrag_result,
            project_id=project_id,
            query=query,
            source_refs=source_refs,
            normalized_refs=normalized_refs,
            libraries=libraries or [],
        )
        if bundle.retrieval_status == "ready":
            self._cache.put(project_id=project_id, query=query, source_refs=source_refs, value=bundle)
        return bundle

    async def async_build_bundle_for_source_refs(
        self,
        *,
        project_id: str,
        query: str,
        source_refs: list[str],
        libraries: list[SourceLibrary] | None = None,
    ) -> RetrievalBundle:
        if not source_refs:
            return empty_retrieval_bundle(
                query=query,
                status="empty",
                fallback_reason="no_source_refs",
                warning="No project sources attached yet.",
            )

        cached = self._cache.get(project_id=project_id, query=query, source_refs=source_refs)
        if cached is not None:
            return cached

        normalized_refs = self._normalize_source_refs(source_refs, libraries=libraries or [])
        client = self._require_lightrag_client()
        async_retrieve = getattr(client, "async_retrieve_project_context", None)
        if async_retrieve is not None:
            lightrag_result = await async_retrieve(
                project_id=project_id,
                query=query,
                source_refs=normalized_refs,
                top_k=Defaults.RETRIEVAL_TOP_K,
            )
        else:
            lightrag_result = await asyncio.to_thread(
                client.retrieve_project_context,
                project_id=project_id,
                query=query,
                source_refs=normalized_refs,
                top_k=Defaults.RETRIEVAL_TOP_K,
            )
        bundle = self._bundle_from_lightrag_result(
            lightrag_result=lightrag_result,
            project_id=project_id,
            query=query,
            source_refs=source_refs,
            normalized_refs=normalized_refs,
            libraries=libraries or [],
        )
        if bundle.retrieval_status == "ready":
            self._cache.put(project_id=project_id, query=query, source_refs=source_refs, value=bundle)
        return bundle

    def _bundle_from_lightrag_result(
        self,
        *,
        lightrag_result,
        project_id: str,
        query: str,
        source_refs: list[str],
        normalized_refs: list[dict[str, Any]],
        libraries: list[SourceLibrary],
    ) -> RetrievalBundle:
        _ = (project_id, normalized_refs)
        if (
            lightrag_result.retrieval_status == "ready"
            and (lightrag_result.chunks or lightrag_result.references or lightrag_result.text)
        ):
            return RetrievalBundle(
                query=lightrag_result.query or query,
                text=lightrag_result.text,
                references=list(lightrag_result.references or []),
                chunks=[
                    RetrievalChunk(
                        text=str(item.get("text") or ""),
                        source_ref=dict(item.get("reference") or {}),
                        source_path=str(item.get("source") or item.get("source_path") or ""),
                        score=float(item.get("score")) if item.get("score") is not None else None,
                        metadata={
                            key: value
                            for key, value in item.items()
                            if key not in {"text", "reference", "source", "source_path", "score"}
                        },
                    )
                    for item in (lightrag_result.chunks or [])
                ],
                warnings=list(lightrag_result.warnings or []),
                retrieval_status="ready",
                fallback_reason=lightrag_result.fallback_reason,
                metadata=dict(lightrag_result.metadata or {}),
            )

        chunks: list[RetrievalChunk] = []
        references: list[dict[str, object]] = []
        warnings: list[str] = list(lightrag_result.warnings or [])

        for raw_ref in source_refs:
            candidate = self._resolve_source_path(raw_ref, libraries=libraries)
            if candidate is None:
                warnings.append(f"Missing source: {raw_ref}")
                continue
            preview = self._read_preview(candidate)
            if not preview:
                warnings.append(f"Empty source: {candidate}")
                continue
            references.append(
                {
                    "source_ref": raw_ref,
                    "source_path": str(candidate),
                    "title": candidate.name,
                }
            )
            chunks.append(
                RetrievalChunk(
                    text=preview,
                    source_ref={"source_ref": raw_ref, "title": candidate.name},
                    source_path=str(candidate),
                    score=1.0,
                )
            )

        if not chunks:
            status = "error" if warnings else "empty"
            fallback = (
                lightrag_result.fallback_reason
                or ("unreadable_sources" if warnings else "no_retrieval_hits")
            )
            return empty_retrieval_bundle(
                query=query,
                status=status,
                fallback_reason=fallback,
                warning=warnings[0] if warnings else None,
                metadata={"warnings": warnings},
            )

        text = "\n\n".join(
            f"[{chunk.source_ref.get('title') or chunk.source_path}]\n{chunk.text}"
            for chunk in chunks
        )
        return RetrievalBundle(
            query=query,
            text=text,
            references=references,
            chunks=chunks,
            warnings=warnings,
            retrieval_status="ready",
            metadata={
                "source_count": len(chunks),
                "fallback_from_lightrag": lightrag_result.retrieval_status,
            },
        )

    def sync_project_sources(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        libraries: list[SourceLibrary] | None = None,
    ) -> dict[str, Any]:
        source_refs = session.source_refs or project.source_subset or project.source_refs
        normalized_refs = self._normalize_source_refs(source_refs, libraries=libraries or [])
        self._cache.invalidate_project(project.project_id)
        return self._require_lightrag_client().sync_project_sources(project.project_id, normalized_refs)

    def sync_source_refs(
        self,
        *,
        project_id: str,
        source_refs: list[str],
        libraries: list[SourceLibrary] | None = None,
    ) -> dict[str, Any]:
        normalized_refs = self._normalize_source_refs(source_refs, libraries=libraries or [])
        self._cache.invalidate_project(project_id)
        return self._require_lightrag_client().sync_project_sources(project_id, normalized_refs)

    async def async_sync_source_refs(
        self,
        *,
        project_id: str,
        source_refs: list[str],
        libraries: list[SourceLibrary] | None = None,
    ) -> dict[str, Any]:
        normalized_refs = self._normalize_source_refs(source_refs, libraries=libraries or [])
        self._cache.invalidate_project(project_id)
        client = self._require_lightrag_client()
        async_sync = getattr(client, "async_sync_project_sources", None)
        if async_sync is not None:
            return await async_sync(project_id, normalized_refs)
        return await asyncio.to_thread(
            client.sync_project_sources,
            project_id,
            normalized_refs,
        )

    def _require_lightrag_client(self) -> LightRAGClientProtocol:
        if self._lightrag_client is None and self._lightrag_error is not None:
            raise self._lightrag_error
        if self._lightrag_client is None:
            raise RuntimeError("LightRAG client is unavailable.")
        return self._lightrag_client

    def _normalize_source_refs(
        self,
        source_refs: list[str],
        *,
        libraries: list[SourceLibrary],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for raw_ref in source_refs:
            candidate = self._resolve_source_path(raw_ref, libraries=libraries)
            if candidate is None:
                normalized.append({"source_ref": raw_ref, "title": Path(raw_ref).name})
                continue
            normalized.append(
                {
                    "source_ref": raw_ref,
                    "source_path": str(candidate),
                    "title": candidate.name,
                    "source_id": str(candidate),
                }
            )
        return normalized

    def _resolve_source_path(
        self,
        raw_ref: str,
        *,
        libraries: list[SourceLibrary],
    ) -> Path | None:
        candidate = Path(raw_ref)
        if candidate.exists():
            return candidate.resolve()
        if self._library_root is not None:
            rooted = (self._library_root / raw_ref).resolve()
            if rooted.exists():
                return rooted
        for library in libraries:
            for source_path in library.source_paths:
                lib_candidate = Path(source_path)
                if lib_candidate.name == raw_ref and lib_candidate.exists():
                    return lib_candidate.resolve()
        return None

    def _read_preview(self, path: Path, limit: int = 3000) -> str:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""
        return text[:limit].strip()
