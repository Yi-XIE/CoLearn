"""Main assembly entrypoint for a single CoLearn learning turn."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from threading import Thread
from time import time
from typing import Any, Callable
from uuid import uuid4

from colearn.logging_config import get_logger

from colearn.compression import ProductCompressionBridge, ProductCompressionResult, RuntimeCompressionBridge
from colearn.knowledge import KnowledgeWorkspaceService
from colearn.learning.state_hooks import (
    before_turn,
    build_prompt_support_bundle,
    build_retrieval_evidence_map,
    build_learning_board,
    build_retrieval_focus,
    build_retrieval_query_context,
    build_retrieval_reason,
    build_state_snapshot,
    policy,
)
from colearn.memory.store import EventMemoryStore, MemoryEvent
from colearn.paths import colearn_nanobot_workspace
from colearn.projects.models import LearningProject
from colearn.projects.service import LearningProjectService
from colearn.retrieval.service import RetrievalService
from colearn.runtime_v2.context_bridge import build_learning_turn_request
from colearn.runtime_v2.executor import NanobotTurnExecutor
from colearn.runtime_v2 import build_learning_closure
from colearn.sessions.store import LearningSession, SessionStore
from .source_preflight import SourceReadinessPreflight

logger = get_logger(__name__)


from colearn.utils.async_guards import reject_sync_inside_event_loop as _reject_sync_inside_event_loop

class BackgroundTurnFinalizer:
    def __init__(
        self,
        *,
        product_compression: ProductCompressionBridge,
        on_result: Callable[..., None],
    ) -> None:
        self.product_compression = product_compression
        self.on_result = on_result
        self._threads: list[Thread] = []

    def schedule(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        board,
        request,
        result,
    ) -> None:
        """Spawn a daemon Thread for product compression that may outlive the turn.

        Daemon so the process can exit if needed; `shutdown(timeout)` should be
        called by the FastAPI lifespan to give in-flight compressions a chance
        to finish before SIGTERM.
        """
        status_payload = {
            "status": "scheduled",
            "started_at": int(time()),
            "finished_at": None,
            "error": "",
            "base_board_version": int(board.board_version or 1),
        }
        worker = Thread(
            target=self._run,
            kwargs={
                "project": project,
                "session": session,
                "board": board,
                "request": request,
                "result": result,
                "status_payload": status_payload,
            },
            daemon=True,
        )
        self._threads.append(worker)
        worker.start()

    def shutdown(self, timeout: float = 5.0) -> None:
        for t in self._threads:
            t.join(timeout=timeout)
        self._threads = [t for t in self._threads if t.is_alive()]

    def _run(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        board,
        request,
        result,
        status_payload: dict[str, Any],
    ) -> None:
        try:
            product_output = self.product_compression.compress(
                project=project,
                session=session,
                board=board,
                request=request,
                final_text=result.final_text,
            )
            self.on_result(
                session_id=session.session_id,
                project_id=project.project_id,
                request=request,
                board=board,
                product_output=product_output,
                error=None,
                status_payload=status_payload,
            )
        except Exception as exc:
            self.on_result(
                session_id=session.session_id,
                project_id=project.project_id,
                request=request,
                board=board,
                product_output=None,
                error=exc,
                status_payload=status_payload,
            )


class LearningOrchestrator:
    SESSION_AUTOCOMPACT_MAX_MESSAGES = 24
    SESSION_AUTOCOMPACT_KEEP_TAIL = 12
    SESSION_AUTOCOMPACT_SUMMARY_MAX_CHARS = 800
    DREAM_CONSOLIDATION_EVENT_INTERVAL = 20
    BOARD_DERIVATION_EVENT_INTERVAL = 5  # Q3: trigger board snapshot every N events

    def __init__(
        self,
        *,
        project_service: LearningProjectService | None = None,
        session_store: SessionStore | None = None,
        memory_store: EventMemoryStore | None = None,
        knowledge_service: KnowledgeWorkspaceService | None = None,
        retrieval_service: RetrievalService | None = None,
        executor: NanobotTurnExecutor | None = None,
        runtime_compression: RuntimeCompressionBridge | None = None,
        product_compression: ProductCompressionBridge | None = None,
        board_deriver: Any = None,  # Q4: optional BoardSnapshotDeriver
    ) -> None:
        self.project_service = project_service or LearningProjectService()
        self.session_store = session_store or SessionStore()
        self.memory_store = memory_store or EventMemoryStore()
        self.knowledge_service = knowledge_service or KnowledgeWorkspaceService()
        self.retrieval_service = retrieval_service or RetrievalService()
        self.source_preflight = SourceReadinessPreflight(
            retrieval_service=self.retrieval_service,
            knowledge_service=self.knowledge_service,
        )
        self.executor = executor or NanobotTurnExecutor(
            workspace=colearn_nanobot_workspace(),
            retrieval_service=self.retrieval_service,
            memory_store=self.memory_store,
        )
        self.runtime_compression = runtime_compression or RuntimeCompressionBridge()
        self.product_compression = product_compression or ProductCompressionBridge()
        self.background_finalizer = BackgroundTurnFinalizer(
            product_compression=self.product_compression,
            on_result=self.apply_background_result,
        )
        self.board_deriver = board_deriver

    def shutdown(self, timeout: float = 5.0) -> None:
        self.background_finalizer.shutdown(timeout=timeout)

    def run_turn(
        self,
        *,
        session_id: str,
        user_message: str,
        project_id: str = "",
        language: str = "zh",
        attachments: list[dict[str, object]] | None = None,
        requested_skills: list[str] | None = None,
        stream_emit: Callable[[dict[str, Any]], None] | None = None,
    ):
        """Synchronous turn entry — runs the five-stage pipeline.

        Sync by design: callers (FastAPI WS handler) wrap it in `to_thread.run_sync`
        so the nested `asyncio.run` inside the executor doesn't collide with the
        request's event loop. Pipeline: preflight → support → execute → finalize → writeback.
        """
        turn_context = self._prepare_turn_context(
            session_id=session_id,
            project_id=project_id,
        )
        session = turn_context["session"]
        project = turn_context["project"]
        board = turn_context["board"]
        snapshot = turn_context["snapshot"]
        source_profile = turn_context["source_profile"]
        retrieval_context = self._prepare_retrieval_context(
            project=project,
            session=session,
            board=board,
            source_profile=source_profile,
            user_message=user_message,
        )
        self._sync_project_retrieval_profile(
            project=project,
            source_profile=source_profile,
            board=board,
            retrieval_context=retrieval_context,
        )
        turn_policy = policy(
            board=board,
            user_message=user_message,
        )
        request = self._build_turn_request(
            session=session,
            project=project,
            board=board,
            snapshot=snapshot,
            source_profile=source_profile,
            retrieval_context=retrieval_context,
            user_message=user_message,
            language=language,
            turn_policy=turn_policy,
            attachments=attachments or [],
            requested_skills=requested_skills or [],
            stream_emit=stream_emit,
        )
        compressed, normalized = self._execute_turn(
            project=project,
            session=session,
            request=request,
            snapshot=snapshot,
            turn_policy=turn_policy,
        )
        normalized, retrieval_hits, retrieval_misses, retrieval_evidence_map = self._enrich_turn_result(
            request=compressed.request,
            result=normalized,
            retrieval_context=retrieval_context,
        )
        request_with_metadata = self._attach_retrieval_metadata(
            compressed.request,
            retrieval_focus=retrieval_context["retrieval_focus"],
            retrieval_query_context=retrieval_context["retrieval_query_context"],
            retrieval_reason=retrieval_context["retrieval_reason"],
            prefetched_references=retrieval_context["prefetched_references"],
            parallel_support=retrieval_context["parallel_support"],
            prompt_support_bundle=retrieval_context["prompt_support_bundle"],
            retrieval_hits=retrieval_hits,
            retrieval_misses=retrieval_misses,
            retrieval_evidence_map=retrieval_evidence_map,
        )
        self._write_back(
            project=project,
            session=session,
            request=request_with_metadata,
            result=normalized,
        )
        self.background_finalizer.schedule(
            project=project,
            session=session,
            board=board,
            request=compressed.request,
            result=normalized,
        )
        return normalized

    def _prepare_turn_context(
        self,
        *,
        session_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        session = self._get_or_create_session(session_id=session_id, project_id=project_id)
        project = self._get_or_create_project(project_id=project_id, session=session)
        source_refs = list(session.source_refs or project.source_subset or project.source_refs)
        source_profile = self.source_preflight.run(
            project_id=project.project_id,
            source_refs=source_refs,
        )
        board = build_learning_board(
            project=project,
            session=session,
            latest_review=project.latest_review,
        )
        snapshot = build_state_snapshot(
            project=project,
            session=session,
            latest_review=project.latest_review,
        )
        return {
            "session": session,
            "project": project,
            "source_profile": source_profile,
            "board": board,
            "snapshot": snapshot,
        }

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

    def _sync_project_retrieval_profile(
        self,
        *,
        project: LearningProject,
        source_profile: dict[str, Any],
        board,
        retrieval_context: dict[str, Any],
    ) -> None:
        retrieval_bundle = retrieval_context["retrieval_bundle"]
        project.retrieval_profile = {
            **project.retrieval_profile,
            **source_profile,
            "board": board.to_dict(),
            "retrieval_focus": retrieval_context["retrieval_focus"],
            "retrieval_query_context": retrieval_context["retrieval_query_context"],
            "retrieval_reason": retrieval_context["retrieval_reason"],
            "prefetched_references": retrieval_context["prefetched_references"],
            "parallel_support": retrieval_context["parallel_support"],
            "prompt_support_bundle": retrieval_context["prompt_support_bundle"],
            "prefetch_bundle": {
                "query": retrieval_bundle.query,
                "retrieval_status": retrieval_bundle.retrieval_status,
                "fallback_reason": retrieval_bundle.fallback_reason,
                "warnings": list(retrieval_bundle.warnings or []),
            },
        }

    def _build_turn_request(
        self,
        *,
        session: LearningSession,
        project: LearningProject,
        board,
        snapshot,
        source_profile: dict[str, Any],
        retrieval_context: dict[str, Any],
        user_message: str,
        language: str,
        turn_policy,
        attachments: list[dict[str, object]],
        requested_skills: list[str],
        stream_emit: Callable[[dict[str, Any]], None] | None,
    ):
        return build_learning_turn_request(
            session_id=session.session_id,
            user_message=user_message,
            project_id=project.project_id,
            project_title=project.title,
            language=language,
            turn_mode=board.current_turn_mode,
            board_facts=board,
            turn_policy=turn_policy,
            anchor=project.anchor,
            source_references=[{"source_ref": item} for item in (session.source_refs or project.source_refs)],
            memory_references=session.memory_refs or project.memory_refs,
            retrieval_bundle=retrieval_context["retrieval_bundle"],
            state_projection=snapshot,
            continuation_prompt=session.continuation_prompt,
            enabled_tools=turn_policy.enabled_tools or turn_policy.allowed_tools,
            attachments=attachments,
            requested_skills=requested_skills,
            stream_emit=stream_emit,
            metadata=self._build_turn_request_metadata(
                source_profile=source_profile,
                retrieval_context=retrieval_context,
            ),
        )

    def _build_turn_request_metadata(
        self,
        *,
        source_profile: dict[str, Any],
        retrieval_context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "turn_id": str(uuid4()),
            "source_profile": dict(source_profile),
            "retrieval_focus": retrieval_context["retrieval_focus"],
            "retrieval_query_context": retrieval_context["retrieval_query_context"],
            "retrieval_reason": retrieval_context["retrieval_reason"],
            "prefetched_references": retrieval_context["prefetched_references"],
            "parallel_support": retrieval_context["parallel_support"],
            "prompt_support_bundle": retrieval_context["prompt_support_bundle"],
            "workspace": str(getattr(self.executor, "workspace", None) or colearn_nanobot_workspace()),
        }

    def _execute_turn(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        request,
        snapshot,
        turn_policy,
    ) -> tuple[Any, Any]:
        prepared_request = before_turn(
            request=request,
            snapshot=snapshot,
            decision=turn_policy,
        )
        compressed = self.runtime_compression.compress(request=prepared_request)
        result = self.executor.run_turn(request=compressed.request)
        closure_payload = build_learning_closure(
            project=project,
            session=session,
            request=compressed.request,
            final_text=result.final_text,
            raw_learning_result=result.raw_learning_result,
            warnings=[
                *list(result.warnings),
                *compressed.notes,
            ],
        )
        normalized = self.executor.finalize(
            request=compressed.request,
            final_text=result.final_text,
            learning_result=closure_payload,
        )
        return compressed, normalized

    def _enrich_turn_result(
        self,
        *,
        request,
        result,
        retrieval_context: dict[str, Any],
    ) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        retrieval_evidence_map = build_retrieval_evidence_map(
            board=request.board_facts,
            prefetched_references=retrieval_context["prefetched_references"],
            prompt_support_bundle=retrieval_context["prompt_support_bundle"],
        )
        retrieval_hits, retrieval_misses, retrieval_evidence_map = self._build_retrieval_writeback(
            request=request,
            retrieval_focus=retrieval_context["retrieval_focus"],
            retrieval_evidence_map=retrieval_evidence_map,
        )
        runtime_v2 = dict((result.raw_learning_result or {}).get("runtime_v2") or {})
        runtime_v2["retrieval"] = self._build_runtime_retrieval_payload(
            board=request.board_facts,
            retrieval_context=retrieval_context,
            retrieval_hits=retrieval_hits,
            retrieval_misses=retrieval_misses,
            retrieval_evidence_map=retrieval_evidence_map,
        )
        runtime_v2["parallel_support"] = retrieval_context["parallel_support"]
        enriched_learning_result = {
            **dict(result.raw_learning_result or {}),
            "retrieval_hits": retrieval_hits,
            "retrieval_misses": retrieval_misses,
            "retrieval_evidence_map": retrieval_evidence_map,
            "prompt_support_bundle": retrieval_context["prompt_support_bundle"],
            "retrieval_query_context": retrieval_context["retrieval_query_context"],
            "runtime_v2": runtime_v2,
        }
        return (
            replace(result, raw_learning_result=enriched_learning_result),
            retrieval_hits,
            retrieval_misses,
            retrieval_evidence_map,
        )

    def _build_runtime_retrieval_payload(
        self,
        *,
        board,
        retrieval_context: dict[str, Any],
        retrieval_hits: list[dict[str, Any]],
        retrieval_misses: list[dict[str, Any]],
        retrieval_evidence_map: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        return {
            "prefetched_references": retrieval_context["prefetched_references"],
            "prompt_support_bundle": retrieval_context["prompt_support_bundle"],
            "retrieval_focus": retrieval_context["retrieval_focus"],
            "retrieval_query_context": retrieval_context["retrieval_query_context"],
            "retrieval_reason": retrieval_context["retrieval_reason"],
            "retrieval_hits": retrieval_hits,
            "retrieval_misses": retrieval_misses,
            "retrieval_evidence_map": retrieval_evidence_map,
            "knowledge_support_summary": {
                "active_node_id": board.current_progress.active_node_id,
                "critical_blockers": [blocker.id for blocker in board.gaps_and_blockers.critical_blockers],
                "evidence_ref_count": len(board.evidence_refs or []),
                "retrieval_hit_count": len(retrieval_hits),
            },
            "blocker_support_refs": {
                blocker.id: list(retrieval_evidence_map.get(blocker.id, []))
                for blocker in board.gaps_and_blockers.critical_blockers
            },
            "continuation_retrieval_hint": {
                "active_node_id": board.current_progress.active_node_id,
                "evidence_refs": list(board.evidence_refs or []),
                "retrieval_focus": retrieval_context["retrieval_focus"],
                "retrieval_query_context": retrieval_context["retrieval_query_context"],
            },
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

    def _prefetched_references_from_parallel_support(self, parallel_support: dict[str, Any]) -> list[dict[str, Any]]:
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

        Must be called from a sync context (guarded by `_reject_sync_inside_event_loop`).
        Failure semantics are *partial*: one failing query yields status='partial', not
        a hard error, so the turn can still proceed with whatever evidence was gathered.
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
        except Exception as exc:
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
        except Exception as exc:
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

    def _attach_retrieval_metadata(
        self,
        request,
        *,
        retrieval_focus: dict[str, Any],
        retrieval_query_context: dict[str, Any],
        retrieval_reason: str,
        prefetched_references: list[dict[str, Any]],
        parallel_support: dict[str, Any],
        prompt_support_bundle: list[dict[str, Any]],
        retrieval_hits: list[dict[str, Any]],
        retrieval_misses: list[dict[str, Any]],
        retrieval_evidence_map: dict[str, list[dict[str, Any]]],
    ):
        return replace(
            request,
            metadata={
                **dict(request.metadata or {}),
                "retrieval_focus": retrieval_focus,
                "retrieval_query_context": retrieval_query_context,
                "retrieval_reason": retrieval_reason,
                "prefetched_references": prefetched_references,
                "parallel_support": parallel_support,
                "prompt_support_bundle": prompt_support_bundle,
                "retrieval_hits": retrieval_hits,
                "retrieval_misses": retrieval_misses,
                "retrieval_evidence_map": retrieval_evidence_map,
            },
        )

    def _build_retrieval_writeback(
        self,
        *,
        request,
        retrieval_focus: dict[str, Any],
        retrieval_evidence_map: dict[str, list[dict[str, Any]]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        evidence_map = {key: list(value or []) for key, value in retrieval_evidence_map.items()}
        hits: list[dict[str, Any]] = []
        misses: list[dict[str, Any]] = []
        board = request.board_facts
        active_node_id = str(board.current_progress.active_node_id or "").strip()
        blocker_ids = [str(item.id or "").strip() for item in board.gaps_and_blockers.critical_blockers if str(item.id or "").strip()]
        ordered_keys = [active_node_id, *blocker_ids]
        for key in ordered_keys:
            for item in evidence_map.get(key, []):
                if item not in hits:
                    hits.append(item)
        if not hits:
            for key, values in evidence_map.items():
                if str(key).startswith("chunk:"):
                    continue
                for item in values:
                    if item not in hits:
                        hits.append(item)
        if not hits:
            misses.append(
                {
                    "reason": "no_prefetched_references",
                    "retrieval_focus": retrieval_focus,
                }
            )
        ordered_evidence_map: dict[str, list[dict[str, Any]]] = {}
        for key in [*ordered_keys, *sorted(k for k in evidence_map.keys() if k.startswith("chunk:"))]:
            if key in evidence_map:
                ordered_evidence_map[key] = list(evidence_map[key])
        for key in sorted(k for k in evidence_map.keys() if k not in ordered_evidence_map):
            ordered_evidence_map[key] = list(evidence_map[key])
        return hits, misses, ordered_evidence_map

    def _build_last_turn_result(
        self,
        *,
        request,
        result,
        warnings: list[str],
        base_version: int,
        include_product_compression: bool,
    ) -> dict[str, Any]:
        payload = self._build_retrieval_result_fields(
            request=request,
            result=result,
        )
        last_turn_result = {
            "final_text": result.final_text,
            "warnings": warnings,
            "board_patch": result.board_patch,
            "tool_events": list(result.tool_events),
            "stream_events": list(result.stream_events),
            **payload,
            "turn_mode_before": result.turn_mode_before,
            "turn_mode_after": result.turn_mode_after,
            "base_board_version": int(getattr(request.board_facts, "board_version", base_version) or 1),
            "resolved_board_version": int(getattr(result.board_after, "board_version", base_version) or 1),
        }
        if include_product_compression:
            last_turn_result["product_compression"] = {
                "status": "scheduled",
                "started_at": None,
                "finished_at": None,
                "error": "",
                "base_board_version": int(base_version or 1),
            }
        return last_turn_result

    def _build_retrieval_result_fields(
        self,
        *,
        request,
        result,
    ) -> dict[str, Any]:
        runtime_v2 = dict((result.raw_learning_result or {}).get("runtime_v2") or {})
        retrieval_payload = dict(runtime_v2.get("retrieval") or {})
        return {
            "raw_learning_result": dict(result.raw_learning_result or {}),
            "runtime_v2": runtime_v2,
            "prompt_support_bundle": list(
                retrieval_payload.get("prompt_support_bundle")
                or (result.raw_learning_result or {}).get("prompt_support_bundle")
                or []
            ),
            "retrieval_query_context": dict(
                retrieval_payload.get("retrieval_query_context")
                or (result.raw_learning_result or {}).get("retrieval_query_context")
                or {}
            ),
            "knowledge_support_summary": dict(
                retrieval_payload.get("knowledge_support_summary")
                or (result.raw_learning_result or {}).get("knowledge_support_summary")
                or {}
            ),
            "blocker_support_refs": dict(
                retrieval_payload.get("blocker_support_refs")
                or (result.raw_learning_result or {}).get("blocker_support_refs")
                or {}
            ),
            "continuation_retrieval_hint": dict(
                retrieval_payload.get("continuation_retrieval_hint")
                or (result.raw_learning_result or {}).get("continuation_retrieval_hint")
                or {}
            ),
            "retrieval_hits": list(
                retrieval_payload.get("retrieval_hits")
                or (result.raw_learning_result or {}).get("retrieval_hits")
                or []
            ),
            "retrieval_misses": list(
                retrieval_payload.get("retrieval_misses")
                or (result.raw_learning_result or {}).get("retrieval_misses")
                or []
            ),
            "retrieval_evidence_map": dict(
                retrieval_payload.get("retrieval_evidence_map")
                or (result.raw_learning_result or {}).get("retrieval_evidence_map")
                or {}
            ),
            "writeback_envelope": dict((result.raw_learning_result or {}).get("writeback_envelope") or {}),
        }

    def _get_or_create_session(
        self,
        *,
        session_id: str,
        project_id: str,
    ) -> LearningSession:
        session = self.session_store.get_session(session_id)
        if session is None:
            session = self.session_store.create_session(
                session_id=session_id,
                project_id=project_id,
                title="",
            )
        return session

    def _get_or_create_project(
        self,
        *,
        project_id: str,
        session: LearningSession,
    ) -> LearningProject:
        resolved_project_id = project_id or session.project_id or "default-project"
        project = self.project_service.get_project(resolved_project_id)
        if project is None:
            project = self.project_service.create_project(
                resolved_project_id,
                title=resolved_project_id,
            )
        session.project_id = resolved_project_id
        return project

    def _write_back(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        request,
        result,
    ) -> None:
        """Persist turn output with board-version conflict protection.

        Rejects writes whose `board_before.board_version` is older than the current
        session board — protects concurrent turns / background finalizers from
        clobbering newer state. The dropped result still emits a warning in `warnings`.
        """
        # Session Board is the runtime source of truth; project.board_facts is a
        # denormalized mirror for project lists and cross-session recovery.
        current_session = self.session_store.get_session(session.session_id)
        current_session_version = int(getattr(current_session, "board_version", session.board_version) or 1)
        base_version = int(getattr(request.board_facts, "board_version", session.board_version) or 1)
        session_conflict = current_session_version > base_version and current_session is not session
        if session_conflict and current_session is not None:
            session = current_session
        session.turn_mode = result.turn_mode_after
        warnings = list(result.warnings)
        if session_conflict:
            warnings.append("board_version_conflict_session_write_skipped")
        else:
            session.board_facts = dict(result.board_after.to_dict())
            session.board_version = int(result.board_after.board_version or 1)
        session.status = "completed"
        session.active_turn_id = None
        session.active_turns = []
        session.continuation_prompt = result.continuation_prompt
        session.last_turn_result = self._build_last_turn_result(
            request=request,
            result=result,
            warnings=warnings,
            base_version=base_version,
            include_product_compression=True,
        )
        session.messages.extend(
            [
                {"role": "user", "content": request.user_message},
                {"role": "assistant", "content": result.final_text},
            ]
        )
        current_project = self.project_service.get_project(project.project_id)
        current_project_version = int(getattr(current_project, "board_version", project.board_version) or 1)
        project_conflict = current_project_version > base_version and current_project is not project
        if project_conflict and current_project is not None:
            project = current_project
        project.turn_mode = result.turn_mode_after
        if project_conflict:
            warnings.append("board_version_conflict_project_write_skipped")
        else:
            project.board_facts = dict(result.board_after.to_dict())
            project.board_version = int(result.board_after.board_version or 1)
        session.last_turn_result = self._build_last_turn_result(
            request=request,
            result=result,
            warnings=warnings,
            base_version=base_version,
            include_product_compression=True,
        )
        project.anchor_status = "ready" if project.anchor else "missing"
        project.current_main_goal = (
            request.turn_policy.main_goal if request.turn_policy else project.current_main_goal
        )
        project.retrieval_profile = {
            **project.retrieval_profile,
            "last_stream_events": list(result.stream_events),
            "last_tool_events": list(result.tool_events),
            "board": dict(project.board_facts or result.board_after.to_dict()),
        }
        for item in result.memory_events:
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind=str(item.get("kind") or "event"),
                    payload=dict(item.get("payload") or {}),
                )
            )
        # P2: Persist learning_events (incl. signal_extractor output) to event store
        for item in result.learning_events:
            if hasattr(item, "event_id"):
                self.memory_store.append(item)
            elif isinstance(item, dict) and item.get("kind"):
                self.memory_store.append(
                    MemoryEvent(
                        event_id=str(item.get("event_id") or uuid4()),
                        kind=str(item["kind"]),
                        payload=dict(item.get("payload") or {}),
                    )
                )
        # P1: Record board_patch application as event for consolidation input
        board_patch = result.board_patch
        if board_patch and not session_conflict:
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind="board_patch_applied",
                    payload={
                        "session_id": session.session_id,
                        "project_id": project.project_id,
                        "patch_keys": list(board_patch.keys()),
                        "board_version": int(result.board_after.board_version or 1),
                    },
                )
            )
        self._append_nanobot_history(project=project, session=session, result=result)
        self._maybe_compact_session(session)
        self._maybe_consolidate_memory(project, session, result)
        self._maybe_derive_board_snapshot(project=project, session=session, result=result)
        if not session.source_refs and project.source_refs:
            session.source_refs = list(project.source_refs)
        self.session_store.save_session(session)
        self.project_service.save_project(project)

    def _maybe_compact_session(self, session: LearningSession) -> None:
        max_messages = self.SESSION_AUTOCOMPACT_MAX_MESSAGES
        if len(session.messages) <= max_messages:
            return
        keep_tail = session.messages[-self.SESSION_AUTOCOMPACT_KEEP_TAIL :]
        old_messages = session.messages[:-self.SESSION_AUTOCOMPACT_KEEP_TAIL]
        summary, source = self._archive_compacted_messages(old_messages)
        session.messages = [
            {
                "role": "system",
                "content": f"[compacted history] {summary}",
                "metadata": {
                    "colearn_compacted": True,
                    "compacted_count": len(old_messages),
                    "compaction_source": source,
                },
            },
            *keep_tail,
        ]

    def _maybe_consolidate_memory(self, project: LearningProject, session: LearningSession, result) -> None:
        event_count = len(self.memory_store.list_events())
        if event_count == 0 or event_count % self.DREAM_CONSOLIDATION_EVENT_INTERVAL != 0:
            return
        loop = self._runtime_loop()
        dream = getattr(loop, "dream", None) if loop is not None else None
        if dream is None or not hasattr(dream, "run"):
            summary = self._consolidate_dream_events(
                project=project,
                session=session,
                recent_events=self.memory_store.list_events()[-self.DREAM_CONSOLIDATION_EVENT_INTERVAL :],
                fallback_text=result.review_summary or result.final_text,
            )
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind="profile_consolidated",
                    payload=summary,
                )
            )
            return
        try:
            did_work = self._run_async_or_value(dream.run())
            if not did_work:
                return
            store = getattr(dream, "store", None) or getattr(getattr(loop, "context", None), "memory", None)
            memory_excerpt = self._memory_excerpt(store)
            dream_cursor = (
                store.get_last_dream_cursor()
                if store is not None and hasattr(store, "get_last_dream_cursor")
                else None
            )
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind="profile_consolidated",
                    payload={
                        "source": "nanobot_dream",
                        "session_id": session.session_id,
                        "project_id": project.project_id,
                        "dream_cursor": dream_cursor,
                        "memory_excerpt": memory_excerpt,
                        "recent_event_count": self.DREAM_CONSOLIDATION_EVENT_INTERVAL,
                    },
                )
            )
        except Exception as exc:
            warning = f"dream_consolidation_failed:{type(exc).__name__}"
            self._append_session_warning(session, warning)
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind="profile_consolidation_failed",
                    payload={
                        "source": "nanobot_dream",
                        "session_id": session.session_id,
                        "project_id": project.project_id,
                        "error": str(exc),
                    },
                )
            )

    def _maybe_derive_board_snapshot(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        result,
    ) -> None:
        """Q3: Periodically re-derive BoardFacts from event stream via LLM.

        Runs synchronously after writeback. If board_deriver is None (default),
        no-op — preserves backward compat. On success, overwrites session.board_facts
        and emits board_snapshot_derived event for audit.
        """
        if self.board_deriver is None:
            return
        session_events = self.memory_store.list_events_for_session(session.session_id)
        if len(session_events) == 0 or len(session_events) % self.BOARD_DERIVATION_EVENT_INTERVAL != 0:
            return
        from colearn.learning.state_hooks import build_learning_board

        current_board = build_learning_board(session=session, project=project)
        project_summary = (
            f"{project.title}: anchor={project.anchor or {}}; "
            f"sources={len(project.source_refs or [])}"
        )
        try:
            new_board, diff = self.board_deriver.derive_snapshot(
                events=session_events,
                current_board=current_board,
                project_summary=project_summary,
            )
        except Exception as exc:
            logger.warning("board_deriver.derive_snapshot raised: %s", exc)
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind="board_snapshot_failed",
                    payload={
                        "session_id": session.session_id,
                        "project_id": project.project_id,
                        "error": str(exc),
                    },
                )
            )
            return

        if diff.get("status") != "ok":
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind="board_snapshot_failed",
                    payload={
                        "session_id": session.session_id,
                        "project_id": project.project_id,
                        "diff_status": diff.get("status"),
                    },
                )
            )
            return

        session.board_facts = new_board.to_dict()
        session.board_version = int(new_board.board_version or 1)
        self.session_store.save_session(session)
        self.memory_store.append(
            MemoryEvent(
                event_id=str(uuid4()),
                kind="board_snapshot_derived",
                payload={
                    "session_id": session.session_id,
                    "project_id": project.project_id,
                    "board_version": int(new_board.board_version or 1),
                    "event_count": diff.get("event_count", 0),
                    "changes": diff.get("changes", {}),
                },
            )
        )

    def _build_compaction_summary(self, messages: list[dict[str, Any]]) -> str:
        summary = " | ".join(
            str(item.get("content") or "").strip()
            for item in messages
            if str(item.get("content") or "").strip()
        )
        return summary[: self.SESSION_AUTOCOMPACT_SUMMARY_MAX_CHARS]

    def _archive_compacted_messages(self, messages: list[dict[str, Any]]) -> tuple[str, str]:
        loop = self._runtime_loop()
        consolidator = getattr(loop, "consolidator", None) if loop is not None else None
        if consolidator is not None and hasattr(consolidator, "archive"):
            try:
                summary = self._run_async_or_value(consolidator.archive(messages))
                if summary:
                    return str(summary)[: self.SESSION_AUTOCOMPACT_SUMMARY_MAX_CHARS], "nanobot_consolidator"
            except (RuntimeError, TypeError, ValueError) as exc:
                logger.warning("consolidator.archive failed: %s", exc)
        return self._build_compaction_summary(messages), "fallback"

    def _runtime_loop(self):
        get_bot = getattr(self.executor, "_get_bot", None)
        if not callable(get_bot):
            return None
        try:
            bot = get_bot()
        except (RuntimeError, AttributeError, TypeError) as exc:
            logger.debug("_runtime_loop: get_bot failed: %s", exc)
            return None
        return getattr(bot, "_loop", None)

    def _run_async_or_value(self, value):
        if asyncio.iscoroutine(value):
            return asyncio.run(value)
        return value

    def _append_nanobot_history(self, *, project: LearningProject, session: LearningSession, result) -> None:
        loop = self._runtime_loop()
        store = getattr(getattr(loop, "context", None), "memory", None) if loop is not None else None
        if store is None or not hasattr(store, "append_history"):
            return
        try:
            store.append_history(
                self._nanobot_history_entry(project=project, session=session, result=result),
                max_chars=4000,
            )
        except Exception:
            self._append_session_warning(session, "nanobot_history_append_failed")

    def _nanobot_history_entry(self, *, project: LearningProject, session: LearningSession, result) -> str:
        blockers = [
            str(getattr(item, "desc", "") or getattr(item, "id", "") or "").strip()
            for item in list(getattr(result.board_after.gaps_and_blockers, "critical_blockers", []) or [])
        ]
        runtime_v2 = dict((result.raw_learning_result or {}).get("runtime_v2") or {})
        retrieval = dict(runtime_v2.get("retrieval") or {})
        return "\n".join(
            [
                f"session_id: {session.session_id}",
                f"project_id: {project.project_id}",
                f"turn_mode: {result.turn_mode_after}",
                f"user: {self._truncate_for_memory(session.messages[-2].get('content') if len(session.messages) >= 2 else '')}",
                f"assistant: {self._truncate_for_memory(result.final_text)}",
                f"blockers: {'; '.join(blockers) if blockers else 'none'}",
                f"retrieval: hits={len(retrieval.get('retrieval_hits') or [])}; misses={len(retrieval.get('retrieval_misses') or [])}",
            ]
        )

    @staticmethod
    def _truncate_for_memory(value: Any, limit: int = 600) -> str:
        text = str(value or "").strip().replace("\n", " ")
        return text[:limit]

    @staticmethod
    def _memory_excerpt(store: Any, limit: int = 1200) -> str:
        if store is None or not hasattr(store, "read_memory"):
            return ""
        return str(store.read_memory() or "").strip()[:limit]

    @staticmethod
    def _append_session_warning(session: LearningSession, warning: str) -> None:
        last_turn_result = dict(session.last_turn_result or {})
        warnings = list(last_turn_result.get("warnings") or [])
        if warning not in warnings:
            warnings.append(warning)
        last_turn_result["warnings"] = warnings
        session.last_turn_result = last_turn_result

    def _consolidate_dream_events(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        recent_events: list[MemoryEvent],
        fallback_text: str,
    ) -> dict[str, Any]:
        facts = [
            str(event.payload.get("summary") or event.payload.get("content") or event.kind).strip()
            for event in recent_events
            if str(event.payload.get("summary") or event.payload.get("content") or event.kind).strip()
        ]
        combined = " | ".join(facts) or fallback_text[:240]
        return {
            "summary": combined[:240],
            "session_id": session.session_id,
            "project_id": project.project_id,
            "source": "dream_consolidation",
            "recent_event_count": len(recent_events),
            "recent_event_kinds": [event.kind for event in recent_events],
        }

    def apply_background_result(
        self,
        *,
        session_id: str,
        project_id: str,
        request,
        board,
        product_output: ProductCompressionResult | None,
        error: BaseException | None,
        status_payload: dict[str, Any],
    ) -> None:
        session = self.session_store.get_session(session_id)
        project = self.project_service.get_project(project_id)
        if session is None or project is None:
            return

        last_turn_result = dict(session.last_turn_result or {})
        warnings = list(last_turn_result.get("warnings") or [])
        if error is not None:
            warning = f"product_compression_failed: {error}"
            if warning not in warnings:
                warnings.append(warning)
            last_turn_result["warnings"] = warnings
            last_turn_result["product_compression"] = {
                **status_payload,
                "status": "failed",
                "finished_at": int(time()),
                "error": str(error),
            }
            session.last_turn_result = last_turn_result
            self.session_store.save_session(session)
            return

        if product_output is None:
            return
        stale_board = int(session.board_version or 1) > int(board.board_version or 1) + 1
        if stale_board and "product_compression_stale_board_skipped" not in warnings:
            warnings.append("product_compression_stale_board_skipped")
        pending_review = {
            "summary": product_output.review_summary,
            "points": [request.policy_decision.main_goal] if request.policy_decision else [],
            "confusion_points": list(request.policy_decision.review_focus or []) if request.policy_decision else [],
            "status": "ready",
        }
        session.continuation_prompt = product_output.continuation_prompt
        session.pending_review = pending_review
        last_turn_result["warnings"] = warnings
        last_turn_result["product_compression"] = {
            **status_payload,
            "status": "completed",
            "finished_at": int(time()),
            "error": "",
            "stale_board": stale_board,
            "review_summary": product_output.review_summary,
            "continuation_prompt": product_output.continuation_prompt,
        }
        session.last_turn_result = last_turn_result
        project.latest_review = dict(pending_review)
        self.session_store.save_session(session)
        self.project_service.save_project(project)
