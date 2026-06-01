"""Board and event lifecycle hooks for learning state."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Any

from colearn.learning.constants import (
    BlockerType,
    LearningEventType,
    LearningPhase,
    NodeStatus,
    TurnMode,
)
from colearn.learning.hook_utils import json_safe, normalize_turn_mode, utc_now
from colearn.learning.signal_extractor import (
    detect_blocked,
    detect_completion,
    detect_understood,
    extract_blocked_concept,
    extract_understood_concepts,
)
from colearn.learning.state import (
    Blocker,
    BoardFacts,
    ContinuationFacts,
    GapsAndBlockers,
    LearningBoard,
    LearningEvent,
    LearningPlan,
    LearningPlanNode,
    LearningStateSnapshot,
    ProgressFacts,
    StudentSnapshot,
)
from colearn.projects.models import LearningProject


def extract_board_facts(
    *,
    project: LearningProject,
    session_id: str,
    continuation_hint: str = "",
    board_version: int = 1,
    turn_mode: TurnMode | str = TurnMode.LEARN,
) -> BoardFacts:
    gaps = list(project.latest_review.get("confusion_points") or [])
    blockers = [
        Blocker(
            id=f"blk_{idx:03d}",
            type=BlockerType.CONCEPT_MISUNDERSTANDING,
            desc=str(gap),
        )
        for idx, gap in enumerate(gaps)
    ]
    active_node_id = project.project_id
    active_node_label = project.title
    evidence_refs = [{"source_ref": item} for item in (project.source_refs or [])]
    progress = ProgressFacts(
        active_node_id=active_node_id,
        active_node_label=active_node_label,
    )
    gaps_and_blockers = GapsAndBlockers(critical_blockers=blockers, unverified_gaps=[])
    continuation = ContinuationFacts(next_prompt_hint=continuation_hint)
    learning_plan = LearningPlan(
        goal=str(project.goal or project.title or ""),
        plan_nodes=[
            LearningPlanNode(
                id=active_node_id,
                label=active_node_label,
                status=NodeStatus.CURRENT,
                depth=0,
                summary=active_node_label,
            )
        ],
        current_node_id=active_node_id,
    )
    learning_board = LearningBoard.derive(
        current_progress=progress,
        gaps_and_blockers=gaps_and_blockers,
        continuation=continuation,
        evidence_refs=evidence_refs,
    )
    return BoardFacts(
        project_id=project.project_id,
        session_id=session_id,
        current_turn_mode=normalize_turn_mode(turn_mode),
        board_version=board_version,
        updated_at="",
        current_progress=progress,
        student_snapshot=StudentSnapshot(
            mastery_level=0.0,
            last_user_intent_raw="",
        ),
        gaps_and_blockers=gaps_and_blockers,
        continuation=continuation,
        evidence_refs=evidence_refs,
        learning_plan=learning_plan,
        learning_board=learning_board,
    )


def _coerce_learning_plan(raw: Any, *, project: LearningProject, progress: ProgressFacts) -> LearningPlan:
    data = dict(raw or {})
    nodes = [
        LearningPlanNode(
            id=str(item.get("id") or ""),
            label=str(item.get("label") or ""),
            status=str(item.get("status") or "pending"),
            depth=int(item.get("depth") or 0),
            summary=str(item.get("summary") or ""),
        )
        for item in list(data.get("plan_nodes") or [])
        if isinstance(item, dict)
    ]
    current_node_id = str(data.get("current_node_id") or progress.active_node_id or "")
    if not nodes and current_node_id:
        nodes.append(
            LearningPlanNode(
                id=current_node_id,
                label=str(progress.active_node_label or project.title or ""),
                status=NodeStatus.CURRENT,
                depth=0,
                summary=str(progress.active_node_label or project.title or ""),
            )
        )
    return LearningPlan(
        goal=str(data.get("goal") or getattr(project, "goal", "") or project.title or ""),
        plan_nodes=nodes,
        current_node_id=current_node_id,
        review_queue=[str(item) for item in list(data.get("review_queue") or [])],
        pending_checks=[str(item) for item in list(data.get("pending_checks") or [])],
    )


def _coerce_learning_board(
    raw: Any,
    *,
    progress: ProgressFacts,
    gaps: GapsAndBlockers,
    continuation: ContinuationFacts,
    evidence_refs: list[dict[str, Any]],
) -> LearningBoard:
    data = dict(raw or {})
    return LearningBoard(
        current_progress=str(data.get("current_progress") or progress.active_node_label or ""),
        completed_nodes=[str(item) for item in list(data.get("completed_nodes") or progress.completed_node_ids or [])],
        blockers=[
            str(item)
            for item in list(
                data.get("blockers") or [blocker.desc for blocker in gaps.critical_blockers if blocker.desc]
            )
        ],
        objections=[str(item) for item in list(data.get("objections") or [])],
        evidence_refs=[
            str(item)
            for item in list(
                data.get("evidence_refs")
                or [ref.get("source_ref") for ref in evidence_refs if isinstance(ref, dict) and ref.get("source_ref")]
            )
        ],
        continuation=str(data.get("continuation") or continuation.next_prompt_hint or ""),
    )


def build_learning_board(
    *,
    project: LearningProject,
    session: Any,
    latest_review: dict[str, Any] | None = None,
) -> BoardFacts:
    raw = dict(getattr(session, "board_facts", None) or {})
    if raw:
        progress = ProgressFacts(**dict(raw.get("current_progress") or {}))
        gaps = GapsAndBlockers(
            critical_blockers=[
                Blocker(**dict(item))
                for item in list((raw.get("gaps_and_blockers") or {}).get("critical_blockers") or [])
            ],
            unverified_gaps=list((raw.get("gaps_and_blockers") or {}).get("unverified_gaps") or []),
        )
        continuation = ContinuationFacts(**dict(raw.get("continuation") or {}))
        evidence_refs = list(raw.get("evidence_refs") or [])
        return BoardFacts(
            project_id=str(raw.get("project_id") or project.project_id),
            session_id=str(raw.get("session_id") or getattr(session, "session_id", "")),
            current_turn_mode=normalize_turn_mode(raw.get("current_turn_mode")),
            board_version=int(raw.get("board_version") or getattr(session, "board_version", 1) or 1),
            updated_at=str(raw.get("updated_at") or ""),
            current_progress=progress,
            student_snapshot=StudentSnapshot(**dict(raw.get("student_snapshot") or {})),
            gaps_and_blockers=gaps,
            continuation=continuation,
            evidence_refs=evidence_refs,
            learning_plan=_coerce_learning_plan(raw.get("learning_plan"), project=project, progress=progress),
            learning_board=_coerce_learning_board(
                raw.get("learning_board"),
                progress=progress,
                gaps=gaps,
                continuation=continuation,
                evidence_refs=evidence_refs,
            ),
        )
    continuation_hint = str((latest_review or {}).get("continuation_prompt") or "")
    return extract_board_facts(
        project=project,
        session_id=getattr(session, "session_id", ""),
        continuation_hint=continuation_hint,
        board_version=int(getattr(session, "board_version", 1) or 1),
        turn_mode=getattr(session, "turn_mode", getattr(project, "turn_mode", "LEARN")),
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
    _ = user_message
    current = normalize_turn_mode(board.current_turn_mode)
    if current == TurnMode.PAUSED:
        return TurnMode.PAUSED
    if current == TurnMode.CHECK:
        return TurnMode.CHECK
    if board.gaps_and_blockers.critical_blockers:
        return TurnMode.CHECK
    if board.gaps_and_blockers.unverified_gaps:
        return TurnMode.CHECK
    return TurnMode.LEARN


def resolve_model_preset(turn_mode: TurnMode) -> str | None:
    return {
        "LEARN": "explore",
        "CHECK": "deep",
        "PAUSED": None,
    }.get(turn_mode)


def _first_understood_concept(text: str) -> str:
    concepts = extract_understood_concepts(text)
    return concepts[0] if concepts else ""


def _match_resolved_blockers(blockers: list[Blocker], understood_concept: str) -> list[Blocker]:
    """Pick which open blockers an "understood" signal resolves.

    When a concept is parseable, resolve only blockers whose description overlaps
    it (conservative — avoids clearing unrelated blockers). When no concept can be
    parsed but understanding is clearly signaled and exactly one blocker is open,
    resolve that one. With multiple open blockers and no concept, resolve nothing
    rather than risk clearing the wrong one.
    """
    if not blockers:
        return []
    concept = (understood_concept or "").strip().lower()
    if concept:
        matched = [
            blocker
            for blocker in blockers
            if blocker.desc and (concept in blocker.desc.lower() or blocker.desc.lower() in concept)
        ]
        if matched:
            return matched
    if len(blockers) == 1:
        return [blockers[0]]
    return []


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
            type=LearningEventType.CONTINUATION_UPDATED,
            payload=json_safe(
                {
                    "next_prompt_hint": f"Continue from {board.current_progress.active_node_label}",
                    "last_completed_turn_id": user_message[:80],
                }
            ),
        ),
    ]

    tool_names = [
        str(item.get("tool_name") or item.get("tool") or "")
        for item in list(tool_events or [])
        if str(item.get("tool_name") or item.get("tool") or "")
    ]
    source_refs = list(source_references or [])
    active_node_id = board.current_progress.active_node_id
    existing_blockers = list(board.gaps_and_blockers.critical_blockers or [])

    # Completion signal — bilingual. Retrieval (lightrag) NEVER implies mastery;
    # it only attaches evidence (handled in the source_refs loop below). A node is
    # completed when the final text carries an explicit completion marker, or when
    # the student signals understanding while in CHECK mode (i.e. they passed the
    # check). The CHECK gate keeps a bare "I get it" mid-explanation from prematurely
    # closing the node, while the explicit-marker path is the fallback that keeps
    # progress moving even though mastery_level has no write source yet.
    in_check = normalize_turn_mode(board.current_turn_mode) == TurnMode.CHECK
    completion_signaled = detect_completion(final_text) or (in_check and detect_understood(final_text))

    if active_node_id and completion_signaled:
        events.append(
            LearningEvent(
                type=LearningEventType.NODE_COMPLETED,
                payload=json_safe(
                    {
                        "node_id": active_node_id,
                        "node_label": board.current_progress.active_node_label,
                        "signal": "completion_marker" if detect_completion(final_text) else "check_understood",
                    }
                ),
            )
        )
    elif active_node_id and not board.current_progress.completed_node_ids:
        events.append(
            LearningEvent(
                type=LearningEventType.NODE_STARTED,
                payload=json_safe(
                    {
                        "node_id": active_node_id,
                        "node_label": board.current_progress.active_node_label,
                        "signal": "default",
                    }
                ),
            )
        )

    # Blocker detection — bilingual, read from the user's message (where confusion
    # is expressed). Replaces the previous English-only marker list.
    if detect_blocked(user_message):
        blocker_id = hashlib.sha1(user_message[:240].encode("utf-8")).hexdigest()[:10]
        events.append(
            LearningEvent(
                type=LearningEventType.BLOCKER_FOUND,
                payload=json_safe(
                    {
                        "id": f"blk_{blocker_id}",
                        "type": BlockerType.CONCEPT_MISUNDERSTANDING,
                        "desc": extract_blocked_concept(user_message) or user_message[:240],
                        "signal": "user_message",
                    }
                ),
            )
        )

    # Blocker resolution — when the student signals understanding (in either the
    # user message or the AI reply) and open blockers exist, resolve them so the
    # state machine can leave CHECK. Without this, any blocker pinned CHECK forever.
    if existing_blockers and (detect_understood(final_text) or detect_understood(user_message)):
        understood_concept = ""
        for candidate in (final_text, user_message):
            understood_concept = _first_understood_concept(candidate)
            if understood_concept:
                break
        resolved = _match_resolved_blockers(existing_blockers, understood_concept)
        for blocker in resolved:
            events.append(
                LearningEvent(
                    type=LearningEventType.BLOCKER_RESOLVED,
                    payload=json_safe(
                        {
                            "id": blocker.id,
                            "desc": blocker.desc,
                            "signal": "understood",
                        }
                    ),
                )
            )

    for idx, ref in enumerate(source_refs):
        raw_ref = str(ref.get("source_ref") or ref.get("source_path") or ref.get("path") or "").strip()
        if not raw_ref:
            continue
        events.append(
            LearningEvent(
                type=LearningEventType.EVIDENCE_ATTACHED,
                payload=json_safe(
                    {
                        "source_ref": raw_ref,
                        "tool_name": tool_names[0] if tool_names else "",
                        "chunk_id": str(ref.get("chunk_id") or f"source_{idx}"),
                        "signal": "source_reference",
                    }
                ),
            )
        )

    return events


def resolve_turn_mode_after(
    *,
    board_before: BoardFacts,
    board_after: BoardFacts,
    events: list[LearningEvent],
) -> TurnMode:
    before_mode = normalize_turn_mode(board_before.current_turn_mode)
    # Explicit pause is sticky; only an upstream explicit resume leaves PAUSED.
    if before_mode == TurnMode.PAUSED:
        return TurnMode.PAUSED

    event_types = {event.type for event in events}
    # board_after already had resolved blockers removed by apply_events, so this
    # list reflects only blockers that genuinely survived this turn.
    remaining_blockers = list(board_after.gaps_and_blockers.critical_blockers or [])
    unverified_gaps = list(board_after.gaps_and_blockers.unverified_gaps or [])

    # A newly surfaced blocker forces a CHECK so we address it next turn.
    if LearningEventType.BLOCKER_FOUND in event_types:
        return TurnMode.CHECK

    # Fallback: if CHECK mode persists for 3+ turns without BLOCKER_RESOLVED,
    # force clear blockers and return to LEARN to prevent infinite CHECK loop.
    check_turns = board_before.check_mode_turns if before_mode == TurnMode.CHECK else 0
    if remaining_blockers and check_turns >= 3:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"CHECK mode persisted for {check_turns} turns without resolution. "
            f"Force-clearing {len(remaining_blockers)} blockers to prevent deadlock."
        )
        # Clear blockers in board_after (mutate in place since we're in resolution phase)
        board_after.gaps_and_blockers.critical_blockers = []
        return TurnMode.LEARN

    # Unresolved blockers keep us in CHECK — but a blocker that was cleared this
    # turn no longer counts, so a resolved blocker can't pin CHECK forever.
    if remaining_blockers:
        return TurnMode.CHECK
    # Clearing the last blocker this turn returns us to normal learning.
    if LearningEventType.BLOCKER_RESOLVED in event_types:
        return TurnMode.LEARN
    if before_mode == TurnMode.LEARN and LearningEventType.NODE_COMPLETED in event_types:
        return TurnMode.CHECK
    if before_mode == TurnMode.CHECK and LearningEventType.NODE_COMPLETED in event_types:
        return TurnMode.LEARN
    if unverified_gaps:
        return TurnMode.CHECK
    if LearningEventType.NODE_COMPLETED in event_types and board_after.current_progress.active_node_id:
        return TurnMode.LEARN
    return before_mode


def apply_events(
    board: BoardFacts,
    events: list[LearningEvent],
) -> BoardFacts:
    # Sort events: user corrections last (highest priority, will override model events)
    def event_priority(event: LearningEvent) -> int:
        source = event.payload.get("source", "")
        if source == "user_correction":
            return 1  # Apply last
        return 0  # Model-derived events apply first

    sorted_events = sorted(events, key=event_priority)

    completed_node_ids = list(board.current_progress.completed_node_ids)
    blockers = list(board.gaps_and_blockers.critical_blockers)
    continuation = board.continuation
    evidence_refs = list(board.evidence_refs)
    plan = board.learning_plan

    for event in sorted_events:
        if event.type == LearningEventType.NODE_COMPLETED:
            node_id = str(event.payload.get("node_id") or "")
            if node_id and node_id not in completed_node_ids:
                completed_node_ids.append(node_id)
        elif event.type == LearningEventType.CONTINUATION_UPDATED:
            continuation = ContinuationFacts(
                next_prompt_hint=str(event.payload.get("next_prompt_hint") or continuation.next_prompt_hint),
                last_completed_turn_id=str(
                    event.payload.get("last_completed_turn_id") or continuation.last_completed_turn_id
                ),
            )
        elif event.type == LearningEventType.BLOCKER_FOUND:
            blocker = Blocker(
                id=str(event.payload.get("id") or f"blk_{len(blockers):03d}"),
                type=BlockerType(str(event.payload.get("type") or BlockerType.CONCEPT_MISUNDERSTANDING)),
                desc=str(event.payload.get("desc") or ""),
            )
            if blocker.id not in {item.id for item in blockers}:
                blockers.append(blocker)
        elif event.type == LearningEventType.BLOCKER_RESOLVED:
            resolved_id = str(event.payload.get("id") or "")
            if resolved_id:
                blockers = [item for item in blockers if item.id != resolved_id]
        elif event.type == LearningEventType.EVIDENCE_ATTACHED:
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

    plan_nodes: list[LearningPlanNode] = []
    for node in list(plan.plan_nodes or []):
        status = node.status
        if node.id and node.id in completed_node_ids:
            status = "completed"
        elif node.id and node.id == board.current_progress.active_node_id:
            status = "current"
        plan_nodes.append(
            LearningPlanNode(
                id=node.id,
                label=node.label,
                status=status,
                depth=node.depth,
                summary=node.summary,
            )
        )
    if board.current_progress.active_node_id and not any(
        node.id == board.current_progress.active_node_id for node in plan_nodes
    ):
        plan_nodes.append(
            LearningPlanNode(
                id=board.current_progress.active_node_id,
                label=board.current_progress.active_node_label,
                status=NodeStatus.CURRENT,
                depth=0,
                summary=board.current_progress.active_node_label,
            )
        )
    updated_plan = LearningPlan(
        goal=plan.goal,
        plan_nodes=plan_nodes,
        current_node_id=board.current_progress.active_node_id or plan.current_node_id,
        review_queue=list(plan.review_queue or []),
        pending_checks=list(plan.pending_checks or board.gaps_and_blockers.unverified_gaps or []),
    )
    updated_progress = ProgressFacts(
        active_node_id=board.current_progress.active_node_id,
        active_node_label=board.current_progress.active_node_label,
        completed_node_ids=completed_node_ids,
        path_node_ids=list(board.current_progress.path_node_ids),
    )
    updated_gaps = GapsAndBlockers(
        critical_blockers=blockers,
        unverified_gaps=list(board.gaps_and_blockers.unverified_gaps),
    )
    updated_learning_board = LearningBoard.derive(
        current_progress=updated_progress,
        gaps_and_blockers=updated_gaps,
        continuation=continuation,
        evidence_refs=evidence_refs,
        objections=list(board.learning_board.objections or []),
    )

    updated = BoardFacts(
        project_id=board.project_id,
        session_id=board.session_id,
        current_turn_mode=board.current_turn_mode,
        board_version=board.board_version + 1,
        updated_at=utc_now(),
        current_progress=updated_progress,
        student_snapshot=board.student_snapshot,
        gaps_and_blockers=updated_gaps,
        continuation=continuation,
        evidence_refs=evidence_refs,
        learning_plan=updated_plan,
        learning_board=updated_learning_board,
    )
    next_mode = resolve_turn_mode_after(
        board_before=board,
        board_after=updated,
        events=events,
    )
    # Update check_mode_turns counter
    if next_mode == TurnMode.CHECK:
        check_turns = board.check_mode_turns + 1 if board.current_turn_mode == TurnMode.CHECK else 1
    else:
        check_turns = 0
    updated = replace(updated, current_turn_mode=next_mode, check_mode_turns=check_turns)
    all_nodes_done = (
        len(plan_nodes) > 1
        and all(node.status == "completed" for node in plan_nodes)
    )
    if all_nodes_done and getattr(board, "learning_phase", "ready") == "ready":
        updated = replace(updated, learning_phase=LearningPhase.REFLECT)
    return updated


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
