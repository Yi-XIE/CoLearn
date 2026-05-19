"""Tests for RecentTurnReplayCache eviction and cleanup."""

from __future__ import annotations

from colearn.api.turn_cache import RecentTurnReplayCache


def test_cache_start_append_get():
    cache = RecentTurnReplayCache(max_turns=10)
    cache.start_turn("t1", session_id="s1", project_id="p1")
    cache.append("t1", {"type": "session", "seq": 1})
    cache.append("t1", {"type": "content", "seq": 2})
    events = cache.get_events("t1")
    assert len(events) == 2
    assert cache.get_index("t1") == {"session_id": "s1", "project_id": "p1"}


def test_cache_eviction():
    cache = RecentTurnReplayCache(max_turns=3)
    for i in range(5):
        cache.start_turn(f"t{i}", session_id=f"s{i}", project_id="p")
        cache.append(f"t{i}", {"seq": i})
    assert cache.get_events("t0") == []
    assert cache.get_events("t1") == []
    assert cache.get_events("t4") == [{"seq": 4}]
    assert cache.get_index("t0") is None
    assert cache.get_index("t4") is not None


def test_cache_remove():
    cache = RecentTurnReplayCache(max_turns=10)
    cache.start_turn("t1", session_id="s1", project_id="p1")
    cache.append("t1", {"seq": 1})
    cache.remove("t1")
    assert cache.get_events("t1") == []
    assert cache.get_index("t1") is None


def test_cache_clear():
    cache = RecentTurnReplayCache(max_turns=10)
    cache.start_turn("t1", session_id="s1", project_id="p1")
    cache.start_turn("t2", session_id="s2", project_id="p2")
    cache.clear()
    assert cache.get_events("t1") == []
    assert cache.get_events("t2") == []


def test_cache_finish_turn_moves_to_end():
    cache = RecentTurnReplayCache(max_turns=3)
    cache.start_turn("t1", session_id="s1", project_id="p")
    cache.start_turn("t2", session_id="s2", project_id="p")
    cache.start_turn("t3", session_id="s3", project_id="p")
    cache.finish_turn("t1")
    cache.start_turn("t4", session_id="s4", project_id="p")
    assert cache.get_index("t2") is None
    assert cache.get_index("t1") is not None
