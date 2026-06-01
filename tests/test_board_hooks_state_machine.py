"""Tests for board_hooks turn-mode state machine.

Covers three coupled fixes that share board_hooks.py as root cause:
1. Bilingual signal extraction (Chinese turns drive the state machine).
2. Node completion no longer triggered by retrieval (lightrag) calls.
3. Blocker resolution clears blockers so CHECK is not pinned forever.
"""

from __future__ import annotations

from colearn.learning.board_hooks import (
    after_turn,
    extract_learning_events,
)
from colearn.learning.constants import LearningEventType, TurnMode
from colearn.learning.state import (
    Blocker,
    BoardFacts,
    GapsAndBlockers,
    ProgressFacts,
)


def _board(*, turn_mode: TurnMode = TurnMode.LEARN, blockers: list[Blocker] | None = None) -> BoardFacts:
    return BoardFacts(
        project_id="proj-1",
        session_id="sess-1",
        current_turn_mode=turn_mode,
        current_progress=ProgressFacts(
            active_node_id="node-1",
            active_node_label="Newton's First Law",
        ),
        gaps_and_blockers=GapsAndBlockers(critical_blockers=list(blockers or [])),
    )


def _event_types(events) -> set[str]:
    return {str(e.type) for e in events}


# --- Fix 1: bilingual signal extraction ---------------------------------


def test_chinese_blocker_drives_check():
    board = _board(turn_mode=TurnMode.LEARN)
    updated, events = after_turn(
        board=board,
        user_message="我还是不明白特征值这个概念",
        final_text="我们再看一个例子。",
    )
    assert LearningEventType.BLOCKER_FOUND in _event_types(events)
    assert updated.current_turn_mode == TurnMode.CHECK
    assert updated.gaps_and_blockers.critical_blockers


def test_chinese_completion_marks_node_completed():
    board = _board(turn_mode=TurnMode.LEARN)
    updated, events = after_turn(
        board=board,
        user_message="好的",
        final_text="这个节点我们已经完成了，进入下一部分。",
    )
    assert LearningEventType.NODE_COMPLETED in _event_types(events)
    assert "node-1" in updated.current_progress.completed_node_ids


def test_english_blocker_still_works():
    board = _board(turn_mode=TurnMode.LEARN)
    _, events = after_turn(
        board=board,
        user_message="I'm confused about determinants",
        final_text="Let's revisit.",
    )
    assert LearningEventType.BLOCKER_FOUND in _event_types(events)


# --- Fix 2: retrieval (lightrag) must NOT imply completion ---------------


def test_lightrag_call_does_not_complete_node():
    board = _board(turn_mode=TurnMode.LEARN)
    events = extract_learning_events(
        board=board,
        user_message="tell me more",
        final_text="Here is some background on the topic.",
        source_references=[{"source_ref": "notes/newton.md"}],
        tool_events=[{"tool_name": "lightrag"}],
    )
    types = _event_types(events)
    assert LearningEventType.NODE_COMPLETED not in types
    # Retrieval still attaches evidence.
    assert LearningEventType.EVIDENCE_ATTACHED in types


def test_understood_completes_only_in_check_mode():
    # In LEARN mode, a bare "I get it" does NOT close the node (avoids premature
    # completion mid-explanation).
    learn_events = extract_learning_events(
        board=_board(turn_mode=TurnMode.LEARN),
        user_message="ok",
        final_text="现在你应该理解了这个概念。",
    )
    assert LearningEventType.NODE_COMPLETED not in _event_types(learn_events)

    # In CHECK mode, an understood signal means the student passed the check.
    check_events = extract_learning_events(
        board=_board(turn_mode=TurnMode.CHECK),
        user_message="ok",
        final_text="很好，你已经理解了这个概念。",
    )
    assert LearningEventType.NODE_COMPLETED in _event_types(check_events)


# --- Fix 3: blocker resolution unpins CHECK ------------------------------


def test_blocker_resolved_returns_to_learn():
    blocker = Blocker(id="blk_x", desc="特征值")
    board = _board(turn_mode=TurnMode.CHECK, blockers=[blocker])
    updated, events = after_turn(
        board=board,
        user_message="哦，我现在理解了特征值",
        final_text="太好了，那我们继续。",
    )
    assert LearningEventType.BLOCKER_RESOLVED in _event_types(events)
    # The resolved blocker is gone and we are back in LEARN.
    assert not updated.gaps_and_blockers.critical_blockers
    assert updated.current_turn_mode == TurnMode.LEARN


def test_unrelated_understood_keeps_blocker_when_multiple():
    # Two open blockers, an understood signal with no parseable concept overlap:
    # resolve nothing rather than clear the wrong one.
    board = _board(
        turn_mode=TurnMode.CHECK,
        blockers=[Blocker(id="b1", desc="特征值"), Blocker(id="b2", desc="行列式")],
    )
    updated, events = after_turn(
        board=board,
        user_message="我理解了向量加法",
        final_text="好的。",
    )
    assert LearningEventType.BLOCKER_RESOLVED not in _event_types(events)
    assert len(updated.gaps_and_blockers.critical_blockers) == 2
    assert updated.current_turn_mode == TurnMode.CHECK


def test_single_blocker_resolved_without_concept_match():
    # One open blocker + clear understanding signal but no concept overlap:
    # resolve the single blocker (unambiguous).
    board = _board(turn_mode=TurnMode.CHECK, blockers=[Blocker(id="only", desc="特征值")])
    updated, events = after_turn(
        board=board,
        user_message="懂了，明白了",
        final_text="很好。",
    )
    assert LearningEventType.BLOCKER_RESOLVED in _event_types(events)
    assert not updated.gaps_and_blockers.critical_blockers


def test_paused_stays_paused():
    board = _board(turn_mode=TurnMode.PAUSED)
    updated, _ = after_turn(
        board=board,
        user_message="我不明白这个",
        final_text="ok",
    )
    assert updated.current_turn_mode == TurnMode.PAUSED

