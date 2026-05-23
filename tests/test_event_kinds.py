"""Tests for MemoryEventKind constants and TypedDict schemas."""

from __future__ import annotations

from colearn.learning.events import (
    BoardPatchAppliedPayload,
    BoardSnapshotDerivedPayload,
    ConceptSignalPayload,
    MemoryEventKind,
    ReviewWrittenPayload,
    TurnCompletedPayload,
)


def test_all_kind_constants_are_strings():
    for attr in vars(MemoryEventKind):
        if not attr.startswith("_"):
            assert isinstance(getattr(MemoryEventKind, attr), str)


def test_kind_values_are_snake_case():
    for attr in vars(MemoryEventKind):
        if not attr.startswith("_"):
            val = getattr(MemoryEventKind, attr)
            assert val == val.lower().replace(" ", "_"), f"{attr}={val!r} not snake_case"


def test_no_duplicate_kind_values():
    values = [v for k, v in vars(MemoryEventKind).items() if not k.startswith("_")]
    assert len(values) == len(set(values)), "Duplicate kind values found"


def test_board_snapshot_derived_payload_fields():
    payload: BoardSnapshotDerivedPayload = {
        "session_id": "s1",
        "project_id": "p1",
        "board_version": 3,
        "event_count": 10,
        "changes": {"turn_mode": {"old": "EXPLORE", "new": "VERIFY"}},
    }
    assert payload["board_version"] == 3


def test_concept_signal_payload_fields():
    payload: ConceptSignalPayload = {
        "concept": "eigenvalues",
        "source": "extracted_heuristic",
        "raw_match": "I understand eigenvalues now.",
    }
    assert payload["source"] == "extracted_heuristic"


def test_signal_extractor_uses_enum():
    from colearn.learning.signal_extractor import extract_learning_signals
    events = extract_learning_signals("我理解了矩阵乘法。")
    assert events[0]["kind"] == MemoryEventKind.UNDERSTOOD_CONCEPT


def test_turn_hooks_uses_enum():
    """Verify turn_hooks emits events with enum kind values."""
    from colearn.learning.events import MemoryEventKind
    assert MemoryEventKind.TURN_COMPLETED == "turn_completed"
    assert MemoryEventKind.REVIEW_WRITTEN == "review_written"
    assert MemoryEventKind.CONTINUATION_UPDATED == "continuation_updated"
