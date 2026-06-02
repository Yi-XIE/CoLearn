"""
NanoBot v0.2.1 host adapter for CoLearn.

This module keeps NanoBot-specific assumptions out of CoLearn core. The primary
path exposes hooks, tools, and UI manifests for explicit host wiring. A private
fallback exists for local experiments with NanoBot v0.2.1, but it is not the
stable host contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from colearn.colearn_adapters.colearn_tool_registry import ToolRegistryAdapter
from colearn.colearn_context import set_current_session_id
from colearn.colearn_plugin import CoLearnPlugin


@dataclass
class NanoBotInstallPlan:
    """Public wiring payload a NanoBot host can install explicitly."""

    hooks: list[Any]
    tools: list[dict[str, Any]]
    ui_extensions: list[dict[str, Any]]


class NanoBotAdapter:
    """Prepare CoLearn plugin surfaces for a NanoBot-like host."""

    def __init__(self, plugin: CoLearnPlugin) -> None:
        self.plugin = plugin

    def build_install_plan(self) -> NanoBotInstallPlan:
        """Return explicit hook/tool/UI surfaces without mutating host internals."""
        return NanoBotInstallPlan(
            hooks=list(self.plugin.get_hooks()),
            tools=list(self.plugin.get_tools()),
            ui_extensions=list(self.plugin.list_ui_extensions()),
        )

    def register_tools(self, registry: Any) -> None:
        """Register CoLearn tools into a public ToolRegistry-like object."""
        adapter = ToolRegistryAdapter(registry)
        for tool in self.plugin.get_tools():
            adapter.register(tool)

    def extract_session_id(self, context: Any) -> str:
        """Extract session id from NanoBot context with stable fallbacks."""
        if isinstance(context, dict):
            return str(
                context.get("session_id")
                or context.get("session_key")
                or context.get("user_id")
                or "default"
            )
        for attr in ("session_id", "session_key", "user_id"):
            value = getattr(context, attr, None)
            if value:
                return str(value)
        return "default"

    def set_session_context(self, context: Any) -> str:
        """Bind extracted session id into CoLearn ContextVar and return it."""
        session_id = self.extract_session_id(context)
        set_current_session_id(session_id)
        return session_id
