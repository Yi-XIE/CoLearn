"""Derive BoardFacts snapshots from the event stream via LLM.

Replaces the brittle "harness manually patches BoardFacts after each turn"
flow with an event-sourcing approach: events are append-only facts, and the
LLM periodically re-derives a fresh BoardFacts snapshot from them. Errors in
turn-level board_patch are auto-corrected on the next consolidation cycle.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, Callable, Protocol
from uuid import uuid4

from colearn.learning.prompts.board_consolidation import (
    BOARD_CONSOLIDATION_SYSTEM,
    build_consolidation_user_prompt,
)
from colearn.learning.state import (
    BoardFacts,
    Blocker,
    ContinuationFacts,
    GapsAndBlockers,
    ProgressFacts,
    StudentSnapshot,
)
from colearn.logging_config import get_logger
from colearn.memory.store import MemoryEvent

logger = get_logger(__name__)


class _LLMCallable(Protocol):
    def __call__(self, *, system: str, user: str) -> str: ...


class BoardSnapshotDeriver:
    """Calls an LLM to re-derive BoardFacts from an event stream.

    Independent of nanobot turn execution — uses an injected callable so callers
    can wire any LLM (a cheap haiku for cost; the main bot for parity).
    """

    def __init__(
        self,
        *,
        llm_call: _LLMCallable,
        max_events: int = 30,
    ) -> None:
        self._llm_call = llm_call
        self._max_events = max_events

    def derive_snapshot(
        self,
        *,
        events: list[MemoryEvent],
        current_board: BoardFacts,
        project_summary: str = "",
    ) -> tuple[BoardFacts, dict[str, Any]]:
        """Returns (new_board, diff_payload). diff_payload describes changes
        for the audit event; falls back to current_board if LLM/parse fails."""
        if not events:
            return current_board, {"changes": {}, "event_count": 0, "status": "skipped_empty"}

        recent = events[-self._max_events :]
        prompt_user = build_consolidation_user_prompt(
            project_summary=project_summary or current_board.project_id,
            current_board=current_board.to_dict() if hasattr(current_board, "to_dict") else _board_to_dict(current_board),
            events=recent,
        )

        try:
            llm_output = self._llm_call(system=BOARD_CONSOLIDATION_SYSTEM, user=prompt_user)
        except Exception as exc:
            logger.warning("BoardSnapshotDeriver LLM call failed: %s", exc)
            return current_board, {"changes": {}, "event_count": len(recent), "status": "llm_failed", "error": str(exc)}

        parsed = _extract_json(llm_output)
        if parsed is None:
            logger.warning("BoardSnapshotDeriver could not parse LLM output as JSON")
            return current_board, {"changes": {}, "event_count": len(recent), "status": "parse_failed"}

        try:
            new_board = _build_board_from_snapshot(parsed, fallback=current_board)
        except Exception as exc:
            logger.warning("BoardSnapshotDeriver could not build BoardFacts: %s", exc)
            return current_board, {"changes": {}, "event_count": len(recent), "status": "build_failed", "error": str(exc)}

        diff = _diff_boards(current_board, new_board)
        return new_board, {
            "changes": diff,
            "event_count": len(recent),
            "status": "ok",
        }


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    # Try direct parse first.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Extract first {...} block (handles markdown fences or extra prose).
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _build_board_from_snapshot(snapshot: dict[str, Any], *, fallback: BoardFacts) -> BoardFacts:
    """Build a BoardFacts from LLM-emitted JSON, filling missing fields from fallback."""
    blockers_raw = snapshot.get("critical_blockers") or []
    blockers: list[Blocker] = []
    for item in blockers_raw[:3]:
        if not isinstance(item, dict):
            continue
        blockers.append(
            Blocker(
                id=str(item.get("id") or f"b_{uuid4().hex[:6]}"),
                type=str(item.get("type") or "CONCEPT_MISUNDERSTANDING"),
                desc=str(item.get("desc") or "").strip(),
            )
        )

    gaps = [str(g).strip() for g in (snapshot.get("unverified_gaps") or []) if str(g).strip()]

    return BoardFacts(
        project_id=fallback.project_id,
        session_id=fallback.session_id,
        current_turn_mode=str(snapshot.get("current_turn_mode") or fallback.current_turn_mode),
        board_version=int(fallback.board_version or 1) + 1,
        updated_at=fallback.updated_at,
        current_progress=ProgressFacts(
            active_node_id=str(snapshot.get("active_node_id") or fallback.current_progress.active_node_id),
            active_node_label=str(snapshot.get("active_node_label") or fallback.current_progress.active_node_label),
            completed_node_ids=list(fallback.current_progress.completed_node_ids),
            path_node_ids=list(fallback.current_progress.path_node_ids),
        ),
        student_snapshot=StudentSnapshot(
            mastery_level=float(snapshot.get("mastery_level", fallback.student_snapshot.mastery_level)),
            cognitive_load=str(snapshot.get("cognitive_load") or fallback.student_snapshot.cognitive_load),
            last_user_intent_raw=fallback.student_snapshot.last_user_intent_raw,
        ),
        gaps_and_blockers=GapsAndBlockers(critical_blockers=blockers, unverified_gaps=gaps),
        continuation=ContinuationFacts(
            next_prompt_hint=str(snapshot.get("next_prompt_hint") or fallback.continuation.next_prompt_hint),
            last_completed_turn_id=fallback.continuation.last_completed_turn_id,
        ),
        evidence_refs=list(fallback.evidence_refs or []),
    )


def _diff_boards(old: BoardFacts, new: BoardFacts) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if old.current_turn_mode != new.current_turn_mode:
        changes["turn_mode"] = {"old": old.current_turn_mode, "new": new.current_turn_mode}
    if abs(old.student_snapshot.mastery_level - new.student_snapshot.mastery_level) > 0.05:
        changes["mastery_level"] = {
            "old": round(old.student_snapshot.mastery_level, 2),
            "new": round(new.student_snapshot.mastery_level, 2),
        }
    if old.student_snapshot.cognitive_load != new.student_snapshot.cognitive_load:
        changes["cognitive_load"] = {
            "old": old.student_snapshot.cognitive_load,
            "new": new.student_snapshot.cognitive_load,
        }
    old_blocker_ids = {b.id for b in (old.gaps_and_blockers.critical_blockers or [])}
    new_blocker_ids = {b.id for b in (new.gaps_and_blockers.critical_blockers or [])}
    if old_blocker_ids != new_blocker_ids:
        changes["blockers_removed"] = sorted(old_blocker_ids - new_blocker_ids)
        changes["blockers_added"] = sorted(new_blocker_ids - old_blocker_ids)
    old_gaps = set(old.gaps_and_blockers.unverified_gaps or [])
    new_gaps = set(new.gaps_and_blockers.unverified_gaps or [])
    if old_gaps != new_gaps:
        changes["gaps_added"] = sorted(new_gaps - old_gaps)
        changes["gaps_removed"] = sorted(old_gaps - new_gaps)
    if old.current_progress.active_node_id != new.current_progress.active_node_id:
        changes["active_node_id"] = {
            "old": old.current_progress.active_node_id,
            "new": new.current_progress.active_node_id,
        }
    return changes


def _board_to_dict(board: BoardFacts) -> dict[str, Any]:
    return asdict(board)
