"""Turn policy and writeback hooks for learning state."""

from __future__ import annotations

from dataclasses import asdict, replace
from colearn.learning.events import MemoryEventKind
from typing import Any

from colearn.learning.board_hooks import (
    after_turn,
    determine_turn_mode,
    extract_board_facts,
    resolve_model_preset,
)
from colearn.learning.state import ReplyContract, TurnPolicy


LIGHTRAG_HINT_KEYWORDS: tuple[str, ...] = (
    "来源",
    "依据",
    "证据",
    "参考",
    "资料",
    "文献",
    "出处",
    "例子",
    "反例",
    "证明",
    "why",
    "source",
    "sources",
    "reference",
    "references",
    "evidence",
    "example",
    "examples",
    "counterexample",
    "proof",
)


def _needs_lightrag(*, board, user_message: str, turn_mode: str) -> bool:
    if turn_mode == "EXPLORE":
        return True
    if turn_mode == "VERIFY" and bool(board.gaps_and_blockers.unverified_gaps):
        return True
    lowered = str(user_message or "").strip().lower()
    if lowered and any(keyword in lowered for keyword in LIGHTRAG_HINT_KEYWORDS):
        return True
    if turn_mode == "CORRECTION":
        blockers = list(board.gaps_and_blockers.critical_blockers or [])
        if blockers:
            blocker_text = " ".join(str(blocker.desc or "") for blocker in blockers).lower()
            if any(keyword in blocker_text for keyword in LIGHTRAG_HINT_KEYWORDS):
                return True
    return False


def policy(
    *,
    board,
    user_message: str,
    memory_enabled: bool = True,
    **_: Any,
) -> TurnPolicy:
    turn_mode = determine_turn_mode(board, user_message)
    restrictions: list[str] = []

    if turn_mode == "ANCHOR":
        restrictions.append("must_clarify_anchor_first")
    elif turn_mode == "CORRECTION":
        restrictions.extend(["do_not_introduce_new_topic", "do_not_give_direct_answer"])
    elif turn_mode == "VERIFY":
        restrictions.append("do_not_give_direct_answer")

    allowed_tools: list[str] = ["memory"] if memory_enabled else []
    if _needs_lightrag(board=board, user_message=user_message, turn_mode=turn_mode):
        allowed_tools.append("lightrag")

    return TurnPolicy(
        turn_mode=turn_mode,
        model_preset=resolve_model_preset(turn_mode),
        main_goal=(
            "Complete the learning anchor first."
            if turn_mode == "ANCHOR"
            else "Advance the current learning turn with grounded explanations."
        ),
        restrictions=restrictions,
        allowed_tools=allowed_tools,
        enabled_tools=list(allowed_tools),
        reply_contract=ReplyContract(),
        warnings=(
            ["Project anchor is incomplete."]
            if turn_mode == "ANCHOR"
            else [blocker.desc for blocker in board.gaps_and_blockers.critical_blockers]
        ),
        continuation_prompt=board.continuation.next_prompt_hint,
        metadata={
            "board_version": board.board_version,
            "blocker_count": len(board.gaps_and_blockers.critical_blockers),
            "lightrag_enabled": "lightrag" in allowed_tools,
        },
    )


def before_turn(
    *,
    request: Any,
    snapshot: Any,
    decision: Any,
) -> Any:
    _ = snapshot
    if hasattr(request, "metadata") and isinstance(request.metadata, dict):
        board = getattr(request, "board_facts", None)
        continuation = getattr(board, "continuation", None)
        progress = getattr(board, "current_progress", None)
        return replace(
            request,
            metadata={
                **request.metadata,
                "turn_mode_before": getattr(request, "turn_mode", "EXPLORE"),
                "board_version_before": int(getattr(board, "board_version", 1) or 1),
                "active_node_id_before": str(getattr(progress, "active_node_id", "") or ""),
                "active_node_label_before": str(getattr(progress, "active_node_label", "") or ""),
                "continuation_prompt_before": str(getattr(continuation, "next_prompt_hint", "") or ""),
                "allowed_tools_before": list(getattr(decision, "allowed_tools", []) or []),
                "enabled_tools_before": list(getattr(request, "enabled_tools", []) or []),
                "source_readiness_before": str(request.metadata.get("source_profile", {}).get("readiness", "") or ""),
                "policy_restrictions": list(getattr(decision, "restrictions", []) or []),
                "model_preset": getattr(decision, "model_preset", None),
            },
        )
    return request


def after_turn_payload(
    *,
    project: Any,
    session: Any,
    request: Any,
    final_text: str,
    tool_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metadata = dict(getattr(request, "metadata", {}) or {})
    retrieval_metadata = dict(metadata.get("retrieval") or {})
    board = getattr(request, "board_facts", None)
    if board is None:
        board = extract_board_facts(
            project=project,
            session_id=getattr(session, "session_id", ""),
            board_version=int(getattr(session, "board_version", 1) or 1),
            turn_mode=getattr(session, "turn_mode", "EXPLORE"),
        )
    updated_board, events = after_turn(
        board=board,
        user_message=str(getattr(request, "user_message", "")),
        final_text=final_text,
        source_references=list(getattr(request, "source_references", []) or []),
        tool_events=tool_events,
    )
    retrieval_query_context = dict(
        retrieval_metadata.get("query_context") or metadata.get("retrieval_query_context") or {}
    )
    review_summary = final_text[:240].strip()
    continuation_prompt = updated_board.continuation.next_prompt_hint or str(
        getattr(request, "continuation_prompt", "")
    )
    turn_mode_before = str(getattr(request, "turn_mode", "EXPLORE"))
    base_board_version = int(getattr(board, "board_version", 1) or 1)
    resolved_board_version = int(updated_board.board_version or 1)
    event_types = [event.type for event in events]
    return {
        "review_summary": review_summary,
        "continuation_prompt": continuation_prompt,
        "review_to_persist": {
            "summary": review_summary,
            "confusion_points": [
                blocker.desc for blocker in updated_board.gaps_and_blockers.critical_blockers
            ],
        },
        "turn_mode_after": updated_board.current_turn_mode,
        "turn_mode_before": turn_mode_before,
        "board_after": updated_board,
        "learning_events": events,
        "board_patch": {
            "current_turn_mode": updated_board.current_turn_mode,
            "board_version": updated_board.board_version,
            "updated_at": updated_board.updated_at,
            "continuation": asdict(updated_board.continuation),
            "current_progress": asdict(updated_board.current_progress),
            "student_snapshot": asdict(updated_board.student_snapshot),
            "gaps_and_blockers": asdict(updated_board.gaps_and_blockers),
            "evidence_refs": list(updated_board.evidence_refs),
        },
        "continuation_retrieval_hint": {
            "active_node_id": updated_board.current_progress.active_node_id,
            "evidence_refs": list(updated_board.evidence_refs or []),
            "retrieval_focus": retrieval_metadata.get("focus") or metadata.get("retrieval_focus") or {},
            "retrieval_query_context": retrieval_query_context,
        },
        "memory_events": [
            {
                "kind": MemoryEventKind.TURN_COMPLETED,
                "payload": {
                    "session_id": getattr(session, "session_id", ""),
                    "project_id": getattr(project, "project_id", ""),
                    "final_text": final_text,
                    "turn_mode": updated_board.current_turn_mode,
                    "events": event_types,
                    "base_board_version": base_board_version,
                    "resolved_board_version": resolved_board_version,
                },
            },
            {
                "kind": MemoryEventKind.REVIEW_WRITTEN,
                "payload": {
                    "session_id": getattr(session, "session_id", ""),
                    "project_id": getattr(project, "project_id", ""),
                    "summary": review_summary,
                },
            },
            {
                "kind": MemoryEventKind.CONTINUATION_UPDATED,
                "payload": {
                    "session_id": getattr(session, "session_id", ""),
                    "project_id": getattr(project, "project_id", ""),
                    "continuation_prompt": continuation_prompt,
                },
            },
        ],
    }
