"""Tests for memory store eviction and session store idle cleanup."""

from __future__ import annotations

import time
import tempfile
from pathlib import Path

from colearn.memory.store import EventMemoryStore, MemoryEvent
from colearn.sessions.store import SessionStore
from colearn.storage.json_store import JsonStateStore


def test_memory_store_evicts_oldest_events():
    with tempfile.TemporaryDirectory() as tmp:
        store = EventMemoryStore(
            state_store=JsonStateStore(root=Path(tmp)),
            max_events=5,
        )
        for i in range(10):
            store.append(MemoryEvent(event_id=f"ev-{i}", kind="test", payload={"i": i}))

        events = store.list_events()
        assert len(events) == 5
        assert events[0].event_id == "ev-5"
        assert events[-1].event_id == "ev-9"


def test_memory_store_persists_after_eviction():
    with tempfile.TemporaryDirectory() as tmp:
        state = JsonStateStore(root=Path(tmp))
        store = EventMemoryStore(state_store=state, max_events=3)
        for i in range(5):
            store.append(MemoryEvent(event_id=f"ev-{i}", kind="test", payload={}))

        store2 = EventMemoryStore(state_store=state, max_events=3)
        events = store2.list_events()
        assert len(events) == 3
        assert events[0].event_id == "ev-2"


def test_session_store_evicts_idle():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(
            state_store=JsonStateStore(root=Path(tmp)),
            max_idle_seconds=1,
        )
        store.create_session(session_id="s1", project_id="p1")
        store.create_session(session_id="s2", project_id="p1")

        assert store.get_session("s1") is not None
        assert store.get_session("s2") is not None

        time.sleep(1.1)
        store.create_session(session_id="s3", project_id="p1")

        assert store.get_session("s1") is None
        assert store.get_session("s2") is None
        assert store.get_session("s3") is not None
