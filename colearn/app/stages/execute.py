"""ExecuteStage — applies turn policy, builds the request, runs the executor."""

from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from colearn.compression import RuntimeCompressionBridge
from colearn.api.state import SettingsStateService
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
        settings_service: SettingsStateService,
    ) -> None:
        self.executor = executor
        self.runtime_compression = runtime_compression
        self.settings_service = settings_service

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    async def run_async(self, ctx: TurnContext) -> TurnContext:
        ctx.turn_policy = policy(
            board=ctx.board,
            user_message=ctx.user_message,
            memory_enabled=self.settings_service.memory_settings()["enabled"],
            retrieval_context=ctx.retrieval_context(),
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
            plan_stage=ctx.plan_stage,
            goal_lifecycle=ctx.goal_lifecycle,
        )
        compressed, final_text, raw_learning_result, closure_payload = await self._execute_turn_async(
            project=ctx.project,
            session=ctx.session,
            request=ctx.request,
            snapshot=ctx.snapshot,
            turn_policy=ctx.turn_policy,
        )
        ctx.compressed = compressed
        ctx.final_text = final_text
        ctx.raw_learning_result = raw_learning_result
        ctx.closure_payload = closure_payload
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
        plan_stage: dict[str, Any] | None = None,
        goal_lifecycle: dict[str, Any] | None = None,
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
                session_mode=str(getattr(session, "mode", "") or "chat"),
                plan_stage=plan_stage,
                goal_lifecycle=goal_lifecycle,
            ),
        )

    def _build_turn_request_metadata(
        self,
        *,
        source_profile: dict[str, Any],
        retrieval_context: dict[str, Any],
        session_mode: str,
        plan_stage: dict[str, Any] | None = None,
        goal_lifecycle: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        retrieval_metadata = {
            "focus": retrieval_context["retrieval_focus"],
            "query_context": retrieval_context["retrieval_query_context"],
            "reason": retrieval_context["retrieval_reason"],
            "prefetched_references": retrieval_context["prefetched_references"],
            "parallel_support": retrieval_context["parallel_support"],
            "prompt_support_bundle": retrieval_context["prompt_support_bundle"],
            "external_web_fallback": retrieval_context.get("external_web_fallback", {}),
        }
        return {
            "turn_id": str(uuid4()),
            "session_mode": session_mode,
            "plan_stage": dict(plan_stage or {}),
            "goal_lifecycle": dict(goal_lifecycle or {}),
            "source_profile": dict(source_profile),
            "retrieval": retrieval_metadata,
            # Compatibility bridge for older prompt/result helpers. New code
            # should read from metadata["retrieval"] instead.
            "retrieval_focus": retrieval_metadata["focus"],
            "retrieval_query_context": retrieval_metadata["query_context"],
            "retrieval_reason": retrieval_metadata["reason"],
            "prefetched_references": retrieval_metadata["prefetched_references"],
            "parallel_support": retrieval_metadata["parallel_support"],
            "prompt_support_bundle": retrieval_metadata["prompt_support_bundle"],
            "workspace": str(self.executor.workspace or colearn_nanobot_workspace()),
        }

    async def _execute_turn_async(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        request,
        snapshot,
        turn_policy,
    ) -> tuple[Any, Any, Any, Any]:
        prepared_request = before_turn(
            request=request,
            snapshot=snapshot,
            decision=turn_policy,
        )
        compressed = self.runtime_compression.compress(request=prepared_request)
        final_text, messages, tools_used, raw_result = await self.executor.run_turn_async(request=compressed.request)
        closure_payload = build_learning_closure(
            project=project,
            session=session,
            request=compressed.request,
            final_text=final_text,
            raw_learning_result=raw_result,
            warnings=[
                *list(raw_result.get("warnings") or []),
                *compressed.notes,
            ],
        )
        return compressed, final_text, raw_result, closure_payload
