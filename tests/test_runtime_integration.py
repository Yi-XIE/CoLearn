"""Integration tests for CoLearn startup wiring against real NanoBot snapshot."""
from __future__ import annotations

import asyncio

import pytest

nanobot_hook = pytest.importorskip("nanobot.agent.hook")
nanobot_tools_registry = pytest.importorskip("nanobot.agent.tools.registry")
nanobot_tools_base = pytest.importorskip("nanobot.agent.tools.base")

from colearn.colearn_adapters.colearn_nanobot_tool import ColearnDashboardTool
from colearn.colearn_context import set_current_session_id, set_session_store
from colearn.colearn_runtime import install_colearn
from colearn.colearn_state.colearn_store import SessionStore


class FakeLoop:
    """Minimal stand-in matching the AgentLoop attributes install_colearn touches."""

    def __init__(self):
        self._extra_hooks = []
        self.tools = nanobot_tools_registry.ToolRegistry()


class FakeNanobotFacade:
    """Mirror of the Nanobot facade exposing a private _loop."""

    def __init__(self, loop):
        self._loop = loop


def test_install_colearn_attaches_hooks_and_tool_to_loop():
    """install_colearn should wire 4 hooks and the /colearn tool onto a loop."""
    loop = FakeLoop()

    install_colearn(loop)

    assert len(loop._extra_hooks) == 4
    assert all(isinstance(h, nanobot_hook.AgentHook) for h in loop._extra_hooks)
    assert loop.tools.has("colearn")
    assert isinstance(loop.tools.get("colearn"), nanobot_tools_base.Tool)


def test_install_colearn_is_idempotent():
    """Calling install_colearn twice should not duplicate hooks or tools."""
    loop = FakeLoop()

    install_colearn(loop)
    install_colearn(loop)

    assert len(loop._extra_hooks) == 4
    assert len(loop.tools) == 1


def test_install_colearn_accepts_facade():
    """install_colearn should resolve the loop from a Nanobot-like facade."""
    loop = FakeLoop()
    facade = FakeNanobotFacade(loop)

    install_colearn(facade)

    assert len(loop._extra_hooks) == 4
    assert loop.tools.has("colearn")


def test_entry_point_tool_class_executes(tmp_path):
    """The entry-point-discoverable tool class should run with no constructor args."""
    tool = ColearnDashboardTool()
    assert isinstance(tool, nanobot_tools_base.Tool)
    assert tool.name == "colearn"

    store = SessionStore(tmp_path / "sessions")
    session = store.create_session("ep-session")
    session.blackboard.learning.goal = "学习物理"
    store.save(session)
    set_current_session_id("ep-session")
    set_session_store(store)

    output = asyncio.run(tool.execute())
    assert "CoLearn Dashboard" in output
    assert "学习物理" in output


def test_entry_point_tool_schema_is_host_compatible():
    """The tool schema must be acceptable to NanoBot's ToolRegistry."""
    registry = nanobot_tools_registry.ToolRegistry()
    registry.register(ColearnDashboardTool())

    schema = registry.get("colearn").to_schema()
    assert schema["function"]["name"] == "colearn"
    assert "description" in schema["function"]
