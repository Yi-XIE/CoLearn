"""RetrievalStage — pre-fetches references and assembles the prompt support bundle."""

from __future__ import annotations

import asyncio
from typing import Any

from colearn.compression import RuntimeCompressionBridge
from colearn.knowledge import KnowledgeWorkspaceService
from colearn.learning.state_hooks import (
    build_prompt_support_bundle,
    build_retrieval_focus,
    build_retrieval_query_context,
    build_retrieval_reason,
)
from colearn.projects.models import LearningProject
from colearn.retrieval.service import RetrievalService
from colearn.sessions.store import LearningSession
from colearn.utils.async_guards import (
    reject_sync_inside_event_loop as _reject_sync_inside_event_loop,
)

from .context import TurnContext


class RetrievalStage:
    """Pure refactor of the legacy ``_prepare_retrieval_context`` family.

    Builds focus / query context / parallel support / prefetch bundle and the
    prompt-support bundle that downstream stages consume.
    """

    def __init__(
        self,
        *,
        retrieval_service: RetrievalService,
        knowledge_service: KnowledgeWorkspaceService,
        runtime_compression: RuntimeCompressionBridge,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.knowledge_service = knowledge_service
        self.runtime_compression = runtime_compression

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def run(self, ctx: TurnContext) -> TurnContext:
        retrieval_context = self._prepare_retrieval_context(
            project=ctx.project,
            session=ctx.session,
            board=ctx.board,
            source_profile=ctx.source_profile,
            user_message=ctx.user_message,
        )
        ctx.retrieval_focus = retrieval_context["retrieval_focus"]
        ctx.retrieval_reason = retrieval_context["retrieval_reason"]
        ctx.retrieval_query_context = retrieval_context["retrieval_query_context"]
        ctx.parallel_support = retrieval_context["parallel_support"]
        ctx.retrieval_bundle = retrieval_context["retrieval_bundle"]
        ctx.prefetched_references = retrieval_context["prefetched_references"]
        ctx.prompt_support_bundle = retrieval_context["prompt_support_bundle"]
        return ctx

    async def run_async(self, ctx: TurnContext) -> TurnContext:
        retrieval_context = await self._prepare_retrieval_context_async(
            project=ctx.project,
            session=ctx.session,
            board=ctx.board,
            source_profile=ctx.source_profile,
            user_message=ctx.user_message,
        )
        ctx.retrieval_focus = retrieval_context["retrieval_focus"]
        ctx.retrieval_reason = retrieval_context["retrieval_reason"]
        ctx.retrieval_query_context = retrieval_context["retrieval_query_context"]
        ctx.parallel_support = retrieval_context["parallel_support"]
        ctx.retrieval_bundle = retrieval_context["retrieval_bundle"]
        ctx.prefetched_references = retrieval_context["prefetched_references"]
        ctx.prompt_support_bundle = retrieval_context["prompt_support_bundle"]
        return ctx

    # ------------------------------------------------------------------
    # Internals (lifted verbatim from LearningOrchestrator)
    # ------------------------------------------------------------------
    def _prepare_retrieval_context(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        board,
        source_profile: dict[str, Any],
        user_message: str,
    ) -> dict[str, Any]:
        retrieval_focus = build_retrieval_focus(board=board, turn_mode=board.current_turn_mode)
        retrieval_reason = build_retrieval_reason(
            board=board,
            source_readiness=source_profile,
        )
        retrieval_query_context = build_retrieval_query_context(
            board=board,
            user_message=user_message,
            retrieval_focus=retrieval_focus,
            continuation_prompt=session.continuation_prompt,
        )
        parallel_support = self._build_parallel_support(
            project=project,
            session=session,
            retrieval_query_context=retrieval_query_context,
        )
        try:
            retrieval_bundle = self.retrieval_service.build_bundle(
                project=project,
                session=session,
                query=str(
                    retrieval_query_context.get("final_query")
                    or retrieval_focus.get("default_query")
                    or user_message
                    or ""
                ),
                libraries=None,
            )
        except (TimeoutError, OSError, RuntimeError) as exc:
            from colearn.learning.retrieval_bundle import empty_retrieval_bundle
            retrieval_bundle = empty_retrieval_bundle(
                query=str(retrieval_query_context.get("final_query") or user_message or ""),
                status="unavailable",
                fallback_reason=f"retrieval_unavailable:{type(exc).__name__}",
                warning=str(exc)[:200],
            )
        prefetched_references = self._prefetched_references_from_bundle(retrieval_bundle)
        parallel_references = self._prefetched_references_from_parallel_support(parallel_support)
        prompt_references = self._merge_prefetched_references(prefetched_references, parallel_references)
        prompt_support_bundle = build_prompt_support_bundle(
            board=board,
            prefetched_references=prompt_references,
            retrieval_focus=retrieval_focus,
        )
        return {
            "retrieval_focus": retrieval_focus,
            "retrieval_reason": retrieval_reason,
            "retrieval_query_context": retrieval_query_context,
            "parallel_support": parallel_support,
            "retrieval_bundle": retrieval_bundle,
            "prefetched_references": prefetched_references,
            "prompt_support_bundle": prompt_support_bundle,
        }

    async def _prepare_retrieval_context_async(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        board,
        source_profile: dict[str, Any],
        user_message: str,
    ) -> dict[str, Any]:
        retrieval_focus = build_retrieval_focus(board=board, turn_mode=board.current_turn_mode)
        retrieval_reason = build_retrieval_reason(
            board=board,
            source_readiness=source_profile,
        )
        retrieval_query_context = build_retrieval_query_context(
            board=board,
            user_message=user_message,
            retrieval_focus=retrieval_focus,
            continuation_prompt=session.continuation_prompt,
        )
        parallel_support = await self._build_parallel_support_dispatch(
            project=project,
            session=session,
            retrieval_query_context=retrieval_query_context,
        )
        try:
            retrieval_bundle = await self.retrieval_service.async_build_bundle_for_source_refs(
                project_id=project.project_id,
                query=str(
                    retrieval_query_context.get("final_query")
                    or retrieval_focus.get("default_query")
                    or user_message
                    or ""
                ),
                source_refs=list(session.source_refs or project.source_subset or project.source_refs),
                libraries=None,
            )
        except (TimeoutError, OSError, RuntimeError) as exc:
            from colearn.learning.retrieval_bundle import empty_retrieval_bundle
            retrieval_bundle = empty_retrieval_bundle(
                query=str(retrieval_query_context.get("final_query") or user_message or ""),
                status="unavailable",
                fallback_reason=f"retrieval_unavailable:{type(exc).__name__}",
                warning=str(exc)[:200],
            )
        prefetched_references = self._prefetched_references_from_bundle(retrieval_bundle)
        parallel_references = self._prefetched_references_from_parallel_support(parallel_support)
        prompt_references = self._merge_prefetched_references(prefetched_references, parallel_references)
        prompt_support_bundle = build_prompt_support_bundle(
            board=board,
            prefetched_references=prompt_references,
            retrieval_focus=retrieval_focus,
        )
        return {
            "retrieval_focus": retrieval_focus,
            "retrieval_reason": retrieval_reason,
            "retrieval_query_context": retrieval_query_context,
            "parallel_support": parallel_support,
            "retrieval_bundle": retrieval_bundle,
            "prefetched_references": prefetched_references,
            "prompt_support_bundle": prompt_support_bundle,
        }

    async def _build_parallel_support_dispatch(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        retrieval_query_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Async version of _build_parallel_support — calls _build_parallel_support_async directly."""
        queries = self._parallel_support_queries(retrieval_query_context)
        source_refs = list(session.source_refs or project.source_subset or project.source_refs)
        if not source_refs:
            return {"status": "skipped", "reason": "no_source_refs", "queries": queries, "results": []}
        if not queries:
            return {"status": "skipped", "reason": "no_parallel_queries", "queries": [], "results": []}
        try:
            results = await self._build_parallel_support_async(
                project=project,
                session=session,
                source_refs=source_refs,
                queries=queries,
            )
        except (TimeoutError, OSError, RuntimeError) as exc:
            return {"status": "error", "reason": f"{type(exc).__name__}: {exc}", "queries": queries, "results": []}
        statuses = {str(item.get("retrieval_status") or item.get("status") or "") for item in results}
        if any(status == "ready" for status in statuses):
            status = "partial" if any(status in {"error", "empty"} for status in statuses) else "ready"
        else:
            status = "error" if "error" in statuses else "empty"
        return {"status": status, "reason": "", "queries": queries, "results": results}

    def _prefetched_references_from_bundle(self, bundle) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = [dict(item) for item in list(getattr(bundle, "references", []) or [])]
        seen = {
            (
                str(item.get("source_ref") or item.get("source_path") or item.get("path") or ""),
                str(item.get("chunk_id") or ""),
            )
            for item in rows
        }
        for idx, chunk in enumerate(list(getattr(bundle, "chunks", []) or [])):
            source_ref = dict(getattr(chunk, "source_ref", {}) or {})
            raw_ref = str(
                source_ref.get("source_ref")
                or source_ref.get("path")
                or getattr(chunk, "source_path", "")
                or ""
            ).strip()
            if not raw_ref:
                continue
            metadata = dict(getattr(chunk, "metadata", {}) or {})
            chunk_id = str(metadata.get("chunk_id") or metadata.get("id") or f"chunk_{idx}")
            signature = (raw_ref, chunk_id)
            if signature in seen:
                continue
            seen.add(signature)
            rows.append(
                {
                    **source_ref,
                    **metadata,
                    "source_ref": raw_ref,
                    "source_path": str(getattr(chunk, "source_path", "") or ""),
                    "chunk_id": chunk_id,
                    "text": str(getattr(chunk, "text", "") or ""),
                    "score": getattr(chunk, "score", None),
                }
            )
        return rows

    def _merge_prefetched_references(
        self,
        primary: list[dict[str, Any]],
        secondary: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for item in [*primary, *secondary]:
            source_ref = str(item.get("source_ref") or item.get("source_path") or item.get("path") or "")
            chunk_id = str(item.get("chunk_id") or "")
            summary = str(item.get("summary") or item.get("text") or item.get("title") or "")
            signature = (source_ref, chunk_id, summary[:120])
            if signature in seen:
                continue
            seen.add(signature)
            merged.append(dict(item))
        return merged

    def _prefetched_references_from_parallel_support(
        self, parallel_support: dict[str, Any]
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for result in list(parallel_support.get("results") or []):
            query = str(result.get("query") or "")
            for item in list(result.get("references") or []):
                row = dict(item)
                row.setdefault("support_type", "parallel_retrieval")
                row.setdefault("query", query)
                rows.append(row)
        return rows

    def _build_parallel_support(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        retrieval_query_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Run multiple retrieval queries in parallel via asyncio.run.

        Must be called from a sync context (guarded by
        ``_reject_sync_inside_event_loop``).  Failure semantics are *partial*:
        one failing query yields ``status='partial'``, not a hard error, so the
        turn can still proceed with whatever evidence was gathered.
        """
        source_refs = list(session.source_refs or project.source_subset or project.source_refs)
        queries = self._parallel_support_queries(retrieval_query_context)
        if not source_refs:
            return {
                "status": "skipped",
                "reason": "no_source_refs",
                "queries": queries,
                "results": [],
            }
        if not queries:
            return {
                "status": "skipped",
                "reason": "no_parallel_queries",
                "queries": [],
                "results": [],
            }
        try:
            _reject_sync_inside_event_loop("_build_parallel_support")
            results = asyncio.run(
                self._build_parallel_support_async(
                    project=project,
                    session=session,
                    source_refs=source_refs,
                    queries=queries,
                )
            )
        except (TimeoutError, OSError, RuntimeError) as exc:
            return {
                "status": "error",
                "reason": f"{type(exc).__name__}: {exc}",
                "queries": queries,
                "results": [],
            }
        statuses = {str(item.get("retrieval_status") or item.get("status") or "") for item in results}
        if any(status == "ready" for status in statuses):
            status = "partial" if any(status in {"error", "empty"} for status in statuses) else "ready"
        else:
            status = "error" if "error" in statuses else "empty"
        return {
            "status": status,
            "reason": "",
            "queries": queries,
            "results": results,
        }

    def _parallel_support_queries(self, retrieval_query_context: dict[str, Any]) -> list[str]:
        candidates: list[str] = []
        final_query = str(retrieval_query_context.get("final_query") or "").strip()
        if final_query:
            candidates.append(final_query)
        for blocker in list(retrieval_query_context.get("critical_blockers") or []):
            desc = str((blocker or {}).get("desc") or "").strip()
            if desc:
                candidates.append(desc)
        for gap in list(retrieval_query_context.get("unverified_gaps") or []):
            gap_text = str(gap or "").strip()
            if gap_text:
                candidates.append(gap_text)
        deduped: list[str] = []
        seen: set[str] = set()
        for query in candidates:
            key = query.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(query)
            if len(deduped) >= 3:
                break
        return deduped

    async def _build_parallel_support_async(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        source_refs: list[str],
        queries: list[str],
    ) -> list[dict[str, Any]]:
        tasks = [
            self._retrieve_parallel_support_one(
                project=project,
                session=session,
                source_refs=source_refs,
                query=query,
            )
            for query in queries[:3]
        ]
        return list(await asyncio.gather(*tasks))

    async def _retrieve_parallel_support_one(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        source_refs: list[str],
        query: str,
    ) -> dict[str, Any]:
        try:
            async_method = getattr(self.retrieval_service, "async_build_bundle_for_source_refs", None)
            if callable(async_method):
                bundle = await async_method(
                    project_id=project.project_id,
                    query=query,
                    source_refs=source_refs,
                    libraries=None,
                )
            elif hasattr(self.retrieval_service, "build_bundle_for_source_refs"):
                bundle = await asyncio.to_thread(
                    self.retrieval_service.build_bundle_for_source_refs,
                    project_id=project.project_id,
                    query=query,
                    source_refs=source_refs,
                    libraries=None,
                )
            else:
                bundle = await asyncio.to_thread(
                    self.retrieval_service.build_bundle,
                    project=project,
                    session=session,
                    query=query,
                    libraries=None,
                )
        except (TimeoutError, OSError, RuntimeError) as exc:
            return {
                "query": query,
                "retrieval_status": "error",
                "fallback_reason": f"{type(exc).__name__}: {exc}",
                "warnings": [str(exc)],
                "references": [],
            }
        return self._parallel_bundle_payload(query=query, bundle=bundle)

    def _parallel_bundle_payload(self, *, query: str, bundle) -> dict[str, Any]:
        return {
            "query": query,
            "retrieval_status": str(getattr(bundle, "retrieval_status", "") or "unknown"),
            "fallback_reason": str(getattr(bundle, "fallback_reason", "") or ""),
            "warnings": list(getattr(bundle, "warnings", []) or []),
            "references": self._prefetched_references_from_bundle(bundle),
        }
