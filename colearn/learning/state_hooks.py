"""Three-layer control hooks: Board Facts -> Turn Policy -> Learning Events."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
import hashlib
import json
from typing import Any, cast

from colearn.learning.state import (
    Blocker,
    BoardFacts,
    ContinuationFacts,
    GapsAndBlockers,
    LearningEvent,
    LearningStateSnapshot,
    ProgressFacts,
    ReplyContract,
    StudentSnapshot,
    TurnMode,
    TurnPolicy,
)
from colearn.projects.models import LearningProject


def _normalize_turn_mode(raw: str | None) -> TurnMode:
    value = str(raw or "EXPLORE").upper()
    if value in {"ANCHOR", "CORRECTION", "VERIFY", "EXPLORE", "PAUSED"}:
        return cast(TurnMode, value)
    return "EXPLORE"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


def extract_board_facts(
    *,
    project: LearningProject,
    session_id: str,
    continuation_hint: str = "",
    board_version: int = 1,
    turn_mode: str = "EXPLORE",
) -> BoardFacts:
    gaps = list(project.latest_review.get("confusion_points") or [])
    blockers = [
        Blocker(
            id=f"blk_{idx:03d}",
            type="CONCEPT_MISUNDERSTANDING",
            desc=str(gap),
        )
        for idx, gap in enumerate(gaps)
    ]
    return BoardFacts(
        project_id=project.project_id,
        session_id=session_id,
        current_turn_mode=_normalize_turn_mode(turn_mode),
        board_version=board_version,
        updated_at="",
        current_progress=ProgressFacts(
            active_node_id=project.project_id,
            active_node_label=project.title,
        ),
        student_snapshot=StudentSnapshot(
            mastery_level=0.0,
            last_user_intent_raw="",
        ),
        gaps_and_blockers=GapsAndBlockers(
            critical_blockers=blockers,
            unverified_gaps=[],
        ),
        continuation=ContinuationFacts(
            next_prompt_hint=continuation_hint,
        ),
        evidence_refs=[{"source_ref": item} for item in (project.source_refs or [])],
    )


def build_learning_board(
    *,
    project: LearningProject,
    session: Any,
    latest_review: dict[str, Any] | None = None,
) -> BoardFacts:
    raw = dict(getattr(session, "board_facts", None) or project.board_facts or {})
    if raw:
        return BoardFacts(
            project_id=str(raw.get("project_id") or project.project_id),
            session_id=str(raw.get("session_id") or getattr(session, "session_id", "")),
            current_turn_mode=_normalize_turn_mode(raw.get("current_turn_mode")),
            board_version=int(raw.get("board_version") or getattr(session, "board_version", 1) or 1),
            updated_at=str(raw.get("updated_at") or ""),
            current_progress=ProgressFacts(**dict(raw.get("current_progress") or {})),
            student_snapshot=StudentSnapshot(**dict(raw.get("student_snapshot") or {})),
            gaps_and_blockers=GapsAndBlockers(
                critical_blockers=[
                    Blocker(**dict(item))
                    for item in list((raw.get("gaps_and_blockers") or {}).get("critical_blockers") or [])
                ],
                unverified_gaps=list((raw.get("gaps_and_blockers") or {}).get("unverified_gaps") or []),
            ),
            continuation=ContinuationFacts(**dict(raw.get("continuation") or {})),
            evidence_refs=list(raw.get("evidence_refs") or []),
        )
    continuation_hint = str((latest_review or {}).get("continuation_prompt") or "")
    return extract_board_facts(
        project=project,
        session_id=getattr(session, "session_id", ""),
        continuation_hint=continuation_hint,
        board_version=int(getattr(session, "board_version", 1) or 1),
        turn_mode=getattr(session, "turn_mode", getattr(project, "turn_mode", "EXPLORE")),
    )


def build_state_snapshot(
    *,
    project: LearningProject,
    session: Any,
    latest_review: dict[str, Any] | None = None,
) -> LearningStateSnapshot:
    board = build_learning_board(
        project=project,
        session=session,
        latest_review=latest_review,
    )
    return LearningStateSnapshot(
        turn_mode=board.current_turn_mode,
        active_node_id=board.current_progress.active_node_id,
        active_node_label=board.current_progress.active_node_label,
        mastery_level=board.student_snapshot.mastery_level,
        cognitive_load=board.student_snapshot.cognitive_load,
        blockers=[blocker.desc for blocker in board.gaps_and_blockers.critical_blockers],
    )


def determine_turn_mode(board: BoardFacts, user_message: str) -> TurnMode:
    if board.current_turn_mode == "PAUSED":
        return "PAUSED"
    if not board.current_progress.active_node_id:
        return "ANCHOR"
    if board.gaps_and_blockers.critical_blockers:
        return "CORRECTION"
    if board.gaps_and_blockers.unverified_gaps:
        return "VERIFY"
    return "EXPLORE"


def policy(
    *,
    board: BoardFacts,
    user_message: str,
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

    allowed_tools: list[str] = ["memory"]
    if turn_mode == "EXPLORE":
        allowed_tools.append("lightrag")

    return TurnPolicy(
        turn_mode=turn_mode,
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
        },
    )


def build_turn_context(
    *,
    board: BoardFacts,
    turn_policy: TurnPolicy,
    user_message: str,
) -> str:
    lines = [
        f"Project: {board.project_id}",
        f"Turn mode: {turn_policy.turn_mode}",
    ]
    if turn_policy.main_goal:
        lines.append(f"Main goal: {turn_policy.main_goal}")
    if turn_policy.continuation_prompt:
        lines.append(f"Continuation: {turn_policy.continuation_prompt}")
    if turn_policy.restrictions:
        lines.append(f"Restrictions: {', '.join(turn_policy.restrictions)}")
    if board.gaps_and_blockers.critical_blockers:
        blocker_descs = [b.desc for b in board.gaps_and_blockers.critical_blockers]
        lines.append(f"Known blockers: {'; '.join(blocker_descs)}")
    lines.append("User message:")
    lines.append(user_message)
    return "\n\n".join(line for line in lines if line)


def extract_learning_events(
    *,
    board: BoardFacts,
    user_message: str,
    final_text: str,
    source_references: list[dict[str, Any]] | None = None,
    tool_events: list[dict[str, Any]] | None = None,
) -> list[LearningEvent]:
    events: list[LearningEvent] = [
        LearningEvent(
            type="CONTINUATION_UPDATED",
            payload=_json_safe({
                "next_prompt_hint": f"Continue from {board.current_progress.active_node_label}",
                "last_completed_turn_id": user_message[:80],
            }),
        ),
    ]

    final_lower = final_text.lower()
    if board.current_progress.active_node_id and any(
        marker in final_lower for marker in ["completed", "done", "掌握", "完成", "学会"]
    ):
        events.append(
            LearningEvent(
                type="NODE_COMPLETED",
                payload=_json_safe(
                    {
                        "node_id": board.current_progress.active_node_id,
                        "node_label": board.current_progress.active_node_label,
                    }
                ),
            )
        )
    elif not board.current_progress.completed_node_ids:
        events.append(
            LearningEvent(
                type="NODE_STARTED",
                payload=_json_safe({
                    "node_id": board.current_progress.active_node_id,
                    "node_label": board.current_progress.active_node_label,
                }),
            )
        )

    blocker_markers = ["confused", "stuck", "unclear", "不懂", "卡住", "困惑"]
    if any(marker in user_message.lower() for marker in blocker_markers):
        blocker_id = hashlib.sha1(user_message[:240].encode("utf-8")).hexdigest()[:10]
        events.append(
            LearningEvent(
                type="BLOCKER_FOUND",
                payload=_json_safe(
                    {
                        "id": f"blk_{blocker_id}",
                        "type": "CONCEPT_MISUNDERSTANDING",
                        "desc": user_message[:240],
                    }
                ),
            )
        )

    refs = list(source_references or [])
    tool_names = [
        str(item.get("tool_name") or item.get("tool") or "")
        for item in list(tool_events or [])
        if str(item.get("tool_name") or item.get("tool") or "")
    ]
    for idx, ref in enumerate(refs):
        raw_ref = str(ref.get("source_ref") or ref.get("source_path") or ref.get("path") or "").strip()
        if not raw_ref:
            continue
        events.append(
            LearningEvent(
                type="EVIDENCE_ATTACHED",
                payload=_json_safe(
                    {
                        "source_ref": raw_ref,
                        "tool_name": tool_names[0] if tool_names else "",
                        "chunk_id": str(ref.get("chunk_id") or f"source_{idx}"),
                    }
                ),
            )
        )

    return events


def apply_events(
    board: BoardFacts,
    events: list[LearningEvent],
) -> BoardFacts:
    completed_node_ids = list(board.current_progress.completed_node_ids)
    blockers = list(board.gaps_and_blockers.critical_blockers)
    continuation = board.continuation
    evidence_refs = list(board.evidence_refs)

    for event in events:
        if event.type == "NODE_COMPLETED":
            node_id = str(event.payload.get("node_id") or "")
            if node_id and node_id not in completed_node_ids:
                completed_node_ids.append(node_id)
        elif event.type == "CONTINUATION_UPDATED":
            continuation = ContinuationFacts(
                next_prompt_hint=str(event.payload.get("next_prompt_hint") or continuation.next_prompt_hint),
                last_completed_turn_id=str(
                    event.payload.get("last_completed_turn_id") or continuation.last_completed_turn_id
                ),
            )
        elif event.type == "BLOCKER_FOUND":
            blocker = Blocker(
                id=str(event.payload.get("id") or f"blk_{len(blockers):03d}"),
                type=str(event.payload.get("type") or "CONCEPT_MISUNDERSTANDING"),
                desc=str(event.payload.get("desc") or ""),
            )
            if blocker.id not in {item.id for item in blockers}:
                blockers.append(blocker)
        elif event.type == "EVIDENCE_ATTACHED":
            source_ref = str(event.payload.get("source_ref") or "")
            if source_ref:
                evidence = {
                    "source_ref": source_ref,
                    "tool_name": str(event.payload.get("tool_name") or ""),
                    "chunk_id": str(event.payload.get("chunk_id") or ""),
                }
                signature = (
                    evidence["source_ref"],
                    evidence["tool_name"],
                    evidence["chunk_id"],
                )
                existing = {
                    (
                        str(item.get("source_ref") or ""),
                        str(item.get("tool_name") or ""),
                        str(item.get("chunk_id") or ""),
                    )
                    for item in evidence_refs
                }
                if signature not in existing:
                    evidence_refs.append(evidence)

    return BoardFacts(
        project_id=board.project_id,
        session_id=board.session_id,
        current_turn_mode=board.current_turn_mode,
        board_version=board.board_version + 1,
        updated_at=_utc_now(),
        current_progress=ProgressFacts(
            active_node_id=board.current_progress.active_node_id,
            active_node_label=board.current_progress.active_node_label,
            completed_node_ids=completed_node_ids,
            path_node_ids=list(board.current_progress.path_node_ids),
        ),
        student_snapshot=board.student_snapshot,
        gaps_and_blockers=GapsAndBlockers(
            critical_blockers=blockers,
            unverified_gaps=list(board.gaps_and_blockers.unverified_gaps),
        ),
        continuation=continuation,
        evidence_refs=evidence_refs,
    )


def after_turn(
    *,
    board: BoardFacts,
    user_message: str,
    final_text: str,
    source_references: list[dict[str, Any]] | None = None,
    tool_events: list[dict[str, Any]] | None = None,
) -> tuple[BoardFacts, list[LearningEvent]]:
    events = extract_learning_events(
        board=board,
        user_message=user_message,
        final_text=final_text,
        source_references=source_references,
        tool_events=tool_events,
    )
    updated = apply_events(board, events)
    return updated, events


def before_turn(
    *,
    request: Any,
    snapshot: Any,
    decision: Any,
) -> Any:
    if hasattr(request, "metadata") and isinstance(request.metadata, dict):
        return replace(
            request,
            metadata={
                **request.metadata,
                "turn_mode_before": getattr(request, "turn_mode", "EXPLORE"),
                "policy_restrictions": list(getattr(decision, "restrictions", []) or []),
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
    review_summary = final_text[:240].strip()
    continuation_prompt = updated_board.continuation.next_prompt_hint or str(
        getattr(request, "continuation_prompt", "")
    )
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
        "memory_events": [
            {
                "kind": "turn_completed",
                "payload": {
                    "session_id": getattr(session, "session_id", ""),
                    "project_id": getattr(project, "project_id", ""),
                    "final_text": final_text,
                    "turn_mode": updated_board.current_turn_mode,
                    "events": [event.type for event in events],
                },
            },
            {
                "kind": "review_written",
                "payload": {
                    "session_id": getattr(session, "session_id", ""),
                    "project_id": getattr(project, "project_id", ""),
                    "summary": review_summary,
                },
            },
            {
                "kind": "continuation_updated",
                "payload": {
                    "session_id": getattr(session, "session_id", ""),
                    "project_id": getattr(project, "project_id", ""),
                    "continuation_prompt": continuation_prompt,
                },
            },
        ],
    }
