"""Turn runner adapter around NanoBot AgentLoop.process_direct(...)."""
from __future__ import annotations

from typing import Any, Callable


class ProcessDirectTurnRunner:
    """Map CoLearn turn execution to NanoBot's process_direct entrypoint."""

    def __init__(self, loop: Any) -> None:
        self.loop = loop

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
    ) -> Any:
        """Run one turn through the host loop without exposing loop internals."""
        process_direct = getattr(self.loop, "process_direct", None)
        if not callable(process_direct):
            raise AttributeError("Host loop does not expose process_direct(...)")
        return await process_direct(
            content,
            session_key=session_key,
            channel=channel,
            chat_id=chat_id,
            media=media,
            on_progress=on_progress,
            on_stream=on_stream,
            on_stream_end=on_stream_end,
        )
