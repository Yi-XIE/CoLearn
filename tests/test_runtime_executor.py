"""Tests for NanobotTurnExecutor pure-logic helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import anyio
import pytest

from colearn.learning.turn_contract import LearningTurnRequest
from colearn.runtime_v2.executor import NanobotTurnExecutor
from colearn.utils.async_guards import reject_sync_inside_event_loop as _reject_sync_inside_event_loop


def _make_request(**kwargs) -> LearningTurnRequest:
    defaults = {"session_id": "s1", "turn_id": "t1", "user_message": "hi"}
    defaults.update(kwargs)
    return LearningTurnRequest(**defaults)


def test_coerce_stream_event_basic():
    event = NanobotTurnExecutor._coerce_stream_event("content_delta", "hello", extra="x")
    assert event["type"] == "content_delta"
    assert event["content"] == "hello"
    assert event["metadata"]["phase"] == "content_delta"
    assert event["metadata"]["extra"] == "x"


def test_coerce_stream_event_default_content_empty():
    event = NanobotTurnExecutor._coerce_stream_event("stream_end")
    assert event["content"] == ""
    assert event["metadata"]["phase"] == "stream_end"


def test_apply_model_preset_runtime_unavailable():
    bot = SimpleNamespace()  # no _loop
    executor = NanobotTurnExecutor()
    request = _make_request()
    executor._apply_model_preset(bot=bot, preset="default", request=request)
    assert "model_preset_runtime_unavailable" in request.metadata["_runtime_warnings"]


def test_apply_model_preset_missing_uses_default():
    applied: dict[str, Any] = {}

    class Loop:
        model_presets = {"default": object(), "fast": object()}

        def set_model_preset(self, name):
            applied["preset"] = name

    bot = SimpleNamespace(_loop=Loop())
    executor = NanobotTurnExecutor()
    request = _make_request()
    executor._apply_model_preset(bot=bot, preset="missing", request=request)
    assert applied["preset"] == "default"
    assert any("model_preset_missing:missing" in w for w in request.metadata["_runtime_warnings"])


def test_apply_model_preset_apply_failed_logs_warning():
    class Loop:
        model_presets = {"target": object()}

        def set_model_preset(self, name):
            raise RuntimeError("boom")

    bot = SimpleNamespace(_loop=Loop())
    executor = NanobotTurnExecutor()
    request = _make_request()
    executor._apply_model_preset(bot=bot, preset="target", request=request)
    assert any("model_preset_apply_failed:target:RuntimeError" in w for w in request.metadata["_runtime_warnings"])


def test_apply_model_preset_no_presets_set_directly():
    applied: dict[str, Any] = {}

    class Loop:
        model_presets: dict = {}

        def set_model_preset(self, name):
            applied["preset"] = name

    bot = SimpleNamespace(_loop=Loop())
    executor = NanobotTurnExecutor()
    request = _make_request()
    executor._apply_model_preset(bot=bot, preset="any", request=request)
    assert applied["preset"] == "any"


def test_run_turn_inside_event_loop_raises():
    executor = NanobotTurnExecutor()
    request = _make_request()

    async def attempt():
        executor.run_turn(request=request)

    with pytest.raises(RuntimeError, match="cannot run inside an active event loop"):
        anyio.run(attempt)


def test_reject_sync_inside_event_loop_outside_loop_is_noop():
    _reject_sync_inside_event_loop("test_caller")  # should not raise


def test_stream_hook_emits_content_delta():
    captured: list[dict] = []
    hook = NanobotTurnExecutor._StreamHook(captured.append)

    async def run():
        await hook.on_stream(ctx=None, delta="abc")

    anyio.run(run)
    assert captured[0]["type"] == "content_delta"
    assert captured[0]["content"] == "abc"


def test_stream_hook_skips_empty_delta():
    captured: list[dict] = []
    hook = NanobotTurnExecutor._StreamHook(captured.append)

    async def run():
        await hook.on_stream(ctx=None, delta="")

    anyio.run(run)
    assert captured == []


def test_stream_hook_emits_reasoning_and_end():
    captured: list[dict] = []
    hook = NanobotTurnExecutor._StreamHook(captured.append)

    async def run():
        await hook.emit_reasoning("thinking...")
        await hook.emit_reasoning_end()
        await hook.on_stream_end(ctx=None, resuming=False)

    anyio.run(run)
    types = [e["type"] for e in captured]
    assert types == ["reasoning_delta", "reasoning_end", "stream_end"]


def test_stream_hook_before_execute_tools_emits_tool_calls():
    captured: list[dict] = []
    hook = NanobotTurnExecutor._StreamHook(captured.append)
    ctx = SimpleNamespace(tool_calls=[
        SimpleNamespace(name="memory", arguments={"q": "x"}),
    ])

    async def run():
        await hook.before_execute_tools(ctx)

    anyio.run(run)
    assert captured[0]["type"] == "tool_call"
    assert captured[0]["metadata"]["tool_name"] == "memory"


def test_stream_hook_after_iteration_replays_tool_events():
    captured: list[dict] = []
    hook = NanobotTurnExecutor._StreamHook(captured.append)
    ctx = SimpleNamespace(tool_events=[{"type": "tool_result", "content": "ok", "tool_name": "memory"}])

    async def run():
        await hook.after_iteration(ctx)

    anyio.run(run)
    assert captured[0]["type"] == "tool_result"
    assert captured[0]["content"] == "ok"
    assert captured[0]["metadata"]["tool_name"] == "memory"


def test_build_prompt_returns_string():
    executor = NanobotTurnExecutor()
    prompt = executor._build_prompt(_make_request(user_message="hello"))
    assert isinstance(prompt, str)
    assert "hello" in prompt


def test_finalize_normalizes_turn_result():
    executor = NanobotTurnExecutor()
    request = _make_request()
    result = executor.finalize(
        request=request,
        final_text="answer",
        learning_result={"tool_events": [], "raw_messages": []},
    )
    assert result.final_text == "answer"


def test_run_turn_async_with_fake_bot():
    """Exercise the async path with a fake bot to cover stream emit + warning path."""

    class FakeRunResult:
        content = "final answer"
        messages: list = []
        tools_used: list = []

    class FakeBot:
        def __init__(self):
            self._loop = None

        async def run(self, prompt, *, session_key, hooks):
            return FakeRunResult()

    fake_bot = FakeBot()
    executor = NanobotTurnExecutor(_bot=fake_bot)

    request = _make_request(enabled_tools=["__none__"])

    async def run():
        return await executor._run_turn_async(request=request)

    final, messages, tools = anyio.run(run)
    assert final == "final answer"
    assert tools == []


def test_run_turn_async_swallows_stream_emit_exception():
    """stream_emit callback exception should be captured in _runtime_warnings."""

    captured_warnings: list[str] = []

    class FakeRunResult:
        content = ""
        messages: list = []
        tools_used: list = []

    class FakeBot:
        def __init__(self):
            self._loop = None

        async def run(self, prompt, *, session_key, hooks):
            # invoke the hook to trigger stream_emit
            for h in hooks:
                await h.on_stream(ctx=None, delta="trigger")
            return FakeRunResult()

    def bad_emit(_event):
        raise RuntimeError("subscriber gone")

    request = _make_request(enabled_tools=["__none__"], stream_emit=bad_emit)
    executor = NanobotTurnExecutor(_bot=FakeBot())

    async def run():
        return await executor._run_turn_async(request=request)

    anyio.run(run)
    warnings = request.metadata.get("_runtime_warnings", [])
    assert any("stream_emit_failed:RuntimeError" in w for w in warnings)
