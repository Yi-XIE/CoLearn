"""Tests for heuristic learning-signal extraction."""

from __future__ import annotations

from colearn.learning.signal_extractor import extract_learning_signals


def test_chinese_understood():
    events = extract_learning_signals("我已经理解了矩阵乘法的本质。")
    assert any(e["kind"] == "understood_concept" for e in events)
    assert any("矩阵乘法" in e["payload"]["concept"] for e in events)


def test_chinese_blocked():
    events = extract_learning_signals("我还是不明白特征值这个概念，怎么算？")
    assert any(e["kind"] == "still_blocked" for e in events)
    assert any("特征值" in e["payload"]["concept"] for e in events)


def test_english_understood():
    events = extract_learning_signals("I understand eigenvectors now.")
    assert any(e["kind"] == "understood_concept" for e in events)
    assert any("eigenvectors" in e["payload"]["concept"] for e in events)


def test_english_blocked():
    events = extract_learning_signals("I'm confused about determinants.")
    assert any(e["kind"] == "still_blocked" for e in events)
    assert any("determinants" in e["payload"]["concept"] for e in events)


def test_no_signal_returns_empty():
    events = extract_learning_signals("Here is some general material about matrices.")
    assert events == []


def test_empty_input_returns_empty():
    assert extract_learning_signals("") == []
    assert extract_learning_signals("   \n\n  ") == []


def test_dedupes_same_concept():
    text = "我理解了矩阵乘法。我已经理解了矩阵乘法。"
    events = extract_learning_signals(text)
    understood = [e for e in events if e["kind"] == "understood_concept"]
    # both lines mention 矩阵乘法; should be deduped by concept
    concepts = {e["payload"]["concept"] for e in understood}
    assert len(concepts) == 1


def test_multiple_distinct_signals():
    text = "我理解了向量空间，但还是不明白线性变换。"
    events = extract_learning_signals(text)
    kinds = {e["kind"] for e in events}
    assert "understood_concept" in kinds
    assert "still_blocked" in kinds


def test_event_shape():
    events = extract_learning_signals("我理解了导数。")
    assert events
    e = events[0]
    assert "event_id" in e
    assert e["payload"]["source"] == "extracted_heuristic"
    assert "raw_match" in e["payload"]


def test_dont_understand_pattern_english():
    events = extract_learning_signals("I don't understand integration by parts.")
    assert any(e["kind"] == "still_blocked" for e in events)
    assert any("integration" in e["payload"]["concept"] for e in events)
