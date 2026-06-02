"""Hook base compatibility layer.

CoLearn core must be importable without NanoBot installed. When NanoBot is
available, hooks subclass its AgentHook. In tests or standalone tooling, a small
compatible fallback keeps plugin initialization working.
"""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - exercised when NanoBot is installed
    from nanobot.agent.hook import AgentHook, AgentHookContext
except ModuleNotFoundError:  # pragma: no cover - fallback covered indirectly

    class AgentHook:
        """Minimal fallback matching NanoBot AgentHook's constructor surface."""

        def __init__(self, reraise: bool = False) -> None:
            self._reraise = reraise

        async def before_iteration(self, context: Any) -> None:
            return None

        async def after_iteration(self, context: Any) -> None:
            return None

        def finalize_content(self, context: Any, content: str | None) -> str | None:
            return content

    class AgentHookContext:
        """Fallback context marker for type annotations."""

        pass
