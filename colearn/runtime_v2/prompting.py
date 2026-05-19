"""Prompt construction for the CoLearn v0.2 runtime line."""

from __future__ import annotations

from pathlib import Path

from nanobot.agent.context import ContextBuilder

from colearn.learning.turn_contract import LearningTurnRequest
from colearn.paths import colearn_repo_root


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

    retrieval_focus = dict(request.metadata.get("retrieval_focus") or {})
    if retrieval_focus:
        focus_bits: list[str] = []
        turn_mode = str(retrieval_focus.get("turn_mode") or "").strip()
        if turn_mode:
            focus_bits.append(f"mode={turn_mode}")
        active_node_id = str(retrieval_focus.get("active_node_id") or "").strip()
        if active_node_id:
            focus_bits.append(f"node={active_node_id}")
        default_query = str(retrieval_focus.get("default_query") or "").strip()
        if default_query:
            focus_bits.append(f"query={default_query}")
        if focus_bits:
            lines.append(f"Retrieval focus: {'; '.join(focus_bits)}")

    prefetched = list(request.metadata.get("prefetched_references") or [])
    if prefetched:
        lines.append(f"Prefetched references: {len(prefetched)}")

    retrieval_reason = str(request.metadata.get("retrieval_reason") or "").strip()
    if retrieval_reason:
        lines.append(f"Retrieval reason: {retrieval_reason}")

    support_bundle = list(request.metadata.get("prompt_support_bundle") or [])
    if support_bundle:
        support_lines = ["Prompt support bundle:"]
        for item in support_bundle[:4]:
            support_type = str(item.get("support_type") or "reference").strip()
            summary = str(item.get("summary") or "").strip()
            source = str(item.get("source_ref") or item.get("source_path") or "").strip()
            chunk_id = str(item.get("chunk_id") or "").strip()
            target_type = str(item.get("target_type") or (item.get("support_target") or {}).get("type") or "").strip()
            target_label = str(
                item.get("target_label")
                or (item.get("support_target") or {}).get("label")
                or (item.get("support_target") or {}).get("id")
                or ""
            ).strip()
            source_bits = "#".join(part for part in [source, chunk_id] if part)
            target_bits = " ".join(part for part in [target_type, target_label] if part)
            support_lines.append(
                f"- [{support_type}] {summary} (source: {source_bits}; target: {target_bits})"
            )
        lines.append("\n".join(support_lines))

    return lines


def build_turn_prompt(request: LearningTurnRequest) -> str:
    workspace = Path(str(request.metadata.get("workspace") or ".")).resolve()
    # skill_names is passed but currently unused by nanobot's ContextBuilder —
    # always-skills auto-activate via frontmatter `always: true`, and non-always
    # skills appear as summaries for the agent to read_file on demand.
    base_prompt = ContextBuilder(workspace).build_system_prompt(
        skill_names=request.requested_skills or None,
        channel="colearn",
    )
    colearn_context = ""
    for colearn_doc in (workspace / "COLEARN.md", colearn_repo_root() / "COLEARN.md"):
        if colearn_doc.exists():
            colearn_context = colearn_doc.read_text(encoding="utf-8").strip()
            break
    lines = [
        base_prompt,
        f"## COLEARN.md\n\n{colearn_context}" if colearn_context else "",
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
