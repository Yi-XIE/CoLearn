"""Result normalization for the CoLearn v0.2 runtime line."""

from __future__ import annotations

from typing import Any

from colearn.learning.response_contract import LearningTurnResult
from colearn.learning.signal_extractor import extract_learning_signals
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
    turn_envelope = {
        "turn_mode_before": request.metadata.get("turn_mode_before", request.turn_mode),
        "board_version_before": int(request.metadata.get("board_version_before") or request.board_facts.board_version or 1),
        "active_node_id_before": str(request.metadata.get("active_node_id_before") or ""),
        "active_node_label_before": str(request.metadata.get("active_node_label_before") or ""),
        "continuation_prompt_before": str(request.metadata.get("continuation_prompt_before") or request.continuation_prompt or ""),
        "allowed_tools_before": list(request.metadata.get("allowed_tools_before") or []),
        "enabled_tools_before": list(request.metadata.get("enabled_tools_before") or request.enabled_tools),
        "source_readiness_before": str(request.metadata.get("source_readiness_before") or ""),
        "policy_restrictions": list(request.metadata.get("policy_restrictions") or []),
    }
    runtime_retrieval = {
        "prefetched_references": list(request.metadata.get("prefetched_references") or []),
        "prompt_support_bundle": list(request.metadata.get("prompt_support_bundle") or []),
        "retrieval_focus": dict(request.metadata.get("retrieval_focus") or {}),
        "retrieval_query_context": dict(request.metadata.get("retrieval_query_context") or {}),
        "retrieval_reason": str(request.metadata.get("retrieval_reason") or ""),
        "retrieval_hits": list(payload.get("retrieval_hits") or []),
        "retrieval_misses": list(payload.get("retrieval_misses") or []),
        "retrieval_evidence_map": dict(payload.get("retrieval_evidence_map") or {}),
        "knowledge_support_summary": dict(payload.get("knowledge_support_summary") or {}),
        "blocker_support_refs": dict(payload.get("blocker_support_refs") or {}),
        "continuation_retrieval_hint": dict(payload.get("continuation_retrieval_hint") or {}),
    }
    payload.setdefault("runtime_v2", {})
    if isinstance(payload["runtime_v2"], dict):
        payload["runtime_v2"].setdefault("board_summary", board_summary)
        payload["runtime_v2"].setdefault("turn_envelope", turn_envelope)
        payload["runtime_v2"].setdefault("retrieval", runtime_retrieval)
    review_to_persist = dict(payload.get("review_to_persist") or {})
    board_patch = dict(payload.get("board_patch") or {})
    memory_events = list(payload.get("memory_events") or [])
    tool_events = list(payload.get("tool_events") or [])
    stream_events = list(payload.get("stream_events") or [])
    warnings = list(payload.get("warnings") or [])

    # LLM-emitted learning_events take precedence; harness extracts heuristic
    # signals from final_text as a fallback so the state machine never goes
    # blind even if the LLM doesn't emit structured events. Dedupe by (kind,
    # concept) — extracted ones are dropped if LLM already covered them.
    payload_events = list(payload.get("learning_events") or [])

    def _event_signature(event: Any) -> tuple[str, str]:
        # LearningEvent dataclass uses .type/.payload; harness-extracted dicts
        # use .kind/.payload — accept both.
        if hasattr(event, "type"):
            kind = str(getattr(event, "type", "") or "")
            payload_ = getattr(event, "payload", {}) or {}
        else:
            kind = str(event.get("kind") or event.get("type") or "")
            payload_ = event.get("payload") or {}
        concept = str((payload_ or {}).get("concept") or "").lower()
        return (kind, concept)

    seen_signatures = {_event_signature(e) for e in payload_events}
    merged_events = list(payload_events)
    for event in extract_learning_signals(final_text):
        signature = _event_signature(event)
        if signature in seen_signatures or not signature[1]:
            continue
        merged_events.append(event)
        seen_signatures.add(signature)
    return LearningTurnResult(
        final_text=final_text,
        next_explanation=str(payload.get("next_explanation") or ""),
        next_practice=list(payload.get("next_practice") or []),
        board_before=request.board_facts,
        board_after=payload.get("board_after") or request.board_facts,
        learning_events=merged_events,
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
            "runtime_v2_turn_envelope": turn_envelope,
            "runtime_v2_retrieval": runtime_retrieval,
            "turn_mode_before": turn_envelope["turn_mode_before"],
            "turn_mode_after": str(payload.get("turn_mode_after") or request.turn_mode),
            "base_board_version": turn_envelope["board_version_before"],
            "resolved_board_version": int((payload.get("board_after") or request.board_facts).board_version if hasattr(payload.get("board_after") or request.board_facts, "board_version") else request.board_facts.board_version),
            "writeback_envelope": dict(payload.get("writeback_envelope") or {}),
        },
    )
