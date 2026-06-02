"""CoLearn context builder - builds learning context for LLM injection."""
from pathlib import Path

from colearn.colearn_state.colearn_models import LearningSession
from colearn.colearn_wiki.colearn_query import WikiQueryService


class ContextBuilder:
    """Builds learning context from Wiki and blackboard for LLM injection."""

    def __init__(self, wiki_service: WikiQueryService | None = None):
        """
        Initialize context builder.

        Args:
            wiki_service: Optional WikiQueryService instance. If not provided,
                         creates a new instance with default index directory.
        """
        self.wiki_service = wiki_service or WikiQueryService()

    def build_learning_context(self, session: LearningSession) -> str:
        """
        Build formatted learning context string for LLM injection.

        Fetches the current active node from Wiki and formats it with:
        - Prerequisites
        - Misconceptions
        - Examples
        - Learning objectives
        - Current blockers from blackboard

        Args:
            session: Current learning session with blackboard state

        Returns:
            Formatted context string ready for LLM injection.
            Returns empty string if no active node or node not found.
        """
        learning = session.blackboard.learning
        active_node_id = learning.active_node_id

        if not active_node_id:
            return ""

        # Fetch current node from Wiki
        page = self.wiki_service.get_by_id(active_node_id)
        if not page:
            return f"# Active Node: {active_node_id}\n\n[Node not found in Wiki]\n"

        # Build context sections
        sections = []

        # Header
        sections.append(f"# Learning Context: {page.get('title', active_node_id)}")
        sections.append("")

        # Summary
        if page.get("summary"):
            sections.append("## Summary")
            sections.append(page["summary"])
            sections.append("")

        # Learning objectives
        objectives = page.get("learning_objectives", [])
        if objectives:
            sections.append("## Learning Objectives")
            for obj in objectives:
                sections.append(f"- {obj}")
            sections.append("")

        # Prerequisites
        prereqs = page.get("prerequisites", [])
        if prereqs:
            sections.append("## Prerequisites")
            for prereq_id in prereqs:
                prereq_page = self.wiki_service.get_by_id(prereq_id)
                if prereq_page:
                    sections.append(f"- {prereq_page.get('title', prereq_id)} ({prereq_id})")
                else:
                    sections.append(f"- {prereq_id}")
            sections.append("")

        # Common misconceptions
        misconceptions = page.get("misconceptions", [])
        if misconceptions:
            sections.append("## Common Misconceptions")
            for misconception in misconceptions:
                sections.append(f"- {misconception}")
            sections.append("")

        # Examples (from experiment_refs)
        experiment_refs = page.get("experiment_refs", [])
        if experiment_refs:
            sections.append("## Related Activities/Examples")
            for exp_id in experiment_refs:
                exp_page = self.wiki_service.get_by_id(exp_id)
                if exp_page:
                    sections.append(f"- {exp_page.get('title', exp_id)} ({exp_id})")
                else:
                    sections.append(f"- {exp_id}")
            sections.append("")

        # Current blockers from blackboard
        blockers = learning.blockers
        if blockers:
            sections.append("## Current Blockers")
            for blocker in blockers:
                sections.append(f"- {blocker}")
            sections.append("")

        # Current progress
        if learning.current_progress:
            sections.append("## Current Progress")
            sections.append(learning.current_progress)
            sections.append("")

        # Goal
        if learning.goal:
            sections.append("## Learning Goal")
            sections.append(learning.goal)
            sections.append("")

        return "\n".join(sections)
