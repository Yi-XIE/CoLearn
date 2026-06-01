"""Tests for LearningBoard.derive — the single source of UI board projection."""

from __future__ import annotations

from colearn.learning.state import (
    Blocker,
    ContinuationFacts,
    GapsAndBlockers,
    LearningBoard,
    ProgressFacts,
)


def _progress() -> ProgressFacts:
    return ProgressFacts(
        active_node_id="node-1",
        active_node_label="Newton's First Law",
        completed_node_ids=["node-0"],
    )


def test_derive_projects_canonical_fields():
    board = LearningBoard.derive(
        current_progress=_progress(),
        gaps_and_blockers=GapsAndBlockers(
            critical_blockers=[Blocker(id="b1", desc="confuses mass and weight")]
        ),
        continuation=ContinuationFacts(next_prompt_hint="ask about inertia"),
        evidence_refs=[{"source_ref": "phys.md"}, {"source_ref": ""}, {"no_ref": 1}],
    )
    assert board.current_progress == "Newton's First Law"
    assert board.completed_nodes == ["node-0"]
    assert board.blockers == ["confuses mass and weight"]
    assert board.continuation == "ask about inertia"
    # Only well-formed source_refs survive the projection.
    assert board.evidence_refs == ["phys.md"]


def test_derive_label_and_continuation_overrides():
    board = LearningBoard.derive(
        current_progress=_progress(),
        gaps_and_blockers=GapsAndBlockers(),
        continuation=ContinuationFacts(next_prompt_hint="canonical hint"),
        evidence_refs=[],
        current_progress_label="Planned First Node",
        continuation_text="Continue with Planned First Node",
    )
    assert board.current_progress == "Planned First Node"
    assert board.continuation == "Continue with Planned First Node"


def test_derive_carries_objections_only_when_supplied():
    base_kwargs = dict(
        current_progress=_progress(),
        gaps_and_blockers=GapsAndBlockers(),
        continuation=ContinuationFacts(),
        evidence_refs=[],
    )
    assert LearningBoard.derive(**base_kwargs).objections == []
    assert LearningBoard.derive(**base_kwargs, objections=["disputes the premise"]).objections == [
        "disputes the premise"
    ]


def test_derive_does_not_alias_input_lists():
    progress = _progress()
    board = LearningBoard.derive(
        current_progress=progress,
        gaps_and_blockers=GapsAndBlockers(),
        continuation=ContinuationFacts(),
        evidence_refs=[],
    )
    # Mutating the projection must not write back into canonical state.
    board.completed_nodes.append("node-2")
    assert progress.completed_node_ids == ["node-0"]
