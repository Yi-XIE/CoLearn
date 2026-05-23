"""Tests for ProductCompressionBridge and RuntimeCompressionBridge."""

from __future__ import annotations

from colearn.compression import ProductCompressionBridge, RuntimeCompressionBridge
from colearn.learning.retrieval_bundle import RetrievalBundle, RetrievalChunk
from colearn.learning.state import BoardFacts, ContinuationFacts, PolicyDecision
from colearn.learning.turn_contract import LearningTurnRequest
from colearn.projects.models import LearningProject
from colearn.sessions.store import LearningSession


def _make_session(**kwargs) -> LearningSession:
    defaults = {"session_id": "s1", "project_id": "p1"}
    defaults.update(kwargs)
    return LearningSession(**defaults)


def _make_project(**kwargs) -> LearningProject:
    defaults = {"project_id": "p1", "title": "Test"}
    defaults.update(kwargs)
    return LearningProject(**defaults)


def _make_board(**kwargs) -> BoardFacts:
    defaults = {"project_id": "p1", "session_id": "s1", "board_version": 2, "updated_at": "2026-01-01"}
    defaults.update(kwargs)
    return BoardFacts(**defaults)


def _make_request(**kwargs) -> LearningTurnRequest:
    defaults = {"session_id": "s1", "turn_id": "t1", "user_message": "hello", "turn_mode": "EXPLORE"}
    defaults.update(kwargs)
    return LearningTurnRequest(**defaults)


# --- ProductCompressionBridge ---

def test_product_compress_basic():
    bridge = ProductCompressionBridge()
    result = bridge.compress(
        project=_make_project(),
        session=_make_session(),
        board=_make_board(),
        request=_make_request(),
        final_text="Short answer.",
    )
    assert result.review_summary == "Short answer."
    assert "hello" in result.continuation_prompt
    assert result.board_patch["board_version"] == 2


def test_product_compress_truncates_long_text():
    bridge = ProductCompressionBridge(max_summary_chars=20, max_continuation_chars=30)
    long_text = "A" * 100
    result = bridge.compress(
        project=_make_project(),
        session=_make_session(),
        board=_make_board(),
        request=_make_request(user_message="B" * 100),
        final_text=long_text,
    )
    assert len(result.review_summary) == 20
    assert result.review_summary.endswith("...")
    assert len(result.continuation_prompt) == 30
    assert result.continuation_prompt.endswith("...")


def test_product_compress_empty_text():
    bridge = ProductCompressionBridge()
    board = _make_board(continuation=ContinuationFacts(next_prompt_hint="fallback hint"))
    result = bridge.compress(
        project=_make_project(),
        session=_make_session(continuation_prompt="session cp"),
        board=board,
        request=_make_request(user_message=""),
        final_text="",
    )
    assert result.review_summary == ""
    assert result.continuation_prompt == "fallback hint"


def test_product_compress_chinese_text():
    bridge = ProductCompressionBridge(max_summary_chars=10)
    result = bridge.compress(
        project=_make_project(),
        session=_make_session(),
        board=_make_board(),
        request=_make_request(user_message="理解线性代数"),
        final_text="这是一个很长的中文回答内容用来测试截断",
    )
    assert len(result.review_summary) == 10
    assert result.review_summary.endswith("...")


def test_product_compress_board_patch_structure():
    bridge = ProductCompressionBridge()
    policy = PolicyDecision(main_goal="learn algebra", review_focus=["vectors", "matrices"])
    result = bridge.compress(
        project=_make_project(),
        session=_make_session(),
        board=_make_board(),
        request=_make_request(policy_decision=policy),
        final_text="Done.",
    )
    patch = result.board_patch
    assert "current_turn_mode" in patch
    assert "continuation" in patch
    assert "latest_review" in patch
    assert patch["latest_review"]["points"] == ["learn algebra"]
    assert patch["latest_review"]["confusion_points"] == ["vectors", "matrices"]


# --- RuntimeCompressionBridge ---

def test_runtime_compress_no_truncation():
    bridge = RuntimeCompressionBridge()
    request = _make_request(user_message="short")
    result = bridge.compress(request=request)
    assert result.request.user_message == "short"
    assert result.notes == []


def test_runtime_compress_truncates_user_message():
    bridge = RuntimeCompressionBridge(max_user_message_chars=10)
    request = _make_request(user_message="A" * 50)
    result = bridge.compress(request=request)
    assert len(result.request.user_message) == 13  # 10 + "..."
    assert "user_message_truncated" in result.notes


def test_runtime_compress_truncates_retrieval():
    bundle = RetrievalBundle(
        query="test",
        text="X" * 5000,
        chunks=[
            RetrievalChunk(text="C" * 2000, source_ref={"name": "doc.pdf"}),
            RetrievalChunk(text="short chunk"),
        ],
        retrieval_status="ready",
    )
    bridge = RuntimeCompressionBridge(max_retrieval_chars=100, max_chunk_chars=50)
    request = _make_request(retrieval_bundle=bundle)
    result = bridge.compress(request=request)
    assert len(result.request.retrieval_bundle.text) <= 104  # 100 + "..."
    assert len(result.request.retrieval_bundle.chunks[0].text) <= 53
    assert result.request.retrieval_bundle.chunks[1].text == "short chunk"
    assert "retrieval_truncated" in result.notes
    assert "retrieval_text_truncated" in result.request.retrieval_bundle.warnings
