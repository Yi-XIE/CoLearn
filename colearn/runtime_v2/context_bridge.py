"""Bridge CoLearn learning context into runtime-facing turn requests."""

from __future__ import annotations

from typing import Any, Callable

from colearn.learning.retrieval_bundle import RetrievalBundle, empty_retrieval_bundle
from colearn.learning.state import BoardFacts, LearningStateSnapshot, PolicyDecision, TurnPolicy
from colearn.learning.turn_contract import LearningTurnRequest


def build_learning_turn_request(
    *,
    session_id: str,
    user_message: str,
    language: str = "zh",
    project_id: str = "",
    project_title: str = "",
    turn_mode: str = "EXPLORE",
    board_facts: BoardFacts | None = None,
    turn_policy: TurnPolicy | None = None,
    anchor: dict[str, Any] | None = None,
    source_references: list[dict[str, Any]] | None = None,
    memory_references: list[str] | None = None,
    retrieval_bundle: RetrievalBundle | None = None,
    state_projection: LearningStateSnapshot | None = None,
    policy_decision: PolicyDecision | None = None,
    continuation_prompt: str = "",
    enabled_tools: list[str] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    requested_skills: list[str] | None = None,
    stream_emit: Callable[[dict[str, Any]], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    metadata: dict[str, Any] | None = None,
) -> LearningTurnRequest:
    metadata = metadata or {}
    return LearningTurnRequest(
        session_id=session_id,
        user_message=user_message,
        language=language,
        project_id=project_id,
        project_title=project_title,
        turn_mode=turn_mode,
        model_preset=str((turn_policy.model_preset if turn_policy else metadata.get("model_preset")) or "") or None,
        board_facts=board_facts or BoardFacts(),
        turn_policy=turn_policy,
        anchor=anchor or {},
        source_references=source_references or [],
        memory_references=memory_references or [],
        retrieval_bundle=retrieval_bundle or empty_retrieval_bundle(query=user_message),
        state_projection=state_projection or LearningStateSnapshot(),
        continuation_prompt=continuation_prompt,
        enabled_tools=enabled_tools or [],
        attachments=attachments or [],
        requested_skills=requested_skills or [],
        stream_emit=stream_emit,
        cancel_check=cancel_check,
        metadata=metadata,
    )
