"""Shared utilities used by multiple stages.

Kept tiny on purpose: anything that touches a service should live in the
relevant stage file, not here.
"""

from __future__ import annotations

import asyncio
from typing import Any

from colearn.logging_config import get_logger
from colearn.sessions.store import LearningSession

logger = get_logger(__name__)


def runtime_loop(executor: Any) -> Any:
    """Best-effort accessor for the nanobot ``runtime`` loop hung off the executor.

    Returns ``None`` when the executor cannot expose a bot — callers must be
    tolerant of that.
    """
    get_bot = getattr(executor, "_get_bot", None)
    if not callable(get_bot):
        return None
    try:
        bot = get_bot()
    except (RuntimeError, AttributeError, TypeError) as exc:
        logger.debug("runtime_loop: get_bot failed: %s", exc)
        return None
    return getattr(bot, "_loop", None)


def run_async_or_value(value: Any) -> Any:
    """If ``value`` is a coroutine, drive it to completion via ``asyncio.run``."""
    if asyncio.iscoroutine(value):
        return asyncio.run(value)
    return value


def truncate_for_memory(value: Any, limit: int = 600) -> str:
    text = str(value or "").strip().replace("\n", " ")
    return text[:limit]


def memory_excerpt(store: Any, limit: int = 1200) -> str:
    if store is None or not hasattr(store, "read_memory"):
        return ""
    return str(store.read_memory() or "").strip()[:limit]


def append_session_warning(session: LearningSession, warning: str) -> None:
    last_turn_result = dict(session.last_turn_result or {})
    warnings = list(last_turn_result.get("warnings") or [])
    if warning not in warnings:
        warnings.append(warning)
    last_turn_result["warnings"] = warnings
    session.last_turn_result = last_turn_result


def build_compaction_summary(messages: list[dict[str, Any]], max_chars: int) -> str:
    summary = " | ".join(
        str(item.get("content") or "").strip()
        for item in messages
        if str(item.get("content") or "").strip()
    )
    return summary[:max_chars]


def nanobot_history_entry(
    *,
    project: Any,
    session: LearningSession,
    result: Any,
) -> str:
    blockers = [
        str(getattr(item, "desc", "") or getattr(item, "id", "") or "").strip()
        for item in list(getattr(result.board_after.gaps_and_blockers, "critical_blockers", []) or [])
    ]
    runtime_v2 = dict((result.raw_learning_result or {}).get("runtime_v2") or {})
    retrieval = dict(runtime_v2.get("retrieval") or {})
    return "\n".join(
        [
            f"session_id: {session.session_id}",
            f"project_id: {project.project_id}",
            f"turn_mode: {result.turn_mode_after}",
            f"user: {truncate_for_memory(session.messages[-2].get('content') if len(session.messages) >= 2 else '')}",
            f"assistant: {truncate_for_memory(result.final_text)}",
            f"blockers: {'; '.join(blockers) if blockers else 'none'}",
            f"retrieval: hits={len(retrieval.get('retrieval_hits') or [])}; misses={len(retrieval.get('retrieval_misses') or [])}",
        ]
    )
