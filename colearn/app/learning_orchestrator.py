"""Main assembly entrypoint for a single CoLearn learning turn."""

from __future__ import annotations

from typing import Any, Callable

from colearn.logging_config import get_logger

from colearn.config.defaults import Defaults
from colearn.compression import ProductCompressionBridge, RuntimeCompressionBridge
from colearn.knowledge import KnowledgeWorkspaceService
from colearn.learning.board_deriver import BoardSnapshotDeriver
from colearn.learning.response_contract import LearningTurnResult
from colearn.memory.store import EventMemoryStore
from colearn.paths import colearn_nanobot_workspace
from colearn.projects.service import LearningProjectService
from colearn.retrieval.service import RetrievalService
from colearn.runtime_v2.executor import NanobotTurnExecutor
from colearn.sessions.store import SessionStore
from .background_finalizer import BackgroundTurnFinalizer
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
        executor: NanobotTurnExecutor | None = None,
        runtime_compression: RuntimeCompressionBridge | None = None,
        product_compression: ProductCompressionBridge | None = None,
        board_deriver: BoardSnapshotDeriver | None = None,
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

    async def run_turn_async(
        self,
        *,
        session_id: str,
        user_message: str,
        project_id: str = "",
        language: str = "zh",
        attachments: list[dict[str, object]] | None = None,
        requested_skills: list[str] | None = None,
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
            stream_emit=stream_emit,
            cancel_check=cancel_check,
        )
        ctx = self.preflight.run(ctx)
        ctx = await self.retrieval.run_async(ctx)
        self.preflight.sync_project_retrieval_profile(ctx)
        ctx = await self.execute.run_async(ctx)
        ctx = self.finalize.run(ctx)
        await self.writeback.run_async(ctx)
        return ctx.result
