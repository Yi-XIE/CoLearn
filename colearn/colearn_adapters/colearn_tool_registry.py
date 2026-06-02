"""Explicit CoLearn tool registration adapter."""
from __future__ import annotations

from typing import Any


class ToolRegistryAdapter:
    """Register CoLearn tools against dict-like or ToolRegistry-like hosts."""

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def register(self, tool: dict[str, Any]) -> None:
        """Register a tool metadata dict explicitly."""
        name = tool.get("command") or tool.get("name")
        if not name:
            raise ValueError("Tool metadata must include 'command' or 'name'")

        register = getattr(self.registry, "register", None)
        if callable(register):
            register(self._coerce_for_host_registry(tool))
            return

        if isinstance(self.registry, dict):
            self.registry[name] = dict(tool)
            return

        try:
            self.registry[name] = tool
        except Exception as exc:
            raise TypeError("Unsupported tool registry shape") from exc

    def unregister(self, name: str) -> None:
        unregister = getattr(self.registry, "unregister", None)
        if callable(unregister):
            unregister(name)
            return
        if isinstance(self.registry, dict):
            self.registry.pop(name, None)

    def get(self, name: str) -> Any:
        getter = getattr(self.registry, "get", None)
        if callable(getter):
            return getter(name)
        if isinstance(self.registry, dict):
            return self.registry.get(name)
        return None

    def get_definitions(self) -> list[dict[str, Any]]:
        get_definitions = getattr(self.registry, "get_definitions", None)
        if callable(get_definitions):
            return list(get_definitions())
        if isinstance(self.registry, dict):
            return [
                {"name": key, **value} if isinstance(value, dict) else {"name": key}
                for key, value in self.registry.items()
            ]
        return []

    def _coerce_for_host_registry(self, tool: dict[str, Any]) -> Any:
        """Wrap CoLearn metadata dict into a NanoBot Tool object when supported."""
        try:
            from colearn.colearn_adapters.colearn_nanobot_tool import (  # noqa: WPS433
                colearn_tool_from_metadata,
            )
        except Exception:
            return tool
        try:
            return colearn_tool_from_metadata(tool)
        except Exception:
            return tool
