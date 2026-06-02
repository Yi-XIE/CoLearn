"""Stream callback adapter primitives."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class StreamObserver:
    """Collects stream deltas while optionally forwarding them to host callbacks."""

    on_stream: Callable[..., Any] | None = None
    on_stream_end: Callable[..., Any] | None = None
    deltas: list[str] = field(default_factory=list)

    def handle_delta(self, delta: str, *args: Any, **kwargs: Any) -> Any:
        self.deltas.append(delta)
        if self.on_stream:
            return self.on_stream(delta, *args, **kwargs)
        return None

    def handle_end(self, *args: Any, **kwargs: Any) -> Any:
        if self.on_stream_end:
            return self.on_stream_end(*args, **kwargs)
        return None

    @property
    def text(self) -> str:
        return "".join(self.deltas)
