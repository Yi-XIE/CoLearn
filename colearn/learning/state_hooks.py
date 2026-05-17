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


SUPPORT_TYPES = {
    "definition",
    "prerequisite",
    "example",
    "counterexample",
    "procedure",
    "reference",
    "extension",
    "comparison",
}

MODE_SUPPORT_PRIORITIES: dict[str, list[str]] = {
    "ANCHOR": ["definition", "prerequisite", "example", "reference", "extension"],
    "CORRECTION": ["counterexample", "comparison", "definition", "reference", "example"],
    "VERIFY": ["procedure", "reference", "definition", "example"],
    "EXPLORE": ["example", "extension", "comparison", "definition", "reference"],
    "PAUSED": ["reference", "definition", "example"],
}

SUPPORT_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("counterexample", ("反例", "误区", "常见错误", "错误", "counterexample", "mistake")),
    ("procedure", ("步骤", "证明", "推导", "做法", "流程", "procedure", "step", "proof")),
    ("example", ("例如", "例子", "案例", "示例", "example", "case")),
    ("comparison", ("区别", "对比", "比较", "comparison", "versus", "vs")),
    ("definition", ("定义", "概念", "本质", "definition", "concept")),
    ("reference", ("来源", "依据", "定理", "文献", "reference", "source", "theorem")),
    ("extension", ("延伸", "拓展", "进一步", "extension", "advanced")),
    ("prerequisite", ("前置", "先修", "基础", "prerequisite", "foundation")),
]


def _evidence_sort_key(item: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(item.get("source_ref") or item.get("source_path") or ""),
        str(item.get("chunk_id") or ""),
        str(item.get("support_type") or ""),
        str(item.get("target_type") or ""),
        str(item.get("target_id") or ""),
    )


def _dedupe_evidence_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in sorted(items, key=_evidence_sort_key):
        signature = (
            str(item.get("source_ref") or item.get("source_path") or ""),
            str(item.get("chunk_id") or ""),
            str(item.get("support_type") or ""),
            str(item.get("target_type") or ""),
            str(item.get("target_id") or ""),
        )
        if signature in seen:
            continue
        seen.add(signature)
        result.append(item)
    return result


def _compact_text(value: Any, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 1, 1)].rstrip()}…"


def _source_label(ref: dict[str, Any]) -> str:
    raw = str(
        ref.get("title")
        or ref.get("source_ref")
        or ref.get("source_path")
        or ref.get("path")
        or "source"
    ).strip()
    return raw.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] or raw


def infer_support_type(ref: dict[str, Any]) -> str:
    explicit = str(ref.get("support_type") or "").strip().lower()
    if explicit in SUPPORT_TYPES:
        return explicit
    haystack = " ".join(
        str(ref.get(key) or "")
        for key in ("summary", "text", "title", "source_ref", "source_path")
    ).lower()
    for support_type, keywords in SUPPORT_TYPE_KEYWORDS:
        if any(keyword.lower() in haystack for keyword in keywords):
            return support_type
    return "reference"


def build_retrieval_query_context(
    *,
    board: BoardFacts,
    user_message: str,
    retrieval_focus: dict[str, Any],
    continuation_prompt: str = "",
) -> dict[str, Any]:
    blockers = [
        {"id": blocker.id, "desc": blocker.desc, "type": blocker.type}
        for blocker in list(board.gaps_and_blockers.critical_blockers or [])
        if str(blocker.desc or "").strip()
    ]
    gaps = [str(item).strip() for item in board.gaps_and_blockers.unverified_gaps if str(item).strip()]
    parts = [
        str(retrieval_focus.get("default_query") or "").strip(),
        str(board.current_progress.active_node_label or board.current_progress.active_node_id or "").strip(),
        str(user_message or "").strip(),
        "；".join(item["desc"] for item in blockers[:2] if item.get("desc")),
        "；".join(gaps[:2]),
        str(continuation_prompt or board.continuation.next_prompt_hint or "").strip(),
    ]
    final_query = " | ".join(part for part in parts if part)
    return {
        "turn_mode": _normalize_turn_mode(board.current_turn_mode),
        "active_node_id": str(board.current_progress.active_node_id or "").strip(),
        "active_node_label": str(board.current_progress.active_node_label or "").strip(),
        "user_message": str(user_message or "").strip(),
        "critical_blockers": blockers,
        "unverified_gaps": gaps,
        "continuation_prompt": str(continuation_prompt or board.continuation.next_prompt_hint or "").strip(),
        "evidence_refs": list(board.evidence_refs or []),
        "default_query": str(retrieval_focus.get("default_query") or "").strip(),
        "final_query": final_query,
    }


def _support_target_for(
    *,
    board: BoardFacts,
    support_type: str,
    turn_mode: str,
    index: int,
    ref: dict[str, Any],
) -> dict[str, str]:
    explicit_target = ref.get("support_target")
    if isinstance(explicit_target, dict):
        target_type = str(explicit_target.get("type") or explicit_target.get("target_type") or "").strip()
        target_id = str(explicit_target.get("id") or explicit_target.get("target_id") or "").strip()
        target_label = str(explicit_target.get("label") or explicit_target.get("target_label") or "").strip()
        if target_type and target_id:
            return {"target_type": target_type, "target_id": target_id, "target_label": target_label}
    target_type = str(ref.get("target_type") or "").strip()
    target_id = str(ref.get("target_id") or "").strip()
    if target_type and target_id:
        return {
            "target_type": target_type,
            "target_id": target_id,
            "target_label": str(ref.get("target_label") or ""),
        }

    blockers = list(board.gaps_and_blockers.critical_blockers or [])
    gaps = [str(item).strip() for item in board.gaps_and_blockers.unverified_gaps if str(item).strip()]
    if (
        turn_mode in {"CORRECTION", "VERIFY"}
        or support_type in {"counterexample", "comparison"}
    ) and blockers:
        blocker = blockers[index % len(blockers)]
        return {"target_type": "blocker", "target_id": blocker.id, "target_label": blocker.desc}
    if turn_mode == "VERIFY" and gaps:
        gap_index = index % len(gaps)
        return {"target_type": "gap", "target_id": f"gap_{gap_index:03d}", "target_label": gaps[gap_index]}
    node_id = str(board.current_progress.active_node_id or board.project_id or "").strip()
    return {
        "target_type": "node",
        "target_id": node_id,
        "target_label": str(board.current_progress.active_node_label or node_id),
    }


def _support_priority_score(*, support_type: str, turn_mode: str, raw_score: Any) -> float:
    priorities = MODE_SUPPORT_PRIORITIES.get(turn_mode, MODE_SUPPORT_PRIORITIES["EXPLORE"])
    try:
        source_score = float(raw_score)
    except (TypeError, ValueError):
        source_score = 0.0
    priority_index = priorities.index(support_type) if support_type in priorities else len(priorities)
    priority_score = max(len(priorities) - priority_index, 0) / max(len(priorities), 1)
    return round(priority_score + min(max(source_score, 0.0), 1.0) * 0.2, 4)


def build_prompt_support_bundle(
    *,
    board: BoardFacts,
    prefetched_references: list[dict[str, Any]],
    retrieval_focus: dict[str, Any] | None = None,
    max_items: int = 4,
) -> list[dict[str, Any]]:
    turn_mode = _normalize_turn_mode((retrieval_focus or {}).get("turn_mode") or board.current_turn_mode)
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for idx, ref in enumerate(prefetched_references):
        raw_ref = str(ref.get("source_ref") or ref.get("source_path") or ref.get("path") or "").strip()
        if not raw_ref:
            continue
        chunk_id = str(ref.get("chunk_id") or f"prefetch_{idx}")
        signature = (raw_ref, chunk_id)
        if signature in seen:
            continue
        seen.add(signature)
        support_type = infer_support_type(ref)
        target = _support_target_for(
            board=board,
            support_type=support_type,
            turn_mode=turn_mode,
            index=idx,
            ref=ref,
        )
        raw_summary = ref.get("summary") or ref.get("text") or ref.get("content") or ref.get("title") or _source_label(ref)
        summary = _compact_text(raw_summary, limit=180)
        score = _support_priority_score(
            support_type=support_type,
            turn_mode=turn_mode,
            raw_score=ref.get("score"),
        )
        candidates.append(
            {
                "source_ref": raw_ref,
                "source_path": str(ref.get("source_path") or ""),
                "title": str(ref.get("title") or _source_label(ref)),
                "chunk_id": chunk_id,
                "support_type": support_type,
                "summary": summary,
                "target_type": target["target_type"],
                "target_id": target["target_id"],
                "target_label": target["target_label"],
                "support_target": {
                    "type": target["target_type"],
                    "id": target["target_id"],
                    "label": target["target_label"],
                },
                "support_reason": (
                    f"{support_type} material supports "
                    f"{target['target_type']} {target['target_label'] or target['target_id']}."
                ),
                "score": score,
                "confidence": score,
            }
        )
    candidates.sort(
        key=lambda item: (
            -float(item.get("score") or 0),
            str(item.get("source_ref") or ""),
            str(item.get("chunk_id") or ""),
        )
    )
    return candidates[: max(max_items, 0)]


def build_retrieval_focus(
    *,
    board: BoardFacts,
    turn_mode: str | None = None,
) -> dict[str, Any]:
    resolved_mode = _normalize_turn_mode(turn_mode or board.current_turn_mode)
    active_node_id = str(board.current_progress.active_node_id or "").strip()
    blocker_refs = [
        {
            "blocker_id": blocker.id,
            "blocker_desc": blocker.desc,
            "blocker_type": blocker.type,
        }
        for blocker in list(board.gaps_and_blockers.critical_blockers or [])
        if str(blocker.desc or "").strip()
    ]
    evidence_refs = list(board.evidence_refs or [])
    focus: dict[str, Any] = {
        "turn_mode": resolved_mode,
        "active_node_id": active_node_id,
        "active_node_label": str(board.current_progress.active_node_label or "").strip(),
        "critical_blockers": blocker_refs,
        "unverified_gaps": [str(item).strip() for item in board.gaps_and_blockers.unverified_gaps if str(item).strip()],
        "evidence_refs": evidence_refs,
    }
    focus["default_query"] = {
        "ANCHOR": "基础定义、前置知识、关键概念",
        "CORRECTION": "反例、纠错证据、概念对照",
        "VERIFY": "步骤核验、来源依据、推理链",
        "EXPLORE": "当前节点扩展资料、相关例子、延伸理解",
        "PAUSED": "当前学习节点背景资料",
    }.get(resolved_mode, "当前学习节点背景资料")
    if active_node_id:
        focus["scope"] = {
            "active_node_id": active_node_id,
            "active_node_label": str(board.current_progress.active_node_label or "").strip(),
        }
    return focus


def build_retrieval_evidence_map(
    *,
    board: BoardFacts,
    prefetched_references: list[dict[str, Any]],
    prompt_support_bundle: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    active_node_id = str(board.current_progress.active_node_id or "").strip()
    support_rows = prompt_support_bundle
    if support_rows is None:
        support_rows = build_prompt_support_bundle(
            board=board,
            prefetched_references=prefetched_references,
            retrieval_focus={"turn_mode": board.current_turn_mode},
        )
    evidence_map: dict[str, list[dict[str, Any]]] = {}
    for idx, ref in enumerate(support_rows):
        raw_ref = str(ref.get("source_ref") or ref.get("source_path") or ref.get("path") or "").strip()
        if not raw_ref:
            continue
        chunk_id = str(ref.get("chunk_id") or f"prefetch_{idx}")
        support_type = infer_support_type(ref)
        target_type = str(ref.get("target_type") or (ref.get("support_target") or {}).get("type") or "node")
        target_id = str(ref.get("target_id") or (ref.get("support_target") or {}).get("id") or active_node_id)
        target_label = str(ref.get("target_label") or (ref.get("support_target") or {}).get("label") or target_id)
        hit = {
            "source_ref": raw_ref,
            "source_path": str(ref.get("source_path") or ""),
            "title": str(ref.get("title") or _source_label(ref)),
            "chunk_id": chunk_id,
            "support_type": support_type,
            "active_node_id": active_node_id,
            "target_type": target_type,
            "target_id": target_id,
            "target_label": target_label,
            "support_target": {"type": target_type, "id": target_id, "label": target_label},
            "support_targets": [target_id] if target_id else [],
            "support_reason": str(ref.get("support_reason") or ""),
            "confidence": float(ref.get("confidence") or ref.get("score") or 0),
            "summary": str(ref.get("summary") or ""),
        }
        for key in [target_id, f"chunk:{chunk_id}"]:
            if key:
                evidence_map.setdefault(key, []).append(hit)
    return {key: _dedupe_evidence_items(value) for key, value in evidence_map.items()}


def build_retrieval_reason(
    *,
    board: BoardFacts,
    source_readiness: dict[str, Any] | None = None,
) -> str:
    mode = _normalize_turn_mode(board.current_turn_mode)
    blockers = list(board.gaps_and_blockers.critical_blockers or [])
    if blockers:
        return f"{mode} turn needs evidence for {len(blockers)} critical blocker(s)."
    if mode == "VERIFY":
        return "VERIFY turn needs source-backed validation."
    if mode == "CORRECTION":
        return "CORRECTION turn needs counterexamples and correction evidence."
    if mode == "ANCHOR":
        return "ANCHOR turn needs base definitions and prerequisites."
    if source_readiness and str(source_readiness.get("readiness") or "").lower() != "ready":
        return f"Source readiness is {source_readiness.get('readiness', 'unknown')}; prefetch to reduce turn risk."
    return f"{mode} turn needs background support for the active learning node."


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
    if board.current_turn_mode in {"ANCHOR", "CORRECTION", "VERIFY"}:
        return board.current_turn_mode
    if not board.current_progress.active_node_id:
        return "ANCHOR"
    if board.gaps_and_blockers.critical_blockers:
        return "CORRECTION"
    if board.gaps_and_blockers.unverified_gaps:
        return "VERIFY"
    return "EXPLORE"


def resolve_model_preset(turn_mode: TurnMode) -> str | None:
    return {
        "EXPLORE": "explore",
        "ANCHOR": "deep",
        "CORRECTION": "deep",
        "VERIFY": "deep",
        "PAUSED": None,
    }.get(turn_mode)


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
        },
    )


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
            payload=_json_safe(
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
    final_lower = final_text.lower()
    user_lower = user_message.lower()

    if any(name == "lightrag" for name in tool_names) and board.current_progress.active_node_id:
        events.append(
            LearningEvent(
                type="NODE_COMPLETED",
                payload=_json_safe(
                    {
                        "node_id": board.current_progress.active_node_id,
                        "node_label": board.current_progress.active_node_label,
                        "signal": "tool:lightrag",
                    }
                ),
            )
        )
    elif board.current_progress.active_node_id and any(
        marker in final_lower for marker in ["completed", "done", "finished", "resolved"]
    ):
        events.append(
            LearningEvent(
                type="NODE_COMPLETED",
                payload=_json_safe(
                    {
                        "node_id": board.current_progress.active_node_id,
                        "node_label": board.current_progress.active_node_label,
                        "signal": "final_text",
                    }
                ),
            )
        )
    elif board.current_progress.active_node_id and not board.current_progress.completed_node_ids:
        events.append(
            LearningEvent(
                type="NODE_STARTED",
                payload=_json_safe(
                    {
                        "node_id": board.current_progress.active_node_id,
                        "node_label": board.current_progress.active_node_label,
                        "signal": "default",
                    }
                ),
            )
        )

    blocker_markers = ["confused", "stuck", "unclear", "unsure", "uncertain"]
    if any(marker in user_lower for marker in blocker_markers):
        blocker_id = hashlib.sha1(user_message[:240].encode("utf-8")).hexdigest()[:10]
        events.append(
            LearningEvent(
                type="BLOCKER_FOUND",
                payload=_json_safe(
                    {
                        "id": f"blk_{blocker_id}",
                        "type": "CONCEPT_MISUNDERSTANDING",
                        "desc": user_message[:240],
                        "signal": "user_message",
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
                type="EVIDENCE_ATTACHED",
                payload=_json_safe(
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
    event_types = {event.type for event in events}
    blockers = list(board_after.gaps_and_blockers.critical_blockers or [])
    unverified_gaps = list(board_after.gaps_and_blockers.unverified_gaps or [])

    if "BLOCKER_FOUND" in event_types or blockers:
        return "CORRECTION"
    if "NODE_STARTED" in event_types and not board_before.current_progress.active_node_id:
        return "ANCHOR"
    if unverified_gaps:
        return "VERIFY"
    if "NODE_COMPLETED" in event_types and board_after.current_progress.active_node_id:
        return "EXPLORE"
    if not board_after.current_progress.active_node_id:
        return "ANCHOR"
    return _normalize_turn_mode(board_before.current_turn_mode)


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

    updated = BoardFacts(
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
    next_mode = resolve_turn_mode_after(
        board_before=board,
        board_after=updated,
        events=events,
    )
    return replace(updated, current_turn_mode=next_mode)


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
    retrieval_hits = _dedupe_evidence_items(list(getattr(request, "metadata", {}).get("retrieval_hits") or []))
    retrieval_misses = list(getattr(request, "metadata", {}).get("retrieval_misses") or [])
    prompt_support_bundle = list(getattr(request, "metadata", {}).get("prompt_support_bundle") or [])
    retrieval_query_context = dict(getattr(request, "metadata", {}).get("retrieval_query_context") or {})
    retrieval_evidence_map = {
        key: _dedupe_evidence_items(list(value or []))
        for key, value in dict(getattr(request, "metadata", {}).get("retrieval_evidence_map") or {}).items()
    }
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
        "retrieval_hits": retrieval_hits,
        "retrieval_misses": retrieval_misses,
        "prompt_support_bundle": prompt_support_bundle,
        "retrieval_query_context": retrieval_query_context,
        "retrieval_evidence_map": retrieval_evidence_map,
        "knowledge_support_summary": {
            "active_node_id": updated_board.current_progress.active_node_id,
            "critical_blockers": [blocker.id for blocker in updated_board.gaps_and_blockers.critical_blockers],
            "evidence_ref_count": len(updated_board.evidence_refs or []),
            "retrieval_hit_count": len(retrieval_hits),
        },
        "blocker_support_refs": {
            blocker.id: _dedupe_evidence_items([ref for ref in retrieval_evidence_map.get(blocker.id, []) if isinstance(ref, dict)])
            for blocker in updated_board.gaps_and_blockers.critical_blockers
        },
        "continuation_retrieval_hint": {
            "active_node_id": updated_board.current_progress.active_node_id,
            "evidence_refs": list(updated_board.evidence_refs or []),
            "retrieval_focus": getattr(request, "metadata", {}).get("retrieval_focus", {}),
            "retrieval_query_context": retrieval_query_context,
        },
        "writeback_envelope": {
            "turn_mode_before": turn_mode_before,
            "turn_mode_after": updated_board.current_turn_mode,
            "base_board_version": base_board_version,
            "resolved_board_version": resolved_board_version,
            "event_types": event_types,
        },
        "memory_events": [
            {
                "kind": "turn_completed",
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
