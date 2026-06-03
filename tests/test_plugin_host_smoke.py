"""Phase 3.7 — host smoke test against the vendored NanoBot v0.2.1 snapshot.

These tests verify that CoLearn plugin surfaces line up with the real NanoBot
public APIs (AgentHook, ToolRegistry, AgentLoop hooks=...). They DO NOT spin up a
full LLM-driven turn — that requires provider credentials. They DO verify:

1. CoLearn hooks subclass the real `nanobot.agent.hook.AgentHook`.
2. CoLearn tools can be wrapped into real `Tool` objects and registered with the
   real `ToolRegistry`.
3. CHAT vs LEARNING routing reads correctly from a populated blackboard session.
4. `/colearn` snapshot reflects the real session state after a hook run.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

# Import nanobot real modules (snapshot is on sys.path via tests/conftest.py).
nanobot_hook = pytest.importorskip("nanobot.agent.hook")
nanobot_tools_base = pytest.importorskip("nanobot.agent.tools.base")
nanobot_tools_registry = pytest.importorskip("nanobot.agent.tools.registry")

from colearn.colearn_adapters.colearn_nanobot_tool import colearn_tool_from_metadata
from colearn.colearn_adapters.colearn_tool_registry import ToolRegistryAdapter
from colearn.colearn_context import set_current_session_id, set_session_store
from colearn.colearn_hooks.colearn_blackboard_monitors import BlackboardMonitorHook
from colearn.colearn_hooks.colearn_finalize import CoLearnFinalizeHook
from colearn.colearn_hooks.colearn_preflight import CoLearnPreflightHook
from colearn.colearn_hooks.colearn_session_binder import SessionBinderHook
from colearn.colearn_plugin import CoLearnPlugin
from colearn.colearn_state.colearn_store import SessionStore
from colearn.colearn_tools.colearn_command import TOOL_METADATA, colearn_snapshot
from colearn.colearn_tools.learn_command import LEARN_TOOL_METADATA


def test_colearn_hooks_subclass_real_agent_hook():
    """All CoLearn hooks must extend the real NanoBot AgentHook ABC."""
    plugin = CoLearnPlugin()

    for hook in plugin.get_hooks():
        assert isinstance(hook, nanobot_hook.AgentHook), type(hook)
    assert {type(h).__name__ for h in plugin.get_hooks()} == {
        SessionBinderHook.__name__,
        CoLearnPreflightHook.__name__,
        BlackboardMonitorHook.__name__,
        CoLearnFinalizeHook.__name__,
    }


def test_colearn_tool_registers_with_real_tool_registry():
    """CoLearn tools must register cleanly into NanoBot's real ToolRegistry."""
    registry = nanobot_tools_registry.ToolRegistry()

    ToolRegistryAdapter(registry).register(TOOL_METADATA)
    ToolRegistryAdapter(registry).register(LEARN_TOOL_METADATA)

    assert "colearn" in registry
    assert "learn" in registry
    tool = registry.get("colearn")
    assert isinstance(tool, nanobot_tools_base.Tool)
    schema = tool.to_schema()
    assert schema["function"]["name"] == "colearn"


def test_colearn_tool_handler_runs_through_registry(tmp_path):
    """ToolRegistry.execute should route to the CoLearn handler and return Markdown."""
    registry = nanobot_tools_registry.ToolRegistry()
    registry.register(colearn_tool_from_metadata(TOOL_METADATA))

    store = SessionStore(tmp_path / "sessions")
    session = store.create_session("smoke-session")
    session.blackboard.learning.goal = "学习机器学习"
    session.blackboard.learning.active_node_id = "ml.model.basic"
    store.save(session)

    set_current_session_id("smoke-session")
    set_session_store(store)

    output = asyncio.run(registry.execute("colearn", {}))
    assert "CoLearn Dashboard" in output
    assert "学习机器学习" in output


def test_blackboard_monitor_runs_under_real_hook_context(tmp_path):
    """BlackboardMonitorHook should update runtime status under a real AgentHookContext."""
    store = SessionStore(tmp_path / "sessions")
    store.save(store.create_session("monitor-session"))
    set_current_session_id("monitor-session")
    set_session_store(store)

    hook = BlackboardMonitorHook()
    context = nanobot_hook.AgentHookContext(iteration=0, messages=[])

    asyncio.run(hook.before_iteration(context))
    snapshot_running = colearn_snapshot()
    assert snapshot_running["runtime"]["current_task_status"] == "RUNNING"

    context.stop_reason = "end_turn"
    asyncio.run(hook.after_iteration(context))
    snapshot_done = colearn_snapshot()
    assert snapshot_done["runtime"]["current_task_status"] == "SUCCESS"


def test_install_plan_matches_real_host_surfaces():
    """NanoBotAdapter.build_install_plan should expose surfaces real NanoBot accepts."""
    from colearn.colearn_adapters.nanobot_adapter import NanoBotAdapter

    plan = NanoBotAdapter(CoLearnPlugin()).build_install_plan()

    assert all(isinstance(h, nanobot_hook.AgentHook) for h in plan.hooks)
    assert plan.tools[0]["command"] == "/colearn"
    assert any(tool["command"] == "/learn" for tool in plan.tools)
    slots = {ext["slot"] for ext in plan.ui_extensions}
    assert {"apps", "page", "thread_toolbar"}.issubset(slots)


def test_real_nanobot_snapshot_present():
    """Sanity-check the vendored NanoBot snapshot used by this smoke suite."""
    snapshot = (
        Path(__file__).resolve().parents[1]
        / "third_party"
        / "nanobot-0.2.1"
        / "nanobot"
    )
    assert snapshot.is_dir()
