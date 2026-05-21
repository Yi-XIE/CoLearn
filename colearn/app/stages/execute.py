"""ExecuteStage — applies turn policy, builds the request, runs the executor."""

from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from colearn.compression import RuntimeCompressionBridge
from colearn.learning.state_hooks import before_turn, policy
from colearn.paths import colearn_nanobot_workspace
from colearn.projects.models import LearningProject
from colearn.runtime_v2 import build_learning_closure
from colearn.runtime_v2.context_bridge import build_learning_turn_request
from colearn.runtime_v2.executor import NanobotTurnExecutor
from colearn.sessions.store import LearningSession

from .context import TurnContext


class ExecuteStage:
    """Builds the LearningTurnRequest, runs the nanobot executor, finalises."""

    def __init__(
        self,
        *,
        executor: NanobotTurnExecutor,
        runtime_compression: RuntimeCompressionBridge,
    ) -> None:
        self.executor = executor
        self.runtime_compression = runtime_compression

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def run(self, ctx: TurnContext) -> TurnContext:
        ctx.turn_policy = policy(
            board=ctx.board,
            user_message=ctx.user_message,
        )
        ctx.request = self._build_turn_request(
            session=ctx.session,
            project=ctx.project,
            board=ctx.board,
            snapshot=ctx.snapshot,
            source_profile=ctx.source_profile,
            retrieval_context=ctx.retrieval_context(),
            user_message=ctx.user_message,
            language=ctx.language,
            turn_policy=ctx.turn_policy,
            attachments=ctx.attachments,
            requested_skills=ctx.requested_skills,
            stream_emit=ctx.stream_emit,
            cancel_check=ctx.cancel_check,
        )
        compressed, normalized = self._execute_turn(
            project=ctx.project,
            session=ctx.session,
            request=ctx.request,
            snapshot=ctx.snapshot,
            turn_policy=ctx.turn_policy,
        )
        ctx.compressed = compressed
        ctx.result = normalized
        return ctx

    async def run_async(self, ctx: TurnContext) -> TurnContext:
        ctx.turn_policy = policy(
            board=ctx.board,
            user_message=ctx.user_message,
        )
        ctx.request = self._build_turn_request(
            session=ctx.session,
            project=ctx.project,
            board=ctx.board,
            snapshot=ctx.snapshot,
            source_profile=ctx.source_profile,
            retrieval_context=ctx.retrieval_context(),
            user_message=ctx.user_message,
            language=ctx.language,
            turn_policy=ctx.turn_policy,
            attachments=ctx.attachments,
            requested_skills=ctx.requested_skills,
            stream_emit=ctx.stream_emit,
            cancel_check=ctx.cancel_check,
        )
        compressed, normalized = await self._execute_turn_async(
            project=ctx.project,
            session=ctx.session,
            request=ctx.request,
            snapshot=ctx.snapshot,
            turn_policy=ctx.turn_policy,
        )
        ctx.compressed = compressed
        ctx.result = normalized
        return ctx

    # ------------------------------------------------------------------
    # Internals (lifted verbatim from LearningOrchestrator)
    # ------------------------------------------------------------------
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
        cancel_check: Callable[[], bool] | None,
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
            cancel_check=cancel_check,
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

    async def _execute_turn_async(
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
        result = await self.executor.run_turn_async(request=compressed.request)
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
