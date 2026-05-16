"""Result normalization for the CoLearn v0.2 runtime line."""

from __future__ import annotations

from typing import Any

from colearn.learning.response_contract import LearningTurnResult
from colearn.learning.turn_contract import LearningTurnRequest


def normalize_learning_turn_result(
    *,
    request: LearningTurnRequest,
    final_text: str,
    learning_result: dict[str, Any] | None = None,
) -> LearningTurnResult:
    payload = dict(learning_result or {})
    board_summary = {
        "turn_mode": request.turn_mode,
        "active_node_id": request.board_facts.current_progress.active_node_id,
        "active_node_label": request.board_facts.current_progress.active_node_label,
        "mastery_level": request.state_projection.mastery_level or request.board_facts.student_snapshot.mastery_level,
        "cognitive_load": request.state_projection.cognitive_load or request.board_facts.student_snapshot.cognitive_load,
        "critical_blocker_count": len(request.board_facts.gaps_and_blockers.critical_blockers or []),
        "unverified_gap_count": len(request.board_facts.gaps_and_blockers.unverified_gaps or []),
    }
    payload.setdefault("runtime_v2", {})
    if isinstance(payload["runtime_v2"], dict):
        payload["runtime_v2"].setdefault("board_summary", board_summary)
    review_to_persist = dict(payload.get("review_to_persist") or {})
    board_patch = dict(payload.get("board_patch") or {})
    memory_events = list(payload.get("memory_events") or [])
    tool_events = list(payload.get("tool_events") or [])
    stream_events = list(payload.get("stream_events") or [])
    warnings = list(payload.get("warnings") or [])
    return LearningTurnResult(
        final_text=final_text,
        next_explanation=str(payload.get("next_explanation") or ""),
        next_practice=list(payload.get("next_practice") or []),
        board_before=request.board_facts,
        board_after=payload.get("board_after") or request.board_facts,
        learning_events=list(payload.get("learning_events") or []),
        review_summary=str(payload.get("review_summary") or ""),
        turn_mode_before=str(request.metadata.get("turn_mode_before") or request.turn_mode),
        turn_mode_after=str(payload.get("turn_mode_after") or request.turn_mode),
        continuation_prompt=str(payload.get("continuation_prompt") or request.continuation_prompt),
        review_to_persist=review_to_persist,
        board_patch=board_patch,
        memory_events=memory_events,
        tool_events=tool_events,
        stream_events=stream_events,
        warnings=warnings,
        retrieval_bundle=request.retrieval_bundle,
        raw_learning_result=payload,
        metadata={
            "project_id": request.project_id,
            "project_title": request.project_title,
            "requested_skills": request.requested_skills,
            "enabled_tools": request.enabled_tools,
            "runtime_v2_board_summary": board_summary,
        },
    )
