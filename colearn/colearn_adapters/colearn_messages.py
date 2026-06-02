"""Message adapter helpers for NanoBot hook contexts and sessions."""
from __future__ import annotations

from typing import Any


def read_messages(source: Any) -> list[Any]:
    """Read messages from a hook context, host session, or dict-like source."""
    if isinstance(source, dict):
        return list(source.get("messages", []))
    return list(getattr(source, "messages", []) or [])


def append_system_context(source: Any, payload: str) -> None:
    """Append a system context message to a compatible message container.

    This intentionally uses a plain dict shape so the host adapter remains thin;
    host-specific conversion can be added here without touching learning logic.
    """
    if not payload:
        return
    messages = read_messages(source)
    messages.append({"role": "system", "content": payload, "source": "colearn"})
    if isinstance(source, dict):
        source["messages"] = messages
    else:
        setattr(source, "messages", messages)
