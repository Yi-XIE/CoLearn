"""Tests for colearn.runtime_v2.tooling install_colearn_tools and CoLearn tools."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anyio
import pytest

from colearn.learning.turn_contract import LearningTurnRequest
from colearn.memory.store import EventMemoryStore, MemoryEvent
from colearn.runtime_v2.tooling import bind_colearn_tools, install_colearn_tools, register_colearn_tools
from colearn.storage.json_store import JsonStateStore


class _Registry:
    def __init__(self) -> None:
        self.registered: dict[str, Any] = {}

    def has(self, name: str) -> bool:
        return name in self.registered

    def unregister(self, name: str) -> None:
        self.registered.pop(name, None)

    def register(self, tool: Any) -> None:
        self.registered[tool.name] = tool

    def get(self, name: str) -> Any:
        return self.registered.get(name)


def _make_bot(*, public_tools: bool = False) -> SimpleNamespace:
    registry = _Registry()
    bot = SimpleNamespace(_loop=SimpleNamespace(tools=registry))
    if public_tools:
        bot.tools = registry
    return bot


def _make_request(**kwargs) -> LearningTurnRequest:
    defaults = {"session_id": "s1", "turn_id": "t1", "project_id": "p1", "user_message": "hi"}
    defaults.update(kwargs)
    return LearningTurnRequest(**defaults)


def test_install_no_enabled_tools_returns_early():
    # enabled_tools=["__none__"] doesn't match any known tool; nothing should register
    bot = _make_bot()
    install_colearn_tools(bot=bot, request=_make_request(enabled_tools=["__none__"]))
    assert bot._loop.tools.registered == {}


def test_register_no_enabled_tools_returns_early():
    bot = _make_bot(public_tools=True)
    register_colearn_tools(bot=bot, request=_make_request(enabled_tools=["__none__"]))
    assert bot.tools.registered == {}


def test_install_no_registry_returns_early():
    bot = SimpleNamespace(_loop=SimpleNamespace(tools=None))
    with pytest.raises(RuntimeError, match="tool registry"):
        install_colearn_tools(bot=bot, request=_make_request(enabled_tools=["memory"]))


def test_install_memory_only():
    bot = _make_bot(public_tools=True)
    install_colearn_tools(bot=bot, request=_make_request(enabled_tools=["memory"]))
    assert "memory" in bot.tools.registered
    assert "lightrag" not in bot.tools.registered


def test_install_both_tools():
    bot = _make_bot(public_tools=True)
    install_colearn_tools(bot=bot, request=_make_request(enabled_tools=["memory", "lightrag"]))
    assert "memory" in bot.tools.registered
    assert "lightrag" in bot.tools.registered


def test_install_replaces_existing_tools():
    bot = _make_bot(public_tools=True)
    bot.tools.registered["memory"] = "stale"
    bot.tools.registered["lightrag"] = "stale"
    install_colearn_tools(bot=bot, request=_make_request(enabled_tools=["memory", "lightrag"]))
    assert bot.tools.registered["memory"] != "stale"
    assert bot.tools.registered["lightrag"] != "stale"


def test_install_reuses_existing_colearn_tool_instances():
    bot = _make_bot(public_tools=True)
    request_one = _make_request(enabled_tools=["memory", "lightrag"], user_message="first")
    install_colearn_tools(bot=bot, request=request_one)
    memory_tool = bot.tools.registered["memory"]
    lightrag_tool = bot.tools.registered["lightrag"]

    request_two = _make_request(enabled_tools=["memory", "lightrag"], user_message="second")
    install_colearn_tools(bot=bot, request=request_two)

    assert bot.tools.registered["memory"] is memory_tool
    assert bot.tools.registered["lightrag"] is lightrag_tool


def test_bind_updates_existing_tool_request():
    bot = _make_bot(public_tools=True)
    request_one = _make_request(enabled_tools=["memory"], user_message="first")
    register_colearn_tools(bot=bot, request=request_one)
    tool = bot.tools.registered["memory"]

    request_two = _make_request(enabled_tools=["memory"], user_message="second")
    bind_colearn_tools(bot=bot, request=request_two)

    async def run():
        return await tool.execute(query="")

    result = anyio.run(run)
    assert result["message"] == "No memory references are attached for this turn."


def test_install_private_registry_fallback_adds_warning():
    bot = _make_bot()
    request = _make_request(enabled_tools=["memory"])
    install_colearn_tools(bot=bot, request=request)
    assert "memory" in bot._loop.tools.registered
    assert "tool_registry_private_api_fallback" in request.metadata["_runtime_warnings"]


def test_memory_tool_returns_events_from_store(tmp_path: Path):
    store = EventMemoryStore(state_store=JsonStateStore(tmp_path))
    store.append(MemoryEvent(event_id="e1", kind="review_written", payload={"session_id": "s1", "project_id": "p1", "summary": "Hello world"}))
    bot = _make_bot(public_tools=True)
    request = _make_request(enabled_tools=["memory"])
    install_colearn_tools(bot=bot, request=request, memory_store=store)
    tool = bot.tools.registered["memory"]

    async def run():
        return await tool.execute(query="hello")

    result = anyio.run(run)
    assert "id=e1" in result
    assert "Hello world" in result


def test_memory_tool_empty_returns_empty_payload():
    bot = _make_bot(public_tools=True)
    request = _make_request(enabled_tools=["memory"], memory_references=[])
    install_colearn_tools(bot=bot, request=request, memory_store=None)
    tool = bot.tools.registered["memory"]

    async def run():
        return await tool.execute(query="anything")

    result = anyio.run(run)
    assert isinstance(result, dict)
    assert result["status"] == "empty"
    assert result["evidence_refs"] == []


def test_memory_tool_with_memory_refs_normalizes_evidence():
    bot = _make_bot(public_tools=True)
    request = _make_request(enabled_tools=["memory"], memory_references=["ref-1", "ref-2"])
    install_colearn_tools(bot=bot, request=request, memory_store=None)
    tool = bot.tools.registered["memory"]

    async def run():
        return await tool.execute(query="x")

    result = anyio.run(run)
    assert isinstance(result, dict)
    assert len(result["evidence_refs"]) == 2
    assert result["evidence_refs"][0]["source_ref"] == "ref-1"
    assert result["evidence_refs"][0]["chunk_id"] == "memory_0"


def test_memory_tool_handles_store_exception():
    class ExplodingStore:
        def search_events(self, **kwargs):
            raise RuntimeError("kaboom")

    bot = _make_bot(public_tools=True)
    request = _make_request(enabled_tools=["memory"])
    install_colearn_tools(bot=bot, request=request, memory_store=ExplodingStore())
    tool = bot.tools.registered["memory"]

    async def run():
        return await tool.execute(query="x")

    result = anyio.run(run)
    assert result["status"] == "error"
    assert "Memory context unavailable" in result["message"]


def test_lightrag_tool_uses_retrieval_service():
    class FakeBundle:
        def __init__(self):
            self.retrieval_status = "ready"
            self.references = [{"source_ref": "doc.md", "source_path": "doc.md"}]
            self.warnings: list[str] = []
            self.fallback_reason = ""
            self.text = "retrieved"

    class FakeService:
        async def async_build_bundle_for_source_refs(self, **kwargs):
            self.last_call = kwargs
            return FakeBundle()

    bot = _make_bot(public_tools=True)
    service = FakeService()
    request = _make_request(
        enabled_tools=["lightrag"],
        source_references=[{"source_ref": "doc.md", "source_path": "doc.md"}],
    )
    install_colearn_tools(bot=bot, request=request, retrieval_service=service)
    tool = bot.tools.registered["lightrag"]

    async def run():
        return await tool.execute(question="what is X")

    result = anyio.run(run)
    assert result["status"] == "ready"
    assert result["text"] == "retrieved"
    assert result["source_refs"] == 1
    assert service.last_call["query"] == "what is X"


def test_lightrag_tool_handles_service_exception():
    class ExplodingService:
        async def async_build_bundle_for_source_refs(self, **kwargs):
            raise RuntimeError("boom")

    bot = _make_bot(public_tools=True)
    request = _make_request(enabled_tools=["lightrag"])
    install_colearn_tools(bot=bot, request=request, retrieval_service=ExplodingService())
    tool = bot.tools.registered["lightrag"]

    async def run():
        return await tool.execute(question="q")

    result = anyio.run(run)
    assert result["status"] == "error"
    assert result["fallback_reason"] == "tool_exception"


def test_normalize_evidence_rows_via_memory_tool_handles_missing_fields():
    bot = _make_bot(public_tools=True)
    request = _make_request(
        enabled_tools=["memory"],
        memory_references=["ref-only", ""],
    )
    install_colearn_tools(bot=bot, request=request, memory_store=None)
    tool = bot.tools.registered["memory"]

    async def run():
        return await tool.execute(query="")

    result = anyio.run(run)
    refs = result["evidence_refs"]
    assert len(refs) == 1  # empty ref is filtered out
    assert refs[0]["source_ref"] == "ref-only"
    assert refs[0]["confidence"] == 0.0
    assert refs[0]["support_type"] == "reference"
