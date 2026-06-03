"""Integration tests for CoLearn startup wiring against real NanoBot snapshot."""
from __future__ import annotations

import asyncio

import pytest

nanobot_hook = pytest.importorskip("nanobot.agent.hook")
nanobot_tools_registry = pytest.importorskip("nanobot.agent.tools.registry")
nanobot_tools_base = pytest.importorskip("nanobot.agent.tools.base")

from colearn.colearn_adapters.colearn_nanobot_tool import ColearnDashboardTool, colearn_tool_from_metadata
from colearn.colearn_context import set_current_session_id, set_session_store
from colearn.colearn_runtime import install_colearn
from colearn.colearn_host_integration import cmd_colearn, cmd_learn
from colearn.colearn_state.colearn_store import SessionStore
from colearn.colearn_tools.learn_command import LEARN_TOOL_METADATA


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
    assert loop.tools.has("learn")
    assert isinstance(loop.tools.get("colearn"), nanobot_tools_base.Tool)


def test_install_colearn_is_idempotent():
    """Calling install_colearn twice should not duplicate hooks or tools."""
    loop = FakeLoop()

    install_colearn(loop)
    install_colearn(loop)

    assert len(loop._extra_hooks) == 4
    assert len(loop.tools) == 2


def test_install_colearn_accepts_facade():
    """install_colearn should resolve the loop from a Nanobot-like facade."""
    loop = FakeLoop()
    facade = FakeNanobotFacade(loop)

    install_colearn(facade)

    assert len(loop._extra_hooks) == 4
    assert loop.tools.has("colearn")
    assert loop.tools.has("learn")


def test_learn_tool_schema_is_host_compatible():
    """The /learn tool should also register as a NanoBot-compatible tool."""
    registry = nanobot_tools_registry.ToolRegistry()
    registry.register(colearn_tool_from_metadata(LEARN_TOOL_METADATA))

    schema = registry.get("learn").to_schema()
    assert schema["function"]["name"] == "learn"
    properties = schema["function"]["parameters"]["properties"]
    assert "goal" in properties


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


def test_nanobot_toolloader_discovers_colearn_via_entry_point():
    """NanoBot's real ToolLoader should discover CoLearn through nanobot.tools.

    This only passes when the package is installed (editable is fine), so the
    entry point metadata is visible to importlib.metadata. Skip otherwise.
    """
    from importlib.metadata import entry_points

    eps = list(entry_points(group="nanobot.tools"))
    if not any(ep.name == "colearn" for ep in eps):
        pytest.skip("colearn package not installed; entry point not discoverable")

    loader = pytest.importorskip("nanobot.agent.tools.loader")
    discovered = loader.ToolLoader()._discover_plugins()

    assert "colearn" in discovered
    assert discovered["colearn"] is ColearnDashboardTool


def test_enable_for_nanobot_patches_from_config_idempotently():
    """enable_for_nanobot should patch AgentLoop.from_config exactly once."""
    from colearn.colearn_runtime import enable_for_nanobot
    from nanobot.agent.loop import AgentLoop

    original = AgentLoop.from_config
    try:
        plugin1 = enable_for_nanobot()
        patched1 = AgentLoop.from_config
        plugin2 = enable_for_nanobot()
        patched2 = AgentLoop.from_config

        assert patched1 is patched2
        assert plugin1 is plugin2
        assert getattr(patched1, "_colearn_patched_from_config", False) is True
    finally:
        AgentLoop.from_config = original  # type: ignore[method-assign]


def test_patched_from_config_installs_colearn_on_returned_loop():
    """A loop produced by the patched factory should have CoLearn auto-installed."""
    from colearn.colearn_runtime import enable_for_nanobot
    from nanobot.agent.loop import AgentLoop

    class FakeLoop:
        def __init__(self):
            self._extra_hooks = []
            self.tools = nanobot_tools_registry.ToolRegistry()

    fake = FakeLoop()
    original = AgentLoop.from_config
    AgentLoop.from_config = classmethod(lambda cls, *a, **kw: fake)  # type: ignore[method-assign]
    try:
        enable_for_nanobot()
        produced = AgentLoop.from_config()
        assert produced is fake
        assert len(fake._extra_hooks) == 4
        assert fake.tools.has("colearn")
        assert fake.tools.has("learn")
    finally:
        AgentLoop.from_config = original  # type: ignore[method-assign]


def test_install_colearn_exposes_runtime_metadata():
    loop = FakeLoop()

    plugin = install_colearn(loop)

    assert getattr(loop, "_colearn_plugin") is plugin
    runtime = getattr(loop, "_colearn_runtime")
    assert runtime["plugin"] is plugin
    assert runtime["session_store"] is plugin.session_store


@pytest.mark.asyncio
async def test_host_slash_commands_bind_real_session_key(tmp_path):
    from nanobot.bus.events import InboundMessage
    from nanobot.command.router import CommandContext

    loop = FakeLoop()
    plugin = install_colearn(loop)
    session = plugin.setup_session("cli:direct")
    session.blackboard.learning.goal = "Learn vectors"
    plugin.session_store.save(session)

    msg = InboundMessage(channel="cli", sender_id="user", chat_id="direct", content="/colearn")
    ctx = CommandContext(msg=msg, session=None, key=msg.session_key, raw="/colearn", loop=loop)
    out = await cmd_colearn(ctx)
    assert "CoLearn Dashboard" in out.content

    learn_msg = InboundMessage(channel="cli", sender_id="user", chat_id="direct", content="/learn study tensors")
    learn_ctx = CommandContext(
        msg=learn_msg,
        session=None,
        key=learn_msg.session_key,
        raw="/learn study tensors",
        args="study tensors",
        loop=loop,
    )
    learn_out = await cmd_learn(learn_ctx)
    assert "CoLearn Learning Session" in learn_out.content
    saved = plugin.session_store.load("cli:direct")
    assert saved is not None
    assert saved.blackboard.learning.goal == "study tensors"


