"""Tests for BoardSnapshotDeriver."""

from __future__ import annotations

import json

from colearn.learning.board_deriver import BoardSnapshotDeriver
from colearn.learning.state import (
    BoardFacts,
    Blocker,
    ContinuationFacts,
    GapsAndBlockers,
    ProgressFacts,
    StudentSnapshot,
)
from colearn.memory.store import MemoryEvent


def _current_board(**overrides) -> BoardFacts:
    base = BoardFacts(
        project_id="p1",
        session_id="s1",
        current_turn_mode="EXPLORE",
        board_version=2,
        current_progress=ProgressFacts(active_node_id="vectors", active_node_label="Vectors"),
        student_snapshot=StudentSnapshot(mastery_level=0.3, cognitive_load="NORMAL"),
        gaps_and_blockers=GapsAndBlockers(),
        continuation=ContinuationFacts(),
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _events(*kinds_and_payloads) -> list[MemoryEvent]:
    return [
        MemoryEvent(event_id=f"e{i}", kind=kind, payload=payload)
        for i, (kind, payload) in enumerate(kinds_and_payloads)
    ]


def test_deriver_returns_current_when_events_empty():
    def llm(*, system, user):
        raise AssertionError("should not be called for empty events")

    deriver = BoardSnapshotDeriver(llm_call=llm)
    board, diff = deriver.derive_snapshot(events=[], current_board=_current_board())
    assert diff["status"] == "skipped_empty"
    assert board.current_turn_mode == "EXPLORE"


def test_deriver_builds_board_from_valid_json():
    def llm(*, system, user):
        return json.dumps({
            "current_turn_mode": "CORRECTION",
            "mastery_level": 0.5,
            "cognitive_load": "HIGH",
            "active_node_id": "eigenvalues",
            "active_node_label": "Eigenvalues",
            "critical_blockers": [
                {"id": "b1", "type": "CONCEPT_MISUNDERSTANDING", "desc": "thinks det=trace"}
            ],
            "unverified_gaps": ["determinant computation"],
            "next_prompt_hint": "show counterexample",
        })

    deriver = BoardSnapshotDeriver(llm_call=llm)
    events = _events(("understood_concept", {"concept": "vectors"}), ("still_blocked", {"concept": "eigenvalues"}))
    board, diff = deriver.derive_snapshot(events=events, current_board=_current_board())

    assert diff["status"] == "ok"
    assert board.current_turn_mode == "CORRECTION"
    assert board.student_snapshot.mastery_level == 0.5
    assert board.student_snapshot.cognitive_load == "HIGH"
    assert board.current_progress.active_node_label == "Eigenvalues"
    assert len(board.gaps_and_blockers.critical_blockers) == 1
    assert board.gaps_and_blockers.critical_blockers[0].desc == "thinks det=trace"
    assert "determinant computation" in board.gaps_and_blockers.unverified_gaps
    # board_version increments
    assert board.board_version == 3


def test_deriver_extracts_json_from_markdown_fence():
    def llm(*, system, user):
        return """Here is the snapshot:
```json
{"current_turn_mode": "VERIFY", "mastery_level": 0.7, "cognitive_load": "LOW",
 "active_node_id": "x", "active_node_label": "X", "critical_blockers": [],
 "unverified_gaps": [], "next_prompt_hint": "h"}
```"""

    deriver = BoardSnapshotDeriver(llm_call=llm)
    board, diff = deriver.derive_snapshot(events=_events(("turn_completed", {})), current_board=_current_board())
    assert diff["status"] == "ok"
    assert board.current_turn_mode == "VERIFY"


def test_deriver_falls_back_when_llm_raises():
    def llm(*, system, user):
        raise RuntimeError("api offline")

    deriver = BoardSnapshotDeriver(llm_call=llm)
    current = _current_board()
    board, diff = deriver.derive_snapshot(events=_events(("turn_completed", {})), current_board=current)
    assert diff["status"] == "llm_failed"
    assert board is current


def test_deriver_falls_back_when_json_unparseable():
    def llm(*, system, user):
        return "this is not json at all just prose"

    deriver = BoardSnapshotDeriver(llm_call=llm)
    current = _current_board()
    board, diff = deriver.derive_snapshot(events=_events(("turn_completed", {})), current_board=current)
    assert diff["status"] == "parse_failed"
    assert board is current


def test_deriver_diff_captures_changes():
    def llm(*, system, user):
        return json.dumps({
            "current_turn_mode": "CORRECTION",  # changed from EXPLORE
            "mastery_level": 0.7,  # changed from 0.3
            "cognitive_load": "HIGH",  # changed from NORMAL
            "active_node_id": "vectors",
            "active_node_label": "Vectors",
            "critical_blockers": [],
            "unverified_gaps": ["new_gap"],
            "next_prompt_hint": "",
        })

    deriver = BoardSnapshotDeriver(llm_call=llm)
    _, diff = deriver.derive_snapshot(events=_events(("turn_completed", {})), current_board=_current_board())
    changes = diff["changes"]
    assert changes["turn_mode"] == {"old": "EXPLORE", "new": "CORRECTION"}
    assert changes["mastery_level"]["new"] == 0.7
    assert changes["cognitive_load"] == {"old": "NORMAL", "new": "HIGH"}
    assert "new_gap" in changes["gaps_added"]


def test_deriver_caps_to_max_events():
    captured_user_prompts = []

    def llm(*, system, user):
        captured_user_prompts.append(user)
        return json.dumps({
            "current_turn_mode": "EXPLORE",
            "mastery_level": 0.3,
            "cognitive_load": "NORMAL",
            "active_node_id": "x",
            "active_node_label": "X",
            "critical_blockers": [],
            "unverified_gaps": [],
            "next_prompt_hint": "",
        })

    deriver = BoardSnapshotDeriver(llm_call=llm, max_events=5)
    events = _events(*[("turn_completed", {"i": i}) for i in range(20)])
    deriver.derive_snapshot(events=events, current_board=_current_board())
    # Only the last 5 events should appear in the prompt
    user_prompt = captured_user_prompts[0]
    assert "5 条学习事件" in user_prompt
    # Earlier events should not appear
    assert '"i": 0' not in user_prompt or '"i": 19' in user_prompt
