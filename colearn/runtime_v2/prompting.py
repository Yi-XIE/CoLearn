"""Prompt construction for the CoLearn v0.2 runtime line."""

from __future__ import annotations

from colearn.learning.turn_contract import LearningTurnRequest


def _board_runtime_lines(request: LearningTurnRequest) -> list[str]:
    board = request.board_facts
    snapshot = request.state_projection
    lines: list[str] = []

    active_label = str(
        board.current_progress.active_node_label
        or snapshot.active_node_label
        or board.current_progress.active_node_id
        or snapshot.active_node_id
        or ""
    ).strip()
    if active_label:
        lines.append(f"Learning focus: {active_label}")

    mastery = snapshot.mastery_level or board.student_snapshot.mastery_level
    cognitive_load = str(snapshot.cognitive_load or board.student_snapshot.cognitive_load or "").strip()
    learner_state_bits: list[str] = []
    if mastery:
        learner_state_bits.append(f"mastery={mastery:.2f}")
    if cognitive_load:
        learner_state_bits.append(f"cognitive_load={cognitive_load}")
    if learner_state_bits:
        lines.append(f"Learner state: {'; '.join(learner_state_bits)}")

    blockers = [str(item.desc or item.id or "").strip() for item in board.gaps_and_blockers.critical_blockers]
    blockers = [item for item in blockers if item]
    if blockers:
        lines.append(f"Critical blockers: {'; '.join(blockers[:3])}")

    gaps = [str(item).strip() for item in board.gaps_and_blockers.unverified_gaps if str(item).strip()]
    if gaps:
        lines.append(f"Unverified gaps: {'; '.join(gaps[:3])}")

    next_hint = str(
        request.continuation_prompt
        or board.continuation.next_prompt_hint
        or ""
    ).strip()
    if next_hint:
        lines.append(f"Continuation hint: {next_hint}")

    evidence_count = len(board.evidence_refs or [])
    if evidence_count:
        lines.append(f"Evidence refs attached: {evidence_count}")

    return lines


def build_turn_prompt(request: LearningTurnRequest) -> str:
    lines = [
        f"Project: {request.project_title or request.project_id or 'Untitled Project'}",
        f"Turn mode: {request.turn_mode}",
    ]
    policy = request.turn_policy or request.policy_decision
    if policy and getattr(policy, "main_goal", ""):
        lines.append(f"Main goal: {policy.main_goal}")
    if request.continuation_prompt:
        lines.append(f"Continuation: {request.continuation_prompt}")
    source_profile = dict(request.metadata.get("source_profile") or {})
    if source_profile:
        sync = dict(source_profile.get("sync") or {})
        warnings = list(source_profile.get("warnings") or sync.get("warnings") or [])
        readiness = str(source_profile.get("readiness") or "unknown")
        sync_status = str(source_profile.get("sync_status") or sync.get("sync_status") or "unknown")
        source_count = int(source_profile.get("source_count") or len(source_profile.get("sources") or []))
        hint = (
            f"Source readiness: readiness={readiness}; sync_status={sync_status}; "
            f"available_sources={source_count}"
        )
        if warnings:
            hint = f"{hint}; warnings={'; '.join(str(item) for item in warnings[:3])}"
        lines.append(hint)
    lines.extend(_board_runtime_lines(request))
    restrictions = list(request.metadata.get("policy_restrictions") or [])
    if not restrictions and policy is not None:
        restrictions = list(getattr(policy, "restrictions", []) or [])
    if restrictions:
        lines.append(f"Restrictions: {', '.join(restrictions)}")
    if request.anchor:
        lines.append(f"Anchor: {request.anchor}")
    lines.append("User message:")
    lines.append(request.user_message)
    return "\n\n".join(line for line in lines if line)
