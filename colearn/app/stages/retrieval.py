"""RetrievalStage - pre-fetches references and assembles the prompt support bundle."""

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

from .context import TurnContext


class RetrievalStage:
    """Build retrieval context for downstream execution stages."""

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
        ctx.external_web_fallback = retrieval_context["external_web_fallback"]
        ctx.retrieval_bundle = retrieval_context["retrieval_bundle"]
        ctx.prefetched_references = retrieval_context["prefetched_references"]
        ctx.prompt_support_bundle = retrieval_context["prompt_support_bundle"]
        return ctx

    def skip(self, ctx: TurnContext, *, reason: str) -> TurnContext:
        from colearn.learning.retrieval_bundle import empty_retrieval_bundle

        query = str(ctx.user_message or "")
        ctx.retrieval_focus = {"turn_mode": "PAUSED", "default_query": query}
        ctx.retrieval_reason = reason
        ctx.retrieval_query_context = {"final_query": query, "skipped": True, "reason": reason}
        ctx.parallel_support = {"status": "skipped", "reason": reason, "queries": [], "results": []}
        ctx.external_web_fallback = {"recommended": False, "reason": reason}
        ctx.retrieval_bundle = empty_retrieval_bundle(
            query=query,
            status="skipped",
            fallback_reason=reason,
            warning="learning retrieval skipped in chat mode",
        )
        ctx.prefetched_references = []
        ctx.prompt_support_bundle = []
        return ctx

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
            turn_mode=board.current_turn_mode,
            board=board,
        )
        retrieval_bundle = await self._build_prefetch_bundle(
            project=project,
            session=session,
            turn_mode=board.current_turn_mode,
            retrieval_focus=retrieval_focus,
            retrieval_query_context=retrieval_query_context,
            user_message=user_message,
            board=board,
        )
        prefetched_references = self._prefetched_references_from_bundle(retrieval_bundle)
        parallel_references = self._prefetched_references_from_parallel_support(parallel_support)
        prompt_references = self._merge_prefetched_references(prefetched_references, parallel_references)
        prompt_support_bundle = build_prompt_support_bundle(
            board=board,
            prefetched_references=prompt_references,
            retrieval_focus=retrieval_focus,
        )
        external_web_fallback = self._external_web_fallback(
            user_message=user_message,
            retrieval_bundle=retrieval_bundle,
            prompt_support_bundle=prompt_support_bundle,
        )
        return {
            "retrieval_focus": retrieval_focus,
            "retrieval_reason": retrieval_reason,
            "retrieval_query_context": retrieval_query_context,
            "parallel_support": parallel_support,
            "external_web_fallback": external_web_fallback,
            "retrieval_bundle": retrieval_bundle,
            "prefetched_references": prefetched_references,
            "prompt_support_bundle": prompt_support_bundle,
        }

    async def _build_prefetch_bundle(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        turn_mode: str,
        retrieval_focus: dict[str, Any],
        retrieval_query_context: dict[str, Any],
        user_message: str,
        board=None,
    ):
        from colearn.learning.retrieval_bundle import empty_retrieval_bundle

        query = str(
            retrieval_query_context.get("final_query")
            or retrieval_focus.get("default_query")
            or user_message
            or ""
        )
        if not self._should_prefetch_retrieval(turn_mode=turn_mode, board=board):
            return empty_retrieval_bundle(
                query=query,
                status="skipped",
                fallback_reason=f"prefetch_skipped:{str(turn_mode or '').lower()}",
                warning="retrieval prefetch skipped for current turn mode",
            )

        # Dynamically adjust top_k based on cognitive_load:
        # HIGH → 3 (slightly more than effective_max=2 for ranking headroom)
        # NORMAL → 5 (current default)
        # LOW → 8 (increased coverage for deeper exploration)
        cognitive_load = str(getattr(getattr(board, "student_snapshot", None), "cognitive_load", "") or "").upper()
        effective_top_k = {"HIGH": 3, "NORMAL": 5, "LOW": 8}.get(cognitive_load, 5)

        source_refs = list(session.source_refs or project.source_subset or project.source_refs)
        async_method = getattr(self.retrieval_service, "async_build_bundle_for_source_refs", None)
        try:
            if callable(async_method):
                return await async_method(
                    project_id=project.project_id,
                    query=query,
                    source_refs=source_refs,
                    libraries=None,
                    top_k=effective_top_k,
                )
            if hasattr(self.retrieval_service, "build_bundle_for_source_refs"):
                return await asyncio.to_thread(
                    self.retrieval_service.build_bundle_for_source_refs,
                    project_id=project.project_id,
                    query=query,
                    source_refs=source_refs,
                    libraries=None,
                    top_k=effective_top_k,
                )
            return await asyncio.to_thread(
                self.retrieval_service.build_bundle,
                project=project,
                session=session,
                query=query,
                libraries=None,
                top_k=effective_top_k,
            )
        except (TimeoutError, OSError, RuntimeError) as exc:
            return empty_retrieval_bundle(
                query=query,
                status="unavailable",
                fallback_reason=f"retrieval_unavailable:{type(exc).__name__}",
                warning=str(exc)[:200],
            )

    async def _build_parallel_support_dispatch(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        retrieval_query_context: dict[str, Any],
        turn_mode: str,
        board=None,
    ) -> dict[str, Any]:
        queries = self._parallel_support_queries(retrieval_query_context, board=board)
        source_refs = list(session.source_refs or project.source_subset or project.source_refs)
        if not self._should_prefetch_retrieval(turn_mode=turn_mode, board=board):
            return {"status": "skipped", "reason": f"turn_mode:{turn_mode.lower()}", "queries": queries, "results": []}
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

    def _should_prefetch_retrieval(self, *, turn_mode: str, board=None) -> bool:
        mode = str(turn_mode or "").upper()
        if mode == "PAUSED":
            return False
        if mode == "CHECK":
            return True
        if mode != "LEARN" or board is None:
            return True
        if int(getattr(board, "board_version", 1) or 1) <= 1:
            return True
        if board.gaps_and_blockers.critical_blockers or board.gaps_and_blockers.unverified_gaps:
            return True
        return not bool(board.evidence_refs or board.learning_board.evidence_refs)

    def _external_web_fallback(
        self,
        *,
        user_message: str,
        retrieval_bundle,
        prompt_support_bundle: list[dict[str, Any]],
    ) -> dict[str, Any]:
        lowered = str(user_message or "").strip().lower()
        explicit = any(
            marker in lowered
            for marker in (
                "latest",
                "current",
                "today",
                "news",
                "web",
                "internet",
                "online",
                "search",
                "browse",
                "最新",
                "今天",
                "新闻",
                "网页",
                "网上",
                "互联网",
                "搜索",
                "公开资料",
                "外部资料",
            )
        )
        status = str(getattr(retrieval_bundle, "retrieval_status", "") or "").lower()
        no_local_support = status in {"empty", "unavailable", "error"} or not prompt_support_bundle
        recommended = bool(explicit or no_local_support)
        reason = "explicit_external_source_request" if explicit else "local_retrieval_insufficient"
        return {
            "recommended": recommended,
            "reason": reason if recommended else "",
            "retrieval_status": status,
        }

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
        raise RuntimeError("RetrievalStage is async-only; use _build_parallel_support_dispatch")

    def _parallel_support_queries(self, retrieval_query_context: dict[str, Any], board=None) -> list[str]:
        """Build parallel support queries for blockers and gaps.

        Dynamically adjusts the max query count based on cognitive_load:
        - HIGH: 1 query (only the most urgent blocker)
        - NORMAL: 2 queries (current default, down from 3)
        - LOW: 3 queries (full coverage)
        """
        cognitive_load = str(getattr(getattr(board, "student_snapshot", None), "cognitive_load", "") or "").upper()
        max_queries = {"HIGH": 1, "NORMAL": 2, "LOW": 3}.get(cognitive_load, 2)

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
            if len(deduped) >= max_queries:
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
            bundle = await self.retrieval_service.async_build_bundle_for_source_refs(
                project_id=project.project_id,
                query=query,
                source_refs=source_refs,
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
