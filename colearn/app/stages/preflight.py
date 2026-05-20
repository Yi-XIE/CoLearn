"""PreflightStage — resolves project/session and runs source-readiness gating."""

from __future__ import annotations

from typing import Any

from colearn.knowledge import KnowledgeWorkspaceService
from colearn.learning.state_hooks import build_learning_board, build_state_snapshot
from colearn.projects.models import LearningProject
from colearn.projects.service import LearningProjectService
from colearn.retrieval.service import RetrievalService
from colearn.sessions.store import LearningSession, SessionStore

from ..source_preflight import SourceReadinessPreflight
from .context import TurnContext


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
    def run(self, ctx: TurnContext) -> TurnContext:
        prepared = self._prepare_turn_context(
            session_id=ctx.session_id,
            project_id=ctx.project_id,
        )
        ctx.session = prepared["session"]
        ctx.project = prepared["project"]
        ctx.board = prepared["board"]
        ctx.snapshot = prepared["snapshot"]
        ctx.source_profile = prepared["source_profile"]
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
