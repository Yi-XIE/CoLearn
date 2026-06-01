"""Lightweight learning closure assembly for the CoLearn v0.2 runtime line."""

from __future__ import annotations

from typing import Any

from colearn.learning.state_hooks import after_turn_payload
from colearn.learning.turn_contract import LearningTurnRequest
from colearn.projects.models import LearningProject
from colearn.sessions.store import LearningSession


def build_learning_closure(
    *,
    project: LearningProject,
    session: LearningSession,
    request: LearningTurnRequest,
    final_text: str,
    raw_learning_result: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    base_payload = dict(raw_learning_result or {})
    merged_tool_events = list(
        base_payload.get("tool_events")
        or []
    )
    closure_payload = after_turn_payload(
        project=project,
        session=session,
        request=request,
        final_text=final_text,
        tool_events=merged_tool_events,
    )
    return {
        **closure_payload,
        **base_payload,
        "warnings": [
            *list(base_payload.get("warnings") or []),
            *list(warnings or []),
        ],
        "runtime_v2": {
            **dict(base_payload.get("runtime_v2") or {}),
            "closure_applied": True,
        },
    }
