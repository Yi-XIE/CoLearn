"""Main assembly entrypoint for a single CoLearn learning turn."""

from __future__ import annotations

from threading import Thread
from time import time
from typing import Any, Callable

from colearn.logging_config import get_logger

from colearn.compression import ProductCompressionBridge, ProductCompressionResult, RuntimeCompressionBridge
from colearn.knowledge import KnowledgeWorkspaceService
from colearn.memory.store import EventMemoryStore
from colearn.paths import colearn_nanobot_workspace
from colearn.projects.models import LearningProject
from colearn.projects.service import LearningProjectService
from colearn.retrieval.service import RetrievalService
from colearn.runtime_v2.executor import NanobotTurnExecutor
from colearn.sessions.store import LearningSession, SessionStore
from .source_preflight import SourceReadinessPreflight
from .stages import (
    TurnContext,
    PreflightStage,
    RetrievalStage,
    ExecuteStage,
    FinalizeStage,
    WritebackStage,
)

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
        """Spawn a daemon Thread for product compression that may outlive the turn."""
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
    BOARD_DERIVATION_EVENT_INTERVAL = 5

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
        board_deriver: Any = None,
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

        # --- build stages -----------------------------------------------
        self.preflight = PreflightStage(
            project_service=self.project_service,
            session_store=self.session_store,
            retrieval_service=self.retrieval_service,
            knowledge_service=self.knowledge_service,
            source_preflight=self.source_preflight,
        )
        self.retrieval = RetrievalStage(
            retrieval_service=self.retrieval_service,
            knowledge_service=self.knowledge_service,
            runtime_compression=self.runtime_compression,
        )
        self.execute = ExecuteStage(
            executor=self.executor,
            runtime_compression=self.runtime_compression,
        )
        self.finalize = FinalizeStage()
        self.writeback = WritebackStage(
            project_service=self.project_service,
            session_store=self.session_store,
            memory_store=self.memory_store,
            executor=self.executor,
            background_finalizer=self.background_finalizer,
            build_last_turn_result=self.finalize.build_last_turn_result,
            owner=self,
        )

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
        request's event loop. Pipeline: preflight → retrieval → execute → finalize → writeback.
        """
        ctx = TurnContext(
            session_id=session_id,
            project_id=project_id,
            user_message=user_message,
            language=language,
            attachments=list(attachments or []),
            requested_skills=list(requested_skills or []),
            stream_emit=stream_emit,
        )
        ctx = self.preflight.run(ctx)
        ctx = self.retrieval.run(ctx)
        self.preflight.sync_project_retrieval_profile(ctx)
        ctx = self.execute.run(ctx)
        ctx = self.finalize.run(ctx)
        self.writeback.run(ctx)
        return ctx.result

    # ------------------------------------------------------------------
    # Proxy methods — delegate to stages so tests that call private methods
    # on the orchestrator directly continue to work unchanged.
    # ------------------------------------------------------------------
    def _build_parallel_support(self, *, project, session, retrieval_query_context):
        return self.retrieval._build_parallel_support(
            project=project,
            session=session,
            retrieval_query_context=retrieval_query_context,
        )

    def _write_back(self, *, project, session, request, result):
        return self.writeback._write_back(
            project=project,
            session=session,
            request=request,
            result=result,
        )

    def _maybe_compact_session(self, session):
        return self.writeback._maybe_compact_session(session)

    def _maybe_consolidate_memory(self, project, session, result):
        return self.writeback._maybe_consolidate_memory(project, session, result)

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
