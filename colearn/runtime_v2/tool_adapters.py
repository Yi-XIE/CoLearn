"""Normalize tool selections for the standalone runtime."""

from __future__ import annotations

from typing import Any


def normalize_enabled_tools(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    tools: list[str] = []
    for item in value:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        tools.append(name)
    return tools
