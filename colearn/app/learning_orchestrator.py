"""Main assembly entrypoint for a single CoLearn learning turn."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from colearn.logging_config import get_logger

from colearn.config.defaults import Defaults
from colearn.compression import ProductCompressionBridge, RuntimeCompressionBridge
from colearn.knowledge import KnowledgeWorkspaceService
from colearn.api.state import MemoryDocStateService, SettingsStateService
from colearn.learning.board_deriver import BoardSnapshotDeriver
from colearn.learning.response_contract import LearningTurnResult
from colearn.memory.store import EventMemoryStore
from colearn.paths import colearn_nanobot_workspace
from colearn.projects.service import LearningProjectService
from colearn.retrieval.service import RetrievalService
from colearn.runtime_v2.executor import NanobotTurnExecutor, TurnExecutorProtocol
from colearn.sessions.store import SessionStore
from colearn.storage import JsonStateStore
from .background_finalizer import BackgroundTurnFinalizer
from .source_preflight import SourceReadinessPreflight
from .stages import (
    TurnContext,
    PreflightStage,
    PlanStage,
    RetrievalStage,
    ExecuteStage,
    FinalizeStage,
    WritebackStage,
)

logger = get_logger(__name__)


def _infer_state_store(
    *,
    project_service: LearningProjectService | None,
    session_store: SessionStore | None,
    memory_store: EventMemoryStore | None,
) -> JsonStateStore:
    for owner in (project_service, session_store, memory_store):
        store = getattr(owner, "_state_store", None)
        if isinstance(store, JsonStateStore):
            return store
    return JsonStateStore()

class LearningOrchestrator:
    SESSION_AUTOCOMPACT_MAX_MESSAGES = Defaults.SESSION_AUTOCOMPACT_MAX_MESSAGES
    SESSION_AUTOCOMPACT_KEEP_TAIL = Defaults.SESSION_AUTOCOMPACT_KEEP_TAIL
    SESSION_AUTOCOMPACT_SUMMARY_MAX_CHARS = 800
    DREAM_CONSOLIDATION_EVENT_INTERVAL = Defaults.DREAM_CONSOLIDATION_EVENT_INTERVAL
    BOARD_DERIVATION_EVENT_INTERVAL = Defaults.BOARD_DERIVATION_EVENT_INTERVAL

    def __init__(
        self,
        *,
        project_service: LearningProjectService | None = None,
        session_store: SessionStore | None = None,
        memory_store: EventMemoryStore | None = None,
        knowledge_service: KnowledgeWorkspaceService | None = None,
        retrieval_service: RetrievalService | None = None,
        executor: TurnExecutorProtocol | None = None,
        runtime_compression: RuntimeCompressionBridge | None = None,
        product_compression: ProductCompressionBridge | None = None,
        board_deriver: BoardSnapshotDeriver | None = None,
        settings_service: SettingsStateService | None = None,
        memory_doc_service: MemoryDocStateService | None = None,
    ) -> None:
        self.project_service = project_service or LearningProjectService()
        self.session_store = session_store or SessionStore()
        self.memory_store = memory_store or EventMemoryStore()
        shared_state_store = _infer_state_store(
            project_service=self.project_service,
            session_store=self.session_store,
            memory_store=self.memory_store,
        )
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
        self.settings_service = settings_service or SettingsStateService(state_store=shared_state_store)
        self.memory_doc_service = memory_doc_service or MemoryDocStateService(state_store=shared_state_store)
        self.background_finalizer = BackgroundTurnFinalizer(
            product_compression=self.product_compression,
            on_result=lambda **payload: self.writeback.apply_background_result(**payload),
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
        self.plan = PlanStage(retrieval_service=self.retrieval_service)
        self.retrieval = RetrievalStage(
            retrieval_service=self.retrieval_service,
            knowledge_service=self.knowledge_service,
            runtime_compression=self.runtime_compression,
        )
        self.execute = ExecuteStage(
            executor=self.executor,
            runtime_compression=self.runtime_compression,
            settings_service=self.settings_service,
        )
        self.finalize = FinalizeStage()
        self.writeback = WritebackStage(
            project_service=self.project_service,
            session_store=self.session_store,
            memory_store=self.memory_store,
            settings_service=self.settings_service,
            memory_doc_service=self.memory_doc_service,
            executor=self.executor,
            background_finalizer=self.background_finalizer,
            build_last_turn_result=self.finalize.build_last_turn_result,
            owner=self,
        )

    def shutdown(self, timeout: float = 5.0) -> None:
        self.background_finalizer.shutdown(timeout=timeout)

    async def run_turn_async(
        self,
        *,
        session_id: str,
        user_message: str,
        project_id: str = "",
        language: str = "zh",
        attachments: list[dict[str, object]] | None = None,
        requested_skills: list[str] | None = None,
        requested_mode: str | None = None,
        stream_emit: Callable[[dict[str, Any]], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> LearningTurnResult:
        """Async turn entry — the main internal turn pipeline."""
        return await self._run_turn_pipeline(
            session_id=session_id,
            user_message=user_message,
            project_id=project_id,
            language=language,
            attachments=attachments,
            requested_skills=requested_skills,
            requested_mode=requested_mode,
            stream_emit=stream_emit,
            cancel_check=cancel_check,
        )

    async def _run_turn_pipeline(
        self,
        *,
        session_id: str,
        user_message: str,
        project_id: str = "",
        language: str = "zh",
        attachments: list[dict[str, object]] | None = None,
        requested_skills: list[str] | None = None,
        requested_mode: str | None = None,
        stream_emit: Callable[[dict[str, Any]], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> LearningTurnResult:
        ctx = TurnContext(
            session_id=session_id,
            project_id=project_id,
            user_message=user_message,
            language=language,
            attachments=list(attachments or []),
            requested_skills=list(requested_skills or []),
            requested_mode=requested_mode,
            stream_emit=stream_emit,
            cancel_check=cancel_check,
        )
        ctx = await self.preflight.run_async(ctx)
        ctx = self.plan.run(ctx)
        if ctx.session_mode == "learning":
            ctx = self._sync_sustained_goal(ctx)
        else:
            ctx = self._complete_sustained_goal_for_exit(ctx, reason="session_mode:chat")
        if ctx.session_mode == "learning":
            ctx = await self.retrieval.run_async(ctx)
        else:
            ctx = self.retrieval.skip(ctx, reason="session_mode:chat")
        self.preflight.sync_project_retrieval_profile(ctx)
        ctx = await self.execute.run_async(ctx)
        ctx = self.finalize.run(ctx)
        ctx = self._complete_sustained_goal_if_finished(ctx)
        await self.writeback.run_async(ctx)
        return ctx.result

    def _sync_sustained_goal(self, ctx: TurnContext) -> TurnContext:
        if ctx.session_mode != "learning" or ctx.board is None:
            ctx.goal_lifecycle = {"status": "skipped", "reason": "session_mode:chat"}
            return ctx
        plan = ctx.board.learning_plan
        board = ctx.board.learning_board
        project_goal = ctx.project.goal if ctx.project is not None else ""
        objective = str(plan.goal or project_goal or "").strip()
        ui_summary = str(board.current_progress or objective).strip()
        ctx.goal_lifecycle = self.executor.sync_sustained_goal(
            session_id=ctx.session_id,
            objective=objective,
            ui_summary=ui_summary,
        )
        return ctx

    def _complete_sustained_goal_for_exit(self, ctx: TurnContext, *, reason: str) -> TurnContext:
        ctx.goal_lifecycle = self.executor.complete_sustained_goal(
            session_id=ctx.session_id,
            recap=f"Learning goal closed because {reason}.",
        )
        return ctx

    def _complete_sustained_goal_if_finished(self, ctx: TurnContext) -> TurnContext:
        if ctx.session_mode != "learning" or ctx.result is None:
            return ctx
        if not self._learning_goal_finished(ctx.result):
            return ctx
        recap = f"Completed learning goal: {ctx.result.board_after.learning_plan.goal or ctx.project.title}"
        completed = self.executor.complete_sustained_goal(session_id=ctx.session_id, recap=recap)
        ctx.goal_lifecycle = completed
        raw = dict(ctx.result.raw_learning_result or {})
        runtime_v2 = dict(raw.get("runtime_v2") or {})
        if completed.get("status") == "completed":
            runtime_v2["goal_state"] = {
                "active": False,
                "objective": str(completed.get("objective") or ctx.result.board_after.learning_plan.goal or ""),
                "ui_summary": recap,
            }
            raw["runtime_v2"] = runtime_v2
            ctx.result = replace(ctx.result, raw_learning_result=raw)
        return ctx

    def _learning_goal_finished(self, result: LearningTurnResult) -> bool:
        if str(result.turn_mode_after or "").upper() == "PAUSED":
            return True
        plan = result.board_after.learning_plan
        nodes = list(plan.plan_nodes or [])
        return bool(nodes) and all(str(node.status or "").lower() == "completed" for node in nodes)
