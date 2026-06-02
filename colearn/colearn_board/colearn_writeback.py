"""CoLearn blackboard writeback - updates learning state after each turn."""
import time
from typing import Any

from colearn.colearn_state.colearn_models import LearningSession


class BlackboardWriter:
    """Writes learning events back to the blackboard after turn completion."""

    def update_learning_state(
        self, session: LearningSession, turn_result: dict[str, Any]
    ) -> None:
        """
        Update blackboard.learning fields based on turn result.

        This method performs atomic updates to the learning domain of the blackboard
        after a turn completes in LEARNING mode.

        Args:
            session: Current learning session
            turn_result: Dict containing extracted learning events and state updates
                Expected keys:
                - current_progress: str (optional)
                - blockers: list[str] (optional, appends)
                - objections: list[str] (optional, appends)
                - evidence_refs: list[str] (optional, appends)
                - continuation: str (optional)
                - active_node_id: str (optional)
                - completed_nodes: list[str] (optional, appends)
                - pending_checks: list[str] (optional, replaces)
                - goal: str (optional)

        Side effects:
            Mutates session.blackboard.learning in place
            Updates session.updated_at timestamp
        """
        learning = session.blackboard.learning

        # Update scalar fields if provided
        if "current_progress" in turn_result:
            learning.current_progress = turn_result["current_progress"]

        if "continuation" in turn_result:
            learning.continuation = turn_result["continuation"]

        if "active_node_id" in turn_result:
            learning.active_node_id = turn_result["active_node_id"]

        if "goal" in turn_result:
            learning.goal = turn_result["goal"]

        # Append to list fields (deduplication)
        if "blockers" in turn_result:
            for blocker in turn_result["blockers"]:
                if blocker not in learning.blockers:
                    learning.blockers.append(blocker)

        if "objections" in turn_result:
            for objection in turn_result["objections"]:
                if objection not in learning.objections:
                    learning.objections.append(objection)

        if "evidence_refs" in turn_result:
            for ref in turn_result["evidence_refs"]:
                if ref not in learning.evidence_refs:
                    learning.evidence_refs.append(ref)

        if "completed_nodes" in turn_result:
            for node_id in turn_result["completed_nodes"]:
                if node_id not in learning.completed_nodes:
                    learning.completed_nodes.append(node_id)

        # Replace pending_checks (not append, this is a snapshot)
        if "pending_checks" in turn_result:
            learning.pending_checks = turn_result["pending_checks"]

        # Update session timestamp
        session.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
