"""PreflightStage — resolves project/session and runs source-readiness gating."""

from __future__ import annotations

import time as _time
from dataclasses import replace
from typing import Any

from colearn.knowledge import KnowledgeWorkspaceService
from colearn.learning.constants import LearningPhase
from colearn.learning.state_hooks import build_learning_board, build_state_snapshot
from colearn.projects.models import LearningProject
from colearn.projects.service import LearningProjectService
from colearn.retrieval.service import RetrievalService
from colearn.sessions.store import LearningSession, SessionStore

from ..source_preflight import SourceReadinessPreflight
from .context import TurnContext


LEARNING_INTENT_KEYWORDS = (
    "学",
    "学习",
    "讲讲",
    "讲解",
    "带我学",
    "课程",
    "知识点",
    "复习",
    "练习",
    "learn",
    "study",
    "lesson",
)

SESSION_END_KEYWORDS = (
    "结束",
    "今天就到这",
    "到此为止",
    "下次再学",
    "done",
    "stop",
    "that's all",
    "end session",
    "bye",
    "再见",
)


def _normalize_session_mode(value: str | None) -> str:
    return "learning" if str(value or "").strip().lower() == "learning" else "chat"


def _looks_like_learning_intent(message: str) -> bool:
    lowered = str(message or "").strip().lower()
    return bool(lowered) and any(keyword in lowered for keyword in LEARNING_INTENT_KEYWORDS)


def _looks_like_session_end(message: str) -> bool:
    lowered = str(message or "").strip().lower()
    return bool(lowered) and any(keyword in lowered for keyword in SESSION_END_KEYWORDS)


def _has_profile(session: LearningSession) -> bool:
    return bool(session.profile)


def _recall_is_due(session: LearningSession) -> bool:
    recall = session.next_recall
    if not recall:
        return False
    next_at = recall.get("next_recall_at", "")
    if not next_at:
        return False
    from datetime import datetime, timezone
    try:
        due = datetime.fromisoformat(next_at)
        return datetime.now(timezone.utc) >= due
    except (ValueError, TypeError):
        return False


def _normalize_session_mode(value: str | None) -> str:
    return "learning" if str(value or "").strip().lower() == "learning" else "chat"


def _looks_like_learning_intent(message: str) -> bool:
    lowered = str(message or "").strip().lower()
    return bool(lowered) and any(keyword in lowered for keyword in LEARNING_INTENT_KEYWORDS)


class PreflightStage:
    """Resolves the working session/project, builds the initial board snapshot.

    Pure refactor of ``LearningOrchestrator._prepare_turn_context`` plus the
    follow-up ``_sync_project_retrieval_profile``.
    """

    def __init__(
        self,
        *,
        project_service: LearningProjectService,
        session_store: SessionStore,
        retrieval_service: RetrievalService,
        knowledge_service: KnowledgeWorkspaceService,
        source_preflight: SourceReadinessPreflight,
    ) -> None:
        self.project_service = project_service
        self.session_store = session_store
        self.retrieval_service = retrieval_service
        self.knowledge_service = knowledge_service
        self.source_preflight = source_preflight

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    async def run_async(self, ctx: TurnContext) -> TurnContext:
        prepared = await self._prepare_turn_context(
            session_id=ctx.session_id,
            project_id=ctx.project_id,
            requested_mode=ctx.requested_mode,
            user_message=ctx.user_message,
        )
        ctx.session = prepared["session"]
        ctx.project = prepared["project"]
        ctx.board = prepared["board"]
        ctx.snapshot = prepared["snapshot"]
        ctx.source_profile = prepared["source_profile"]
        ctx.session_mode = prepared["session_mode"]
        return ctx

    def sync_project_retrieval_profile(self, ctx: TurnContext) -> None:
        """Called by RetrievalStage after the bundle/parallel_support are ready.

        Lives on PreflightStage because it concerns the *project* record and
        composes data from preflight (source_profile/board) plus retrieval.
        Kept here so RetrievalStage doesn't grow a project_service dep just
        for this one write.
        """
        self._sync_project_retrieval_profile(
            project=ctx.project,
            source_profile=ctx.source_profile,
            board=ctx.board,
            retrieval_context=ctx.retrieval_context(),
        )

    # ------------------------------------------------------------------
    # Internals (lifted verbatim from LearningOrchestrator)
    # ------------------------------------------------------------------
    async def _prepare_turn_context(
        self,
        *,
        session_id: str,
        project_id: str,
        requested_mode: str | None = None,
        user_message: str = "",
    ) -> dict[str, Any]:
        session = self._get_or_create_session(session_id=session_id, project_id=project_id)
        project = self._get_or_create_project(project_id=project_id, session=session)
        prior_mode = _normalize_session_mode(getattr(session, "mode", "chat"))
        requested = _normalize_session_mode(requested_mode) if requested_mode else None
        session_mode = requested or prior_mode
        if requested is None and prior_mode == "chat" and _looks_like_learning_intent(user_message):
            session_mode = "learning"
        session.mode = session_mode
        project.mode = session_mode
        learning_phase = self._resolve_learning_phase(
            session=session,
            session_mode=session_mode,
            user_message=user_message,
        )
        session.learning_phase = learning_phase
        source_refs = list(session.source_refs or project.source_subset or project.source_refs)
        source_profile = await self.source_preflight.run_async(
            project_id=project.project_id,
            source_refs=source_refs,
        )
        board = build_learning_board(
            project=project,
            session=session,
            latest_review=project.latest_review,
        )
        board = replace(board, learning_phase=LearningPhase(learning_phase))
        snapshot = build_state_snapshot(
            project=project,
            session=session,
            latest_review=project.latest_review,
        )
        if session_mode == "chat":
            board = replace(board, current_turn_mode="PAUSED")
            snapshot = replace(snapshot, turn_mode="PAUSED")
        return {
            "session": session,
            "project": project,
            "source_profile": source_profile,
            "board": board,
            "snapshot": snapshot,
            "session_mode": session_mode,
        }

    def _resolve_learning_phase(
        self,
        *,
        session: LearningSession,
        session_mode: str,
        user_message: str,
    ) -> str:
        if session_mode != "learning":
            return LearningPhase.READY
        if not _has_profile(session) and len(session.messages) == 0:
            return LearningPhase.INTAKE
        if _recall_is_due(session) and len(session.messages) == 0:
            return LearningPhase.RECALL
        if _looks_like_session_end(user_message):
            return LearningPhase.REFLECT
        return session.learning_phase or LearningPhase.READY

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
            "active_turn_mode": board.current_turn_mode,
            "prefetch_bundle": {
                "query": retrieval_bundle.query,
                "retrieval_status": retrieval_bundle.retrieval_status,
                "fallback_reason": retrieval_bundle.fallback_reason,
                "warnings": list(retrieval_bundle.warnings or []),
            },
            "last_retrieval_status": retrieval_bundle.retrieval_status,
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
