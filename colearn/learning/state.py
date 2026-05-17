"""Three-layer learning state: Board Facts -> Turn Policy -> Learning Events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class ProgressFacts:
    active_node_id: str = ""
    active_node_label: str = ""
    completed_node_ids: list[str] = field(default_factory=list)
    path_node_ids: list[str] = field(default_factory=list)


@dataclass
class StudentSnapshot:
    mastery_level: float = 0.0
    cognitive_load: str = "NORMAL"
    last_user_intent_raw: str = ""


@dataclass
class Blocker:
    id: str
    type: str = "CONCEPT_MISUNDERSTANDING"
    desc: str = ""


@dataclass
class GapsAndBlockers:
    critical_blockers: list[Blocker] = field(default_factory=list)
    unverified_gaps: list[str] = field(default_factory=list)


@dataclass
class ContinuationFacts:
    next_prompt_hint: str = ""
    last_completed_turn_id: str = ""


TurnMode = Literal["ANCHOR", "CORRECTION", "VERIFY", "EXPLORE", "PAUSED"]


@dataclass
class BoardFacts:
    """Persistent truth about learning progress."""

    project_id: str = ""
    session_id: str = ""
    current_turn_mode: TurnMode = "EXPLORE"
    board_version: int = 1
    updated_at: str = ""
    current_progress: ProgressFacts = field(default_factory=ProgressFacts)
    student_snapshot: StudentSnapshot = field(default_factory=StudentSnapshot)
    gaps_and_blockers: GapsAndBlockers = field(default_factory=GapsAndBlockers)
    continuation: ContinuationFacts = field(default_factory=ContinuationFacts)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplyContract:
    style: str = ""
    must_include: list[str] = field(default_factory=list)
    must_avoid: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TurnPolicy:
    """Per-turn projection computed fresh each round."""

    turn_mode: TurnMode = "EXPLORE"
    model_preset: str | None = None
    main_goal: str = ""
    restrictions: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    enabled_tools: list[str] = field(default_factory=list)
    review_focus: list[str] = field(default_factory=list)
    reply_contract: ReplyContract = field(default_factory=ReplyContract)
    warnings: list[str] = field(default_factory=list)
    continuation_prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LearningStateSnapshot:
    turn_mode: TurnMode = "EXPLORE"
    active_node_id: str = ""
    active_node_label: str = ""
    mastery_level: float = 0.0
    cognitive_load: str = "NORMAL"
    blockers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PolicyDecision:
    main_goal: str = ""
    review_focus: list[str] = field(default_factory=list)
    enabled_tools: list[str] = field(default_factory=list)
    continuation_prompt: str = ""
    restrictions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LearningEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
