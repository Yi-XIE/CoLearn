"""Turn result contract carrying learning events and updated board."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .retrieval_bundle import RetrievalBundle, empty_retrieval_bundle
from .state import BoardFacts, LearningEvent


@dataclass(frozen=True)
class LearningTurnResult:
    final_text: str
    next_explanation: str = ""
    next_practice: list[Any] = field(default_factory=list)
    board_before: BoardFacts = field(default_factory=BoardFacts)
    board_after: BoardFacts = field(default_factory=BoardFacts)
    learning_events: list[LearningEvent] = field(default_factory=list)
    continuation_prompt: str = ""
    review_summary: str = ""
    turn_mode_before: str = "EXPLORE"
    turn_mode_after: str = "EXPLORE"
    review_to_persist: dict[str, Any] = field(default_factory=dict)
    board_patch: dict[str, Any] = field(default_factory=dict)
    memory_events: list[dict[str, Any]] = field(default_factory=list)
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    stream_events: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    retrieval_bundle: RetrievalBundle = field(default_factory=lambda: empty_retrieval_bundle())
    raw_learning_result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
