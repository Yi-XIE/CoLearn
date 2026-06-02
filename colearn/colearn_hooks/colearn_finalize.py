"""Finalize hook for light CoLearn response cleanup."""
from __future__ import annotations

from colearn.colearn_hooks.colearn_hook_base import AgentHook, AgentHookContext


class CoLearnFinalizeHook(AgentHook):
    """A light hook reserved for final content normalization.

    Learning truth is written through blackboard writeback, not this content hook.
    """

    def finalize_content(self, context: AgentHookContext, content: str | None) -> str | None:
        return content
