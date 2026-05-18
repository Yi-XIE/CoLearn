"""Retrieval-focused learning state hook helpers."""

from __future__ import annotations

from typing import Any

from colearn.learning.hook_utils import dedupe_evidence_items, normalize_turn_mode
from colearn.learning.state import BoardFacts

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
    ("counterexample", ("\u53cd\u4f8b", "\u8bef\u533a", "\u5e38\u89c1\u9519\u8bef", "\u9519\u8bef", "counterexample", "mistake")),
    ("procedure", ("\u6b65\u9aa4", "\u8bc1\u660e", "\u63a8\u5bfc", "\u505a\u6cd5", "\u6d41\u7a0b", "procedure", "step", "proof")),
    ("example", ("\u4f8b\u5982", "\u4f8b\u5b50", "\u6848\u4f8b", "\u793a\u4f8b", "example", "case")),
    ("comparison", ("\u533a\u522b", "\u5bf9\u6bd4", "\u6bd4\u8f83", "comparison", "versus", "vs")),
    ("definition", ("\u5b9a\u4e49", "\u6982\u5ff5", "\u672c\u8d28", "definition", "concept")),
    ("reference", ("\u6765\u6e90", "\u4f9d\u636e", "\u5b9a\u7406", "\u6587\u732e", "reference", "source", "theorem")),
    ("extension", ("\u5ef6\u4f38", "\u62d3\u5c55", "\u8fdb\u4e00\u6b65", "extension", "advanced")),
    ("prerequisite", ("\u524d\u7f6e", "\u5148\u4fee", "\u57fa\u7840", "prerequisite", "foundation")),
]


def _compact_text(value: Any, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 1, 1)].rstrip()}\u2026"


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
        "\uff1b".join(item["desc"] for item in blockers[:2] if item.get("desc")),
        "\uff1b".join(gaps[:2]),
        str(continuation_prompt or board.continuation.next_prompt_hint or "").strip(),
    ]
    final_query = " | ".join(part for part in parts if part)
    return {
        "turn_mode": normalize_turn_mode(board.current_turn_mode),
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
    turn_mode = normalize_turn_mode((retrieval_focus or {}).get("turn_mode") or board.current_turn_mode)
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
    resolved_mode = normalize_turn_mode(turn_mode or board.current_turn_mode)
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
        "ANCHOR": "\u57fa\u7840\u5b9a\u4e49\u3001\u524d\u7f6e\u77e5\u8bc6\u3001\u5173\u952e\u6982\u5ff5",
        "CORRECTION": "\u53cd\u4f8b\u3001\u7ea0\u9519\u8bc1\u636e\u3001\u6982\u5ff5\u5bf9\u7167",
        "VERIFY": "\u6b65\u9aa4\u6838\u9a8c\u3001\u6765\u6e90\u4f9d\u636e\u3001\u63a8\u7406\u94fe",
        "EXPLORE": "\u5f53\u524d\u8282\u70b9\u6269\u5c55\u8d44\u6599\u3001\u76f8\u5173\u4f8b\u5b50\u3001\u5ef6\u4f38\u7406\u89e3",
        "PAUSED": "\u5f53\u524d\u5b66\u4e60\u8282\u70b9\u80cc\u666f\u8d44\u6599",
    }.get(resolved_mode, "\u5f53\u524d\u5b66\u4e60\u8282\u70b9\u80cc\u666f\u8d44\u6599")
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
    return {key: dedupe_evidence_items(value) for key, value in evidence_map.items()}


def build_retrieval_reason(
    *,
    board: BoardFacts,
    source_readiness: dict[str, Any] | None = None,
) -> str:
    mode = normalize_turn_mode(board.current_turn_mode)
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
