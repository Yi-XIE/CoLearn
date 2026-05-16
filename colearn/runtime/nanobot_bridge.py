"""Backward-compatible import shim for result normalization."""

from __future__ import annotations

from typing import Any

from colearn.learning.turn_contract import LearningTurnRequest
from colearn.runtime_v2.result_bridge import normalize_learning_turn_result as _normalize


def normalize_learning_turn_result(
    *,
    request: LearningTurnRequest,
    final_text: str,
    learning_result: dict[str, Any] | None = None,
):
    return _normalize(
        request=request,
        final_text=final_text,
        learning_result=learning_result,
    )
