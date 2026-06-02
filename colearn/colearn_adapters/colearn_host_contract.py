"""Minimal host contracts CoLearn expects from NanoBot-like runtimes."""
from __future__ import annotations

from typing import Any, Callable, Protocol


class CoLearnTurnRunner(Protocol):
    """Runs one host turn without exposing loop internals to CoLearn core."""

    async def run_turn(
        self,
        *,
        content: str,
        session_key: str,
        channel: str = "cli",
        chat_id: str = "direct",
        media: list[str] | None = None,
        on_progress: Callable[..., Any] | None = None,
        on_stream: Callable[..., Any] | None = None,
        on_stream_end: Callable[..., Any] | None = None,
    ) -> Any: ...


class CoLearnToolRegistry(Protocol):
    """Small tool registry surface needed by CoLearn."""

    def register(self, tool: Any) -> None: ...
    def unregister(self, name: str) -> None: ...
    def get(self, name: str) -> Any: ...
    def get_definitions(self) -> list[dict[str, Any]]: ...


class CoLearnSessionStore(Protocol):
    """Host session mirror store surface."""

    def get_or_create(self, key: str) -> Any: ...
    def save(self, session: Any, *, fsync: bool = False) -> None: ...


class CoLearnUIExtensions(Protocol):
    """UI extension declaration surface for host fixed slots."""

    def list(self, slot: str | None = None) -> list[dict[str, Any]]: ...
    def resolve(self, extension_id: str) -> dict[str, Any] | None: ...
