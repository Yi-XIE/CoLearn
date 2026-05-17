"""Main assembly entrypoint for a single CoLearn learning turn."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from threading import Thread
from time import time
from typing import Any, Callable
from uuid import uuid4

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
from colearn.projects.models import LearningProject
from colearn.projects.service import LearningProjectService
from colearn.retrieval.service import RetrievalService
from colearn.runtime_v2.context_bridge import build_learning_turn_request
from colearn.runtime_v2.executor import NanobotTurnExecutor
from colearn.runtime_v2 import build_learning_closure
from colearn.sessions.store import LearningSession, SessionStore
from .source_preflight import SourceReadinessPreflight


class BackgroundTurnFinalizer:
    def __init__(
        self,
        *,
        product_compression: ProductCompressionBridge,
        on_result: Callable[..., None],
    ) -> None:
        self.product_compression = product_compression
        self.on_result = on_result

    def schedule(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        board,
        request,
        result,
    ) -> None:
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
        worker.start()

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
            workspace=Path.cwd(),
            retrieval_service=self.retrieval_service,
            memory_store=self.memory_store,
        )
        self.runtime_compression = runtime_compression or RuntimeCompressionBridge()
        self.product_compression = product_compression or ProductCompressionBridge()
        self.background_finalizer = BackgroundTurnFinalizer(
            product_compression=self.product_compression,
            on_result=self.apply_background_result,
        )

    def run_turn(
        self,
        *,
        session_id: str,
        user_message: str,
        project_id: str = "",
        language: str = "zh",
        attachments: list[dict[str, object]] | None = None,
    ):
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
        prefetch_bundle = self.retrieval_service.build_bundle(
            project=project,
            session=session,
            query=str(retrieval_query_context.get("final_query") or retrieval_focus.get("default_query") or user_message or ""),
            libraries=None,
        )
        prefetched_references = self._prefetched_references_from_bundle(prefetch_bundle)
        prompt_support_bundle = build_prompt_support_bundle(
            board=board,
            prefetched_references=prefetched_references,
            retrieval_focus=retrieval_focus,
        )
        retrieval_bundle = prefetch_bundle
        project.retrieval_profile = {
            **project.retrieval_profile,
            **source_profile,
            "board": board.to_dict(),
            "retrieval_focus": retrieval_focus,
            "retrieval_query_context": retrieval_query_context,
            "retrieval_reason": retrieval_reason,
            "prefetched_references": prefetched_references,
            "prompt_support_bundle": prompt_support_bundle,
            "prefetch_bundle": {
                "query": prefetch_bundle.query,
                "retrieval_status": prefetch_bundle.retrieval_status,
                "fallback_reason": prefetch_bundle.fallback_reason,
                "warnings": list(prefetch_bundle.warnings or []),
            },
        }
        turn_policy = policy(
            board=board,
            user_message=user_message,
        )
        request = build_learning_turn_request(
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
            retrieval_bundle=retrieval_bundle,
            state_projection=snapshot,
            continuation_prompt=session.continuation_prompt,
            enabled_tools=turn_policy.enabled_tools or turn_policy.allowed_tools,
            attachments=attachments or [],
            metadata={
                "turn_id": str(uuid4()),
                "source_profile": dict(source_profile),
                "retrieval_focus": retrieval_focus,
                "retrieval_query_context": retrieval_query_context,
                "retrieval_reason": retrieval_reason,
                "prefetched_references": prefetched_references,
                "prompt_support_bundle": prompt_support_bundle,
                "workspace": str(getattr(self.executor, "workspace", None) or Path.cwd()),
            },
        )
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
        retrieval_evidence_map = build_retrieval_evidence_map(
            board=compressed.request.board_facts,
            prefetched_references=prefetched_references,
            prompt_support_bundle=prompt_support_bundle,
        )
        retrieval_hits, retrieval_misses, retrieval_evidence_map = self._build_retrieval_writeback(
            request=compressed.request,
            result=normalized,
            retrieval_focus=retrieval_focus,
            prefetched_references=prefetched_references,
            retrieval_evidence_map=retrieval_evidence_map,
        )
        enriched_learning_result = {
            **dict(normalized.raw_learning_result or {}),
            "retrieval_hits": retrieval_hits,
            "retrieval_misses": retrieval_misses,
            "retrieval_evidence_map": retrieval_evidence_map,
            "prompt_support_bundle": prompt_support_bundle,
            "retrieval_query_context": retrieval_query_context,
        }
        runtime_v2 = dict(enriched_learning_result.get("runtime_v2") or {})
        runtime_v2["retrieval"] = {
            "prefetched_references": prefetched_references,
            "prompt_support_bundle": prompt_support_bundle,
            "retrieval_focus": retrieval_focus,
            "retrieval_query_context": retrieval_query_context,
            "retrieval_reason": retrieval_reason,
            "retrieval_hits": retrieval_hits,
            "retrieval_misses": retrieval_misses,
            "retrieval_evidence_map": retrieval_evidence_map,
            "knowledge_support_summary": {
                "active_node_id": compressed.request.board_facts.current_progress.active_node_id,
                "critical_blockers": [
                    blocker.id for blocker in compressed.request.board_facts.gaps_and_blockers.critical_blockers
                ],
                "evidence_ref_count": len(compressed.request.board_facts.evidence_refs or []),
                "retrieval_hit_count": len(retrieval_hits),
            },
            "blocker_support_refs": {
                blocker.id: list(retrieval_evidence_map.get(blocker.id, []))
                for blocker in compressed.request.board_facts.gaps_and_blockers.critical_blockers
            },
            "continuation_retrieval_hint": {
                "active_node_id": compressed.request.board_facts.current_progress.active_node_id,
                "evidence_refs": list(compressed.request.board_facts.evidence_refs or []),
                "retrieval_focus": retrieval_focus,
                "retrieval_query_context": retrieval_query_context,
            },
        }
        enriched_learning_result["runtime_v2"] = runtime_v2
        normalized = replace(normalized, raw_learning_result=enriched_learning_result)
        self._write_back(
            project=project,
            session=session,
            request=self._attach_retrieval_metadata(
                compressed.request,
                retrieval_focus=retrieval_focus,
                retrieval_query_context=retrieval_query_context,
                retrieval_reason=retrieval_reason,
                prefetched_references=prefetched_references,
                prompt_support_bundle=prompt_support_bundle,
                retrieval_hits=retrieval_hits,
                retrieval_misses=retrieval_misses,
                retrieval_evidence_map=retrieval_evidence_map,
            ),
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

    def _attach_retrieval_metadata(
        self,
        request,
        *,
        retrieval_focus: dict[str, Any],
        retrieval_query_context: dict[str, Any],
        retrieval_reason: str,
        prefetched_references: list[dict[str, Any]],
        prompt_support_bundle: list[dict[str, Any]],
        retrieval_hits: list[dict[str, Any]],
        retrieval_misses: list[dict[str, Any]],
        retrieval_evidence_map: dict[str, list[dict[str, Any]]],
    ):
        return request.__class__(
            **{
                **request.__dict__,
                "metadata": {
                    **dict(request.metadata or {}),
                    "retrieval_focus": retrieval_focus,
                    "retrieval_query_context": retrieval_query_context,
                    "retrieval_reason": retrieval_reason,
                    "prefetched_references": prefetched_references,
                    "prompt_support_bundle": prompt_support_bundle,
                    "retrieval_hits": retrieval_hits,
                    "retrieval_misses": retrieval_misses,
                    "retrieval_evidence_map": retrieval_evidence_map,
                },
            }
        )

    def _build_retrieval_writeback(
        self,
        *,
        request,
        result,
        retrieval_focus: dict[str, Any],
        prefetched_references: list[dict[str, Any]],
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
        session.last_turn_result = {
            "final_text": result.final_text,
            "warnings": warnings,
            "board_patch": result.board_patch,
            "tool_events": list(result.tool_events),
            "stream_events": list(result.stream_events),
            "raw_learning_result": dict(result.raw_learning_result or {}),
            "runtime_v2": dict((result.raw_learning_result or {}).get("runtime_v2") or {}),
            "prompt_support_bundle": list(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "prompt_support_bundle"
                )
                or (result.raw_learning_result or {}).get("prompt_support_bundle")
                or []
            ),
            "retrieval_query_context": dict(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "retrieval_query_context"
                )
                or (result.raw_learning_result or {}).get("retrieval_query_context")
                or {}
            ),
            "knowledge_support_summary": dict(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "knowledge_support_summary"
                )
                or (result.raw_learning_result or {}).get("knowledge_support_summary")
                or {}
            ),
            "blocker_support_refs": dict(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "blocker_support_refs"
                )
                or (result.raw_learning_result or {}).get("blocker_support_refs")
                or {}
            ),
            "continuation_retrieval_hint": dict(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "continuation_retrieval_hint"
                )
                or (result.raw_learning_result or {}).get("continuation_retrieval_hint")
                or {}
            ),
            "retrieval_hits": list(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get("retrieval_hits")
                or (result.raw_learning_result or {}).get("retrieval_hits")
                or []
            ),
            "retrieval_misses": list(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get("retrieval_misses")
                or (result.raw_learning_result or {}).get("retrieval_misses")
                or []
            ),
            "retrieval_evidence_map": dict(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "retrieval_evidence_map"
                )
                or (result.raw_learning_result or {}).get("retrieval_evidence_map")
                or {}
            ),
            "writeback_envelope": dict((result.raw_learning_result or {}).get("writeback_envelope") or {}),
            "turn_mode_before": result.turn_mode_before,
            "turn_mode_after": result.turn_mode_after,
            "base_board_version": int(getattr(request.board_facts, "board_version", session.board_version) or 1),
            "resolved_board_version": int(getattr(result.board_after, "board_version", session.board_version) or 1),
            "product_compression": {
                "status": "scheduled",
                "started_at": None,
                "finished_at": None,
                "error": "",
                "base_board_version": int(base_version or 1),
            },
        }
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
        session.last_turn_result = {
            **session.last_turn_result,
            "warnings": warnings,
            "raw_learning_result": dict(result.raw_learning_result or {}),
            "runtime_v2": dict((result.raw_learning_result or {}).get("runtime_v2") or {}),
            "prompt_support_bundle": list(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "prompt_support_bundle"
                )
                or (result.raw_learning_result or {}).get("prompt_support_bundle")
                or []
            ),
            "retrieval_query_context": dict(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "retrieval_query_context"
                )
                or (result.raw_learning_result or {}).get("retrieval_query_context")
                or {}
            ),
            "knowledge_support_summary": dict(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "knowledge_support_summary"
                )
                or (result.raw_learning_result or {}).get("knowledge_support_summary")
                or {}
            ),
            "blocker_support_refs": dict(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "blocker_support_refs"
                )
                or (result.raw_learning_result or {}).get("blocker_support_refs")
                or {}
            ),
            "continuation_retrieval_hint": dict(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "continuation_retrieval_hint"
                )
                or (result.raw_learning_result or {}).get("continuation_retrieval_hint")
                or {}
            ),
            "retrieval_hits": list(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get("retrieval_hits")
                or (result.raw_learning_result or {}).get("retrieval_hits")
                or []
            ),
            "retrieval_misses": list(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get("retrieval_misses")
                or (result.raw_learning_result or {}).get("retrieval_misses")
                or []
            ),
            "retrieval_evidence_map": dict(
                ((result.raw_learning_result or {}).get("runtime_v2") or {}).get("retrieval", {}).get(
                    "retrieval_evidence_map"
                )
                or (result.raw_learning_result or {}).get("retrieval_evidence_map")
                or {}
            ),
            "writeback_envelope": dict((result.raw_learning_result or {}).get("writeback_envelope") or {}),
            "turn_mode_before": result.turn_mode_before,
            "turn_mode_after": result.turn_mode_after,
            "base_board_version": int(getattr(request.board_facts, "board_version", session.board_version) or 1),
            "resolved_board_version": int(getattr(result.board_after, "board_version", session.board_version) or 1),
        }
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
        self._maybe_compact_session(session)
        self._maybe_consolidate_memory(project, session, result)
        if not session.source_refs and project.source_refs:
            session.source_refs = list(project.source_refs)
        self.session_store.save_session(session)
        self.project_service.save_project(project)

    def _maybe_compact_session(self, session: LearningSession) -> None:
        max_messages = self.SESSION_AUTOCOMPACT_MAX_MESSAGES
        if len(session.messages) <= max_messages:
            return
        keep_tail = session.messages[-self.SESSION_AUTOCOMPACT_KEEP_TAIL :]
        summary = self._build_compaction_summary(session.messages[:-self.SESSION_AUTOCOMPACT_KEEP_TAIL])
        session.messages = [
            {"role": "system", "content": f"[compacted history] {summary}"},
            *keep_tail,
        ]

    def _maybe_consolidate_memory(self, project: LearningProject, session: LearningSession, result) -> None:
        event_count = len(self.memory_store.list_events())
        if event_count == 0 or event_count % self.DREAM_CONSOLIDATION_EVENT_INTERVAL != 0:
            return
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

    def _build_compaction_summary(self, messages: list[dict[str, Any]]) -> str:
        summary = " | ".join(
            str(item.get("content") or "").strip()
            for item in messages
            if str(item.get("content") or "").strip()
        )
        return summary[: self.SESSION_AUTOCOMPACT_SUMMARY_MAX_CHARS]

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
