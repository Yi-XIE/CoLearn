"""Tests for turn_mode-driven retrieval query strategy and gap re-rank."""

from __future__ import annotations

from colearn.learning.retrieval_hooks import (
    MODE_QUERY_STRATEGY,
    build_prompt_support_bundle,
    build_retrieval_query_context,
)
from colearn.learning.state import (
    BoardFacts,
    Blocker,
    GapsAndBlockers,
    ProgressFacts,
    StudentSnapshot,
)


def _board(
    *,
    turn_mode="EXPLORE",
    blockers=None,
    gaps=None,
    active_node="linear_algebra",
    cognitive_load="NORMAL",
):
    return BoardFacts(
        project_id="p1",
        session_id="s1",
        current_turn_mode=turn_mode,
        current_progress=ProgressFacts(active_node_id=active_node, active_node_label=active_node.replace("_", " ")),
        student_snapshot=StudentSnapshot(cognitive_load=cognitive_load, mastery_level=0.5),
        gaps_and_blockers=GapsAndBlockers(
            critical_blockers=[Blocker(id=b["id"], desc=b["desc"], type="CONCEPT_MISUNDERSTANDING") for b in (blockers or [])],
            unverified_gaps=list(gaps or []),
        ),
    )


# --- K1 query strategy ---

def test_explore_mode_favors_user_message():
    board = _board(turn_mode="EXPLORE")
    ctx = build_retrieval_query_context(
        board=board,
        user_message="How does eigendecomposition work?",
        retrieval_focus={"default_query": "default fallback"},
    )
    assert ctx["query_intent"] == "expand_concept"
    # user_message should appear before default_query in priority_terms
    user_idx = ctx["priority_terms"].index("How does eigendecomposition work?")
    default_idx = ctx["priority_terms"].index("default fallback")
    assert user_idx < default_idx


def test_correction_mode_leads_with_blockers():
    board = _board(
        turn_mode="CORRECTION",
        blockers=[{"id": "b1", "desc": "matrix is commutative"}],
    )
    ctx = build_retrieval_query_context(
        board=board,
        user_message="why does AB != BA",
        retrieval_focus={"default_query": "linear algebra"},
    )
    assert ctx["query_intent"] == "dispel_misconception"
    # blocker text should be first in priority_terms
    assert ctx["priority_terms"][0] == "matrix is commutative"


def test_anchor_mode_leads_with_gaps():
    board = _board(turn_mode="ANCHOR", gaps=["scalar multiplication"])
    ctx = build_retrieval_query_context(
        board=board,
        user_message="explain matrices",
        retrieval_focus={"default_query": "math basics"},
    )
    assert ctx["query_intent"] == "ground_prerequisites"
    assert ctx["priority_terms"][0] == "scalar multiplication"


def test_verify_mode_leads_with_active_node():
    board = _board(turn_mode="VERIFY", active_node="rank_theorem")
    ctx = build_retrieval_query_context(
        board=board,
        user_message="check my proof",
        retrieval_focus={"default_query": "verification"},
    )
    assert ctx["query_intent"] == "validate_understanding"
    assert "rank theorem" == ctx["priority_terms"][0]


def test_paused_mode_leads_with_continuation_prompt():
    board = _board(turn_mode="PAUSED")
    ctx = build_retrieval_query_context(
        board=board,
        user_message="",
        retrieval_focus={"default_query": "fallback"},
        continuation_prompt="we were comparing two matrix factorizations",
    )
    assert ctx["query_intent"] == "resume_thread"
    assert ctx["priority_terms"][0] == "we were comparing two matrix factorizations"


def test_query_intent_falls_back_to_explore_for_unknown_mode():
    board = _board(turn_mode="WHATEVER")
    ctx = build_retrieval_query_context(
        board=board,
        user_message="hi",
        retrieval_focus={},
    )
    # normalize_turn_mode collapses unknowns to EXPLORE
    assert ctx["query_intent"] == "expand_concept"


def test_priority_terms_are_deduplicated():
    board = _board(turn_mode="EXPLORE", active_node="x")
    ctx = build_retrieval_query_context(
        board=board,
        user_message="x",  # same as active_node label after normalization
        retrieval_focus={"default_query": "x"},
    )
    # 'x' should only appear once
    assert ctx["priority_terms"].count("x") == 1


# --- K2 gap re-rank + cognitive_load ---

def test_chunk_matching_blocker_text_ranks_first():
    board = _board(
        turn_mode="EXPLORE",
        blockers=[{"id": "b1", "desc": "eigenvalue"}],
    )
    refs = [
        {"source_ref": "high_score.md", "text": "general info", "score": 0.95, "chunk_id": "c1"},
        {"source_ref": "blocker_match.md", "text": "eigenvalue computation steps", "score": 0.5, "chunk_id": "c2"},
    ]
    bundle = build_prompt_support_bundle(
        board=board,
        prefetched_references=refs,
        retrieval_focus={"turn_mode": "EXPLORE"},
        max_items=2,
    )
    assert bundle[0]["source_ref"] == "blocker_match.md"
    assert bundle[0]["priority_reason"] == "blocker_match"


def test_chunk_matching_gap_text_gets_bonus():
    board = _board(
        turn_mode="EXPLORE",
        gaps=["determinant"],
    )
    refs = [
        {"source_ref": "high.md", "text": "matrix basics", "score": 0.9, "chunk_id": "c1"},
        {"source_ref": "gap_match.md", "text": "the determinant formula explained", "score": 0.5, "chunk_id": "c2"},
    ]
    bundle = build_prompt_support_bundle(
        board=board,
        prefetched_references=refs,
        retrieval_focus={"turn_mode": "EXPLORE"},
        max_items=2,
    )
    # gap_match should beat the higher-raw-score chunk
    assert bundle[0]["source_ref"] == "gap_match.md"
    assert bundle[0]["priority_reason"] == "gap_match"


def test_high_cognitive_load_tightens_to_two_items():
    board = _board(turn_mode="EXPLORE", cognitive_load="HIGH")
    refs = [
        {"source_ref": f"r{i}.md", "text": f"chunk {i}", "score": 0.5, "chunk_id": f"c{i}"}
        for i in range(6)
    ]
    bundle = build_prompt_support_bundle(
        board=board,
        prefetched_references=refs,
        retrieval_focus={"turn_mode": "EXPLORE"},
        max_items=4,  # would normally return 4
    )
    assert len(bundle) == 2


def test_normal_cognitive_load_uses_full_max_items():
    board = _board(turn_mode="EXPLORE", cognitive_load="NORMAL")
    refs = [
        {"source_ref": f"r{i}.md", "text": f"chunk {i}", "score": 0.5, "chunk_id": f"c{i}"}
        for i in range(6)
    ]
    bundle = build_prompt_support_bundle(
        board=board,
        prefetched_references=refs,
        retrieval_focus={"turn_mode": "EXPLORE"},
        max_items=4,
    )
    assert len(bundle) == 4


def test_priority_reason_is_set_for_every_chunk():
    board = _board(turn_mode="EXPLORE")
    refs = [{"source_ref": "r.md", "text": "raw text", "score": 0.5, "chunk_id": "c1"}]
    bundle = build_prompt_support_bundle(
        board=board,
        prefetched_references=refs,
        retrieval_focus={"turn_mode": "EXPLORE"},
        max_items=1,
    )
    assert bundle[0]["priority_reason"] in {"blocker_match", "gap_match", "mode_priority", "raw_score"}
