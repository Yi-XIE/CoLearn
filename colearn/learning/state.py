"""Three-layer learning state: Board Facts -> Turn Policy -> Learning Events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from colearn.learning.constants import (
    BlockerType,
    CognitiveLoad,
    LearningEventType,
    LearningPhase,
    NodeStatus,
    TurnMode,
)


@dataclass
class ProgressFacts:
    active_node_id: str = ""
    active_node_label: str = ""
    completed_node_ids: list[str] = field(default_factory=list)
    path_node_ids: list[str] = field(default_factory=list)


@dataclass
class StudentSnapshot:
    mastery_level: float = 0.0
    cognitive_load: CognitiveLoad = CognitiveLoad.NORMAL
    last_user_intent_raw: str = ""


@dataclass
class Blocker:
    id: str
    type: BlockerType = BlockerType.CONCEPT_MISUNDERSTANDING
    desc: str = ""


@dataclass
class GapsAndBlockers:
    critical_blockers: list[Blocker] = field(default_factory=list)
    unverified_gaps: list[str] = field(default_factory=list)


@dataclass
class ContinuationFacts:
    next_prompt_hint: str = ""
    last_completed_turn_id: str = ""


@dataclass
class LearningPlanNode:
    id: str = ""
    label: str = ""
    status: NodeStatus = NodeStatus.PENDING
    depth: int = 0
    summary: str = ""


@dataclass
class LearningPlan:
    goal: str = ""
    plan_nodes: list[LearningPlanNode] = field(default_factory=list)
    current_node_id: str = ""
    review_queue: list[str] = field(default_factory=list)
    pending_checks: list[str] = field(default_factory=list)


@dataclass
class LearningBoard:
    """UI-facing projection of board progress.

    Every field except ``objections`` is derived from canonical board state
    (``current_progress`` / ``gaps_and_blockers`` / ``continuation`` /
    ``evidence_refs``). Build it through :meth:`derive` so the projection logic
    lives in exactly one place rather than being re-implemented at each call
    site. ``objections`` is the only field this layer owns directly, so it is
    carried over explicitly.
    """

    current_progress: str = ""
    completed_nodes: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    objections: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    continuation: str = ""

    @staticmethod
    def derive(
        *,
        current_progress: "ProgressFacts",
        gaps_and_blockers: "GapsAndBlockers",
        continuation: "ContinuationFacts",
        evidence_refs: list[dict[str, Any]],
        objections: list[str] | None = None,
        current_progress_label: str | None = None,
        continuation_text: str | None = None,
    ) -> "LearningBoard":
        """Project canonical board facts into the UI board.

        ``current_progress_label`` overrides the displayed node label when the
        caller tracks a different active node than ``current_progress`` (e.g.
        the planner shows the first node while skipping already-mastered ones).
        ``continuation_text`` likewise overrides the continuation hint.
        """
        return LearningBoard(
            current_progress=(
                current_progress_label
                if current_progress_label is not None
                else current_progress.active_node_label
            ),
            completed_nodes=list(current_progress.completed_node_ids),
            blockers=[blocker.desc for blocker in gaps_and_blockers.critical_blockers if blocker.desc],
            objections=list(objections or []),
            evidence_refs=[
                str(item.get("source_ref") or "")
                for item in evidence_refs
                if isinstance(item, dict) and str(item.get("source_ref") or "")
            ],
            continuation=(
                continuation_text
                if continuation_text is not None
                else continuation.next_prompt_hint
            ),
        )



@dataclass
class BoardFacts:
    """Persistent truth about learning progress."""

    project_id: str = ""
    session_id: str = ""
    current_turn_mode: TurnMode = TurnMode.LEARN
    learning_phase: LearningPhase = LearningPhase.READY
    board_version: int = 1
    updated_at: str = ""
    current_progress: ProgressFacts = field(default_factory=ProgressFacts)
    student_snapshot: StudentSnapshot = field(default_factory=StudentSnapshot)
    gaps_and_blockers: GapsAndBlockers = field(default_factory=GapsAndBlockers)
    continuation: ContinuationFacts = field(default_factory=ContinuationFacts)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    learning_plan: LearningPlan = field(default_factory=LearningPlan)
    learning_board: LearningBoard = field(default_factory=LearningBoard)

    def __post_init__(self) -> None:
        if not self.learning_plan.current_node_id and self.current_progress.active_node_id:
            self.learning_plan.current_node_id = self.current_progress.active_node_id
        if not self.learning_plan.goal:
            self.learning_plan.goal = self.current_progress.active_node_label
        if not self.learning_plan.plan_nodes and self.current_progress.active_node_id:
            self.learning_plan.plan_nodes.append(
                LearningPlanNode(
                    id=self.current_progress.active_node_id,
                    label=self.current_progress.active_node_label,
                    status=NodeStatus.CURRENT,
                    depth=0,
                    summary=self.current_progress.active_node_label,
                )
            )
        if not self.learning_board.current_progress:
            self.learning_board.current_progress = self.current_progress.active_node_label
        if not self.learning_board.completed_nodes:
            self.learning_board.completed_nodes = list(self.current_progress.completed_node_ids)
        if not self.learning_board.blockers:
            self.learning_board.blockers = [
                blocker.desc for blocker in self.gaps_and_blockers.critical_blockers if blocker.desc
            ]
        if not self.learning_board.evidence_refs:
            self.learning_board.evidence_refs = [
                str(item.get("source_ref") or "")
                for item in self.evidence_refs
                if isinstance(item, dict) and str(item.get("source_ref") or "")
            ]
        if not self.learning_board.continuation:
            self.learning_board.continuation = self.continuation.next_prompt_hint

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

    turn_mode: TurnMode = TurnMode.LEARN
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
    turn_mode: TurnMode = TurnMode.LEARN
    active_node_id: str = ""
    active_node_label: str = ""
    mastery_level: float = 0.0
    cognitive_load: CognitiveLoad = CognitiveLoad.NORMAL
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
    type: LearningEventType | str
    payload: dict[str, Any] = field(default_factory=dict)
