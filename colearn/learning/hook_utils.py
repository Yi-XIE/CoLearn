"""Shared utilities for learning state hooks."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any, cast

from colearn.learning.state import TurnMode


def normalize_turn_mode(raw: str | None) -> TurnMode:
    value = str(raw or "EXPLORE").upper()
    if value in {"ANCHOR", "CORRECTION", "VERIFY", "EXPLORE", "PAUSED"}:
        return cast(TurnMode, value)
    return "EXPLORE"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


def dedupe_evidence_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def evidence_sort_key(item: dict[str, Any]) -> tuple[str, str, str, str, str]:
        return (
            str(item.get("source_ref") or item.get("source_path") or ""),
            str(item.get("chunk_id") or ""),
            str(item.get("support_type") or ""),
            str(item.get("target_type") or ""),
            str(item.get("target_id") or ""),
        )

    seen: set[tuple[str, str, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in sorted(items, key=evidence_sort_key):
        signature = (
            str(item.get("source_ref") or item.get("source_path") or ""),
            str(item.get("chunk_id") or ""),
            str(item.get("support_type") or ""),
            str(item.get("target_type") or ""),
            str(item.get("target_id") or ""),
        )
        if signature in seen:
            continue
        seen.add(signature)
        result.append(item)
    return result
