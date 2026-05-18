"""Compatibility surface for learning state hooks."""

from __future__ import annotations

from colearn.learning.board_hooks import (
    after_turn,
    apply_events,
    build_learning_board,
    build_state_snapshot,
    determine_turn_mode,
    extract_board_facts,
    extract_learning_events,
    resolve_model_preset,
    resolve_turn_mode_after,
)
from colearn.learning.hook_utils import (
    dedupe_evidence_items as _dedupe_evidence_items,
    json_safe as _json_safe,
    normalize_turn_mode as _normalize_turn_mode,
    utc_now as _utc_now,
)
from colearn.learning.retrieval_hooks import (
    MODE_SUPPORT_PRIORITIES,
    SUPPORT_TYPES,
    SUPPORT_TYPE_KEYWORDS,
    build_prompt_support_bundle,
    build_retrieval_evidence_map,
    build_retrieval_focus,
    build_retrieval_query_context,
    build_retrieval_reason,
    infer_support_type,
)
from colearn.learning.turn_hooks import after_turn_payload, before_turn, policy

__all__ = [
    "SUPPORT_TYPES",
    "MODE_SUPPORT_PRIORITIES",
    "SUPPORT_TYPE_KEYWORDS",
    "infer_support_type",
    "build_retrieval_query_context",
    "build_prompt_support_bundle",
    "build_retrieval_focus",
    "build_retrieval_evidence_map",
    "build_retrieval_reason",
    "extract_board_facts",
    "build_learning_board",
    "build_state_snapshot",
    "determine_turn_mode",
    "resolve_model_preset",
    "policy",
    "extract_learning_events",
    "resolve_turn_mode_after",
    "apply_events",
    "after_turn",
    "before_turn",
    "after_turn_payload",
]
