"""Shared SSE streaming utilities."""

from __future__ import annotations

import json
from typing import Any, Generator


def sse_stream(events: list[dict[str, Any]], *, event_name: str | None = None) -> Generator[str, None, None]:
    for item in events:
        payload = json.dumps(item, ensure_ascii=False)
        if event_name:
            yield f"event: {event_name}\ndata: {payload}\n\n"
        else:
            yield f"data: {payload}\n\n"
