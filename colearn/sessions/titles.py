"""Helpers for deriving default session titles from user input."""

from __future__ import annotations

from typing import Any, Iterable

DEFAULT_SESSION_TITLE_MAX_LENGTH = 60


def first_user_message(messages: Iterable[dict[str, Any]]) -> str:
    for item in messages:
        if str(item.get("role") or "") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if content:
            return content
    return ""


def derive_session_title(
    text: str,
    *,
    max_length: int = DEFAULT_SESSION_TITLE_MAX_LENGTH,
) -> str:
    one_line = " ".join(str(text or "").split()).strip()
    if not one_line:
        return ""
    if len(one_line) <= max_length:
        return one_line
    if max_length <= 3:
        return "." * max_length
    return f"{one_line[: max_length - 3].rstrip()}..."

