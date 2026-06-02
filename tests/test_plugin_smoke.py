"""Smoke tests for CoLearn plugin registration and host adapter wiring."""
from pathlib import Path


def test_plugin_initialization_without_nanobot():
    """CoLearnPlugin should initialize without requiring NanoBot to be installed."""
    from colearn.colearn_plugin import CoLearnPlugin

    plugin = CoLearnPlugin()

    assert plugin.name == "colearn"
    assert plugin.session_store is not None
    assert plugin.context_builder is not None
    assert plugin.blackboard_writer is not None


def test_plugin_get_hooks():
    """CoLearnPlugin should return resident hooks in execution order."""
    from colearn.colearn_hooks.colearn_blackboard_monitors import BlackboardMonitorHook
    from colearn.colearn_hooks.colearn_finalize import CoLearnFinalizeHook
    from colearn.colearn_hooks.colearn_preflight import CoLearnPreflightHook
    from colearn.colearn_hooks.colearn_session_binder import SessionBinderHook
    from colearn.colearn_plugin import CoLearnPlugin

    hooks = CoLearnPlugin().get_hooks()

    assert len(hooks) == 4
    assert isinstance(hooks[0], SessionBinderHook)
    assert isinstance(hooks[1], CoLearnPreflightHook)
    assert isinstance(hooks[2], BlackboardMonitorHook)
    assert isinstance(hooks[3], CoLearnFinalizeHook)


def test_plugin_get_tools():
    """CoLearnPlugin should expose colearn tool metadata."""
    from colearn.colearn_plugin import CoLearnPlugin
    from colearn.colearn_tools.colearn_command import TOOL_METADATA

    tools = CoLearnPlugin().get_tools()

    assert tools == [TOOL_METADATA]
    assert tools[0]["name"] == "colearn"
    assert tools[0]["command"] == "/colearn"
    assert callable(tools[0]["handler"])


def test_setup_session(tmp_path):
    """CoLearnPlugin.setup_session should set ContextVar and create session state."""
    from colearn.colearn_context import get_current_session_id
    from colearn.colearn_plugin import CoLearnPlugin

    plugin = CoLearnPlugin({"state_root": str(tmp_path / "sessions")})
    session = plugin.setup_session("smoke-session")

    assert get_current_session_id() == "smoke-session"
    assert session.session_id == "smoke-session"


def test_nanobot_adapter_build_install_plan():
    """NanoBotAdapter should expose explicit install surfaces without mutating host internals."""
    from colearn.colearn_adapters.nanobot_adapter import NanoBotAdapter
    from colearn.colearn_plugin import CoLearnPlugin

    plan = NanoBotAdapter(CoLearnPlugin()).build_install_plan()

    assert len(plan.hooks) == 4
    assert plan.tools[0]["command"] == "/colearn"
    assert any(ext["id"] == "colearn.knowledge-graph" for ext in plan.ui_extensions)


def test_tool_registry_adapter_registers_dict_registry():
    """ToolRegistryAdapter should explicitly register tools into dict-like registries."""
    from colearn.colearn_adapters.colearn_tool_registry import ToolRegistryAdapter
    from colearn.colearn_tools.colearn_command import TOOL_METADATA, colearn_command

    registry = {}
    ToolRegistryAdapter(registry).register(TOOL_METADATA)

    assert registry["/colearn"] == TOOL_METADATA
    assert registry["/colearn"]["handler"] == colearn_command
    assert callable(registry["/colearn"]["snapshot_handler"])


def test_ui_extension_registry():
    """UI extension registry should expose fixed-slot manifests."""
    from colearn.colearn_adapters.colearn_ui_extensions import UIExtensionRegistry

    registry = UIExtensionRegistry()

    assert registry.resolve("colearn.knowledge-graph")["container"] == "graph"
    assert any(ext["slot"] == "apps" for ext in registry.list("apps"))


def test_pyproject_entry_points():
    """pyproject.toml should register CoLearn as a NanoBot tool entry point."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    content = pyproject.read_text()

    assert '[project.entry-points."nanobot.tools"]' in content
    assert 'colearn = "colearn.colearn_tools.colearn_command:TOOL_METADATA"' in content
    assert "nanobot.plugins" not in content
    assert "nanobot.channels" not in content
