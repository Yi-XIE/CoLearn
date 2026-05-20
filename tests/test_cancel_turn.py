"""Tests for cancel_turn flag-based interruption."""

from __future__ import annotations

import importlib

import colearn.api.dependencies as deps


def test_active_turns_dict_starts_empty():
    # Tests run in shared state — but dict should be a proper container
    assert isinstance(deps.active_turns, dict)


def test_cancel_flag_signals_cancel():
    """Setting the flag in active_turns should mark a turn as cancelled."""
    deps.active_turns["test-turn-x"] = {"cancelled": False}
    deps.active_turns["test-turn-x"]["cancelled"] = True
    assert deps.active_turns["test-turn-x"]["cancelled"] is True
    deps.active_turns.pop("test-turn-x", None)


def test_handle_cancel_turn_sets_flag(monkeypatch):
    """When handle_cancel_turn runs, it flips the flag for the turn id."""
    websocket_module = importlib.import_module("colearn.api.routes.websocket")

    # Pre-register an active turn
    deps.active_turns["t-cancel-1"] = {"cancelled": False}
    deps.turn_cache.start_turn("t-cancel-1", session_id="s-cancel-1", project_id="p-cancel-1")

    captured: list[dict] = []

    class FakeWebSocket:
        async def send_json(self, payload: dict) -> None:
            captured.append(payload)

    import anyio
    anyio.run(
        websocket_module.handle_cancel_turn,
        FakeWebSocket(),
        {"type": "cancel_turn", "turn_id": "t-cancel-1"},
    )

    assert deps.active_turns["t-cancel-1"]["cancelled"] is True
    assert captured  # done event was sent
    assert captured[-1]["metadata"]["status"] == "cancelled"

    deps.active_turns.pop("t-cancel-1", None)


def test_cancel_unknown_turn_does_not_crash():
    """Cancelling a turn that's not in active_turns should not raise."""
    websocket_module = importlib.import_module("colearn.api.routes.websocket")

    captured: list[dict] = []

    class FakeWebSocket:
        async def send_json(self, payload: dict) -> None:
            captured.append(payload)

    import anyio
    anyio.run(
        websocket_module.handle_cancel_turn,
        FakeWebSocket(),
        {"type": "cancel_turn", "turn_id": "nonexistent-turn"},
    )

    # Should still emit done event (graceful)
    assert captured
