"""Turn request contract carrying board facts and turn policy for one round."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .retrieval_bundle import RetrievalBundle, empty_retrieval_bundle
from .state import BoardFacts, LearningStateSnapshot, PolicyDecision, TurnPolicy


@dataclass(frozen=True)
class LearningTurnRequest:
    session_id: str
    turn_id: str = ""
    user_message: str = ""
    language: str = "zh"
    project_id: str = ""
    project_title: str = ""
    turn_mode: str = "EXPLORE"
    model_preset: str | None = None
    board_facts: BoardFacts = field(default_factory=BoardFacts)
    turn_policy: TurnPolicy | None = None
    state_projection: LearningStateSnapshot = field(default_factory=LearningStateSnapshot)
    policy_decision: PolicyDecision | None = None
    continuation_prompt: str = ""
    anchor: dict[str, Any] = field(default_factory=dict)
    source_references: list[dict[str, Any]] = field(default_factory=list)
    memory_references: list[str] = field(default_factory=list)
    enabled_tools: list[str] = field(default_factory=list)
    retrieval_bundle: RetrievalBundle = field(default_factory=lambda: empty_retrieval_bundle())
    attachments: list[dict[str, Any]] = field(default_factory=list)
    requested_skills: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
