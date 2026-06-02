"""NanoBot Tool wrapper for CoLearn slash commands.

This wraps a CoLearn TOOL_METADATA dict into a real `nanobot.agent.tools.base.Tool`
subclass so it can be registered through `ToolRegistry.register(...)` without the
host having to learn about CoLearn's metadata shape.
"""
from __future__ import annotations

from typing import Any, Callable

try:  # pragma: no cover - exercised only when NanoBot is installed
    from nanobot.agent.tools.base import Tool as _NanoBotTool

    class CoLearnTool(_NanoBotTool):
        """Adapter that exposes CoLearn handlers through NanoBot's Tool ABC."""

        def __init__(
            self,
            *,
            name: str,
            description: str,
            handler: Callable[..., Any],
            parameters: dict[str, Any] | None = None,
        ) -> None:
            self._name = name
            self._description = description
            self._handler = handler
            self._parameters = parameters or {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            }

        @property
        def name(self) -> str:
            return self._name

        @property
        def description(self) -> str:
            return self._description

        @property
        def parameters(self) -> dict[str, Any]:
            return self._parameters

        async def execute(self, **kwargs: Any) -> Any:
            result = self._handler(**kwargs) if kwargs else self._handler()
            if hasattr(result, "__await__"):
                return await result
            return result

    def colearn_tool_from_metadata(metadata: dict[str, Any]) -> CoLearnTool:
        """Build a CoLearnTool from a CoLearn tool metadata dict."""
        name = metadata.get("name") or metadata.get("command", "").lstrip("/")
        return CoLearnTool(
            name=name,
            description=metadata.get("description", ""),
            handler=metadata["handler"],
            parameters=metadata.get("parameters"),
        )

    class ColearnDashboardTool(_NanoBotTool):
        """Zero-arg, entry-point-discoverable `/colearn` dashboard tool.

        NanoBot's ToolLoader discovers `Tool` subclasses via the ``nanobot.tools``
        entry point and instantiates them with no arguments. This concrete class
        is that discoverable surface; it delegates to the CoLearn command handler.
        """

        config_key = "colearn"

        @property
        def name(self) -> str:
            return "colearn"

        @property
        def description(self) -> str:
            from colearn.colearn_tools.colearn_command import TOOL_METADATA

            return TOOL_METADATA["description"]

        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {}, "additionalProperties": False}

        async def execute(self, **kwargs: Any) -> Any:
            from colearn.colearn_tools.colearn_command import colearn_command

            return colearn_command()

except ModuleNotFoundError:  # pragma: no cover - covered indirectly
    CoLearnTool = None  # type: ignore[assignment]
    ColearnDashboardTool = None  # type: ignore[assignment]

    def colearn_tool_from_metadata(metadata: dict[str, Any]) -> Any:
        raise RuntimeError(
            "NanoBot is not installed; CoLearnTool wrapper requires nanobot.agent.tools.base"
        )
