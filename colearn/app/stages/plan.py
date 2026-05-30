"""PlanStage - builds the minimal LearningPlan for Learning Mode."""

from __future__ import annotations

from dataclasses import asdict, replace
import re
from typing import Any

from colearn.learning.constants import LearningPhase, NodeStatus
from colearn.learning.state import (
    LearningBoard,
    LearningPlan,
    LearningPlanNode,
    ProgressFacts,
)

from .context import TurnContext


_REPLAN_MARKERS = (
    "change topic",
    "switch topic",
    "start over",
    "instead learn",
    "重新学",
    "换个主题",
    "改学",
)


class PlanStage:
    """Generate a small, stable plan only when the board needs one.

    When a retrieval service is available, queries LightRAG for course
    structure to produce a more intelligent plan. Falls back to the
    4-step template when retrieval is unavailable.
    """

    def __init__(self, *, retrieval_service: Any = None) -> None:
        self._retrieval_service = retrieval_service

    def run(self, ctx: TurnContext) -> TurnContext:
        if ctx.session_mode != "learning" or ctx.board is None or ctx.project is None:
            ctx.plan_stage = {"status": "skipped", "reason": "session_mode:chat"}
            return ctx
        if not self._should_plan(ctx):
            ctx.plan_stage = {"status": "skipped", "reason": "plan_exists"}
            return ctx

        plan = self._build_intelligent_plan(ctx) or self._build_plan(ctx)
        first_node = plan.plan_nodes[0] if plan.plan_nodes else LearningPlanNode()
        learning_board = LearningBoard(
            current_progress=first_node.label,
            completed_nodes=list(ctx.board.current_progress.completed_node_ids),
            blockers=[blocker.desc for blocker in ctx.board.gaps_and_blockers.critical_blockers if blocker.desc],
            objections=list(ctx.board.learning_board.objections or []),
            evidence_refs=[
                str(item.get("source_ref") or "")
                for item in list(ctx.board.evidence_refs or [])
                if isinstance(item, dict) and str(item.get("source_ref") or "")
            ],
            continuation=f"Continue with {first_node.label}" if first_node.label else ctx.board.continuation.next_prompt_hint,
        )
        mastery = ctx.board.student_snapshot.mastery_level
        nodes_to_skip = self._skip_mastered_nodes(plan.plan_nodes, mastery)
        active_node = first_node
        for node in plan.plan_nodes:
            if node.id not in nodes_to_skip:
                active_node = node
                break
        ctx.board = replace(
            ctx.board,
            current_turn_mode="LEARN",
            learning_phase=LearningPhase.READY,
            current_progress=ProgressFacts(
                active_node_id=active_node.id,
                active_node_label=active_node.label,
                completed_node_ids=list(ctx.board.current_progress.completed_node_ids) + list(nodes_to_skip),
                path_node_ids=[node.id for node in plan.plan_nodes if node.id],
            ),
            learning_plan=plan,
            learning_board=learning_board,
        )
        if ctx.snapshot is not None:
            ctx.snapshot = replace(
                ctx.snapshot,
                active_node_id=active_node.id,
                active_node_label=active_node.label,
            )
        ctx.project.goal = plan.goal
        ctx.plan_patch = asdict(plan)
        ctx.plan_stage = {
            "status": "planned",
            "reason": "missing_or_replan_requested",
            "node_count": len(plan.plan_nodes),
            "skipped_nodes": len(nodes_to_skip),
        }
        return ctx

    def _should_plan(self, ctx: TurnContext) -> bool:
        board = ctx.board
        plan = board.learning_plan
        nodes = list(plan.plan_nodes or [])
        user_message = str(ctx.user_message or "").lower()
        if any(marker in user_message for marker in _REPLAN_MARKERS):
            return True
        if not nodes:
            return True
        if len(nodes) == 1 and nodes[0].id == board.project_id:
            return True
        return not str(plan.current_node_id or "").strip()

    def _build_intelligent_plan(self, ctx: TurnContext) -> LearningPlan | None:
        """Try to build a plan using LightRAG course structure."""
        if self._retrieval_service is None:
            return None
        client = getattr(self._retrieval_service, "_lightrag_client", None) or getattr(
            self._retrieval_service, "lightrag_client", None
        )
        if client is None or not getattr(client, "enabled", False):
            return None
        goal = self._goal_text(ctx)
        try:
            result = client.retrieve_project_context(
                project_id=ctx.project.project_id if ctx.project else "",
                query=f"course structure outline for: {goal}",
                mode="hybrid",
                top_k=8,
            )
            if not result or getattr(result, "retrieval_status", "") != "success":
                return None
            chunks = getattr(result, "chunks", []) or []
            if not chunks:
                return None
            return self._plan_from_chunks(goal, chunks, ctx)
        except (RuntimeError, ValueError, OSError, ConnectionError, AttributeError):
            return None

    def _plan_from_chunks(self, goal: str, chunks: list, ctx: TurnContext) -> LearningPlan | None:
        """Extract plan nodes from retrieval chunks."""
        base_id = self._slug(goal) or str(ctx.project.project_id or "learning")
        nodes: list[LearningPlanNode] = []
        seen_labels: set[str] = set()
        for i, chunk in enumerate(chunks[:8]):
            label = ""
            if isinstance(chunk, dict):
                label = str(chunk.get("title") or chunk.get("label") or chunk.get("content", "")[:60]).strip()
            elif hasattr(chunk, "title"):
                label = str(getattr(chunk, "title", "") or "").strip()
            if not label or label in seen_labels:
                continue
            seen_labels.add(label)
            nodes.append(LearningPlanNode(
                id=f"{base_id}-{len(nodes) + 1}",
                label=f"{goal}: {label}" if len(label) < 40 else label,
                status=NodeStatus.CURRENT if len(nodes) == 0 else NodeStatus.PENDING,
                depth=len(nodes),
                summary=label,
            ))
        if len(nodes) < 2:
            return None
        return LearningPlan(
            goal=goal,
            plan_nodes=nodes,
            current_node_id=nodes[0].id,
            review_queue=[nodes[1].id] if len(nodes) > 1 else [],
            pending_checks=[nodes[-1].id],
        )

    def _skip_mastered_nodes(self, nodes: list[LearningPlanNode], mastery: float) -> set[str]:
        """Skip early nodes if mastery is high enough."""
        if mastery < 0.5 or len(nodes) <= 2:
            return set()
        skip_count = min(len(nodes) - 2, int(mastery * len(nodes) * 0.3))
        return {nodes[i].id for i in range(skip_count)}

    def _build_plan(self, ctx: TurnContext) -> LearningPlan:
        goal = self._goal_text(ctx)
        base_id = self._slug(goal) or str(ctx.project.project_id or "learning")
        labels = [
            f"{goal}: orientation",
            f"{goal}: core concepts",
            f"{goal}: worked example",
            f"{goal}: check understanding",
        ]
        nodes = [
            LearningPlanNode(
                id=f"{base_id}-{idx + 1}",
                label=label,
                status=NodeStatus.CURRENT if idx == 0 else (NodeStatus.PENDING),
                depth=idx,
                summary=label,
            )
            for idx, label in enumerate(labels)
        ]
        return LearningPlan(
            goal=goal,
            plan_nodes=nodes,
            current_node_id=nodes[0].id,
            review_queue=[nodes[1].id],
            pending_checks=[nodes[-1].id],
        )

    def _goal_text(self, ctx: TurnContext) -> str:
        message = re.sub(r"\s+", " ", str(ctx.user_message or "").strip())
        lowered = message.lower()
        if any(marker in lowered for marker in _REPLAN_MARKERS):
            for marker in _REPLAN_MARKERS:
                idx = lowered.find(marker)
                if idx >= 0:
                    message = message[idx + len(marker) :].strip(" :.,")
                    break
            if message:
                return message[:120]
        project = ctx.project
        project_goal = str((project.goal if project else "") or "").strip()
        if project_goal:
            return project_goal[:120]
        project_title = str((project.title if project else "") or "").strip()
        project_id = str((project.project_id if project else "") or "").strip()
        if project_title and project_title not in {project_id, "default-project", "CoLearn"}:
            return project_title[:120]
        for prefix in ("i want to learn", "learn", "study"):
            if message.lower().startswith(prefix):
                message = message[len(prefix) :].strip(" :.,")
                break
        return (message or str(ctx.project.title or "Learning goal"))[:120]

    def _slug(self, text: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
        return value[:48]
