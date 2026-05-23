"""Tests for turn timeout in NanobotTurnExecutor."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import anyio
import pytest

from colearn.learning.turn_contract import LearningTurnRequest
from colearn.runtime_v2.executor import NanobotTurnExecutor, TurnTimeoutError


def _make_request(**kwargs) -> LearningTurnRequest:
    defaults = {"session_id": "s1", "turn_id": "t1", "user_message": "hi"}
    defaults.update(kwargs)
    return LearningTurnRequest(**defaults)


def test_turn_timeout_raises_when_bot_hangs():
    class HangingBot:
        _loop = None

        async def run(self, prompt, *, session_key, hooks):
            await anyio.sleep(60)  # never returns within timeout
            return SimpleNamespace(content="never", messages=[], tools_used=[])

    executor = NanobotTurnExecutor(_bot=HangingBot())
    request = _make_request(metadata={"turn_timeout_seconds": 0.1, "_runtime_warnings": []})

    async def run():
        return await executor._run_turn_async(request=request)

    with pytest.raises(TurnTimeoutError, match="exceeded timeout"):
        anyio.run(run)


def test_turn_completes_within_timeout():
    class FastBot:
        _loop = None

        async def run(self, prompt, *, session_key, hooks):
            return SimpleNamespace(content="done", messages=[], tools_used=[])

    executor = NanobotTurnExecutor(_bot=FastBot())
    request = _make_request(metadata={"turn_timeout_seconds": 5.0, "_runtime_warnings": []})

    async def run():
        return await executor._run_turn_async(request=request)

    final, _, _ = anyio.run(run)
    assert final == "done"


def test_no_timeout_means_no_wait_for():
    """Backward-compat: when turn_timeout_seconds absent, behavior unchanged."""
    class FastBot:
        _loop = None

        async def run(self, prompt, *, session_key, hooks):
            return SimpleNamespace(content="ok", messages=[], tools_used=[])

    executor = NanobotTurnExecutor(_bot=FastBot())
    request = _make_request()

    async def run():
        return await executor._run_turn_async(request=request)

    final, _, _ = anyio.run(run)
    assert final == "ok"


def test_zero_or_negative_timeout_disables_check():
    class FastBot:
        _loop = None

        async def run(self, prompt, *, session_key, hooks):
            return SimpleNamespace(content="ok", messages=[], tools_used=[])

    executor = NanobotTurnExecutor(_bot=FastBot())
    request = _make_request(metadata={"turn_timeout_seconds": 0, "_runtime_warnings": []})

    async def run():
        return await executor._run_turn_async(request=request)

    final, _, _ = anyio.run(run)
    assert final == "ok"
