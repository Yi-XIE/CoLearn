"""Event kind constants and TypedDict payload schemas for MemoryEvent."""

from __future__ import annotations

from typing import Any
from typing import TypedDict


class MemoryEventKind:
    BOARD_PATCH_APPLIED = "board_patch_applied"
    BOARD_SNAPSHOT_DERIVED = "board_snapshot_derived"
    BOARD_SNAPSHOT_FAILED = "board_snapshot_failed"
    PROFILE_CONSOLIDATED = "profile_consolidated"
    PROFILE_CONSOLIDATION_FAILED = "profile_consolidation_failed"
    TURN_COMPLETED = "turn_completed"
    REVIEW_WRITTEN = "review_written"
    CONTINUATION_UPDATED = "continuation_updated"
    UNDERSTOOD_CONCEPT = "understood_concept"
    STILL_BLOCKED = "still_blocked"


class BoardSnapshotDerivedPayload(TypedDict):
    session_id: str
    project_id: str
    board_version: int
    event_count: int
    changes: dict[str, Any]


class BoardPatchAppliedPayload(TypedDict):
    session_id: str
    project_id: str
    patch_keys: list[str]
    board_version: int


class TurnCompletedPayload(TypedDict):
    session_id: str
    project_id: str
    final_text: str
    turn_mode: str
    events: list[str]
    base_board_version: int
    resolved_board_version: int


class ReviewWrittenPayload(TypedDict):
    session_id: str
    project_id: str
    summary: str


class ConceptSignalPayload(TypedDict):
    concept: str
    source: str
    raw_match: str
