"""Smoke tests for run_colearn.py launcher."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "run_colearn.py"

nanobot_tools_registry = pytest.importorskip("nanobot.agent.tools.registry")
nanobot_hook = pytest.importorskip("nanobot.agent.hook")


@pytest.fixture(scope="module")
def launcher():
    spec = importlib.util.spec_from_file_location("run_colearn_launcher", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_launcher_parser_has_all_subcommands(launcher):
    """The launcher should expose serve / run / chat parsers."""
    parser = launcher._build_parser()
    actions = {a.dest: a for a in parser._actions if a.dest == "command"}
    assert actions, "subparsers action missing"
    choices = set(actions["command"].choices.keys())
    assert {"serve", "run", "chat"}.issubset(choices)


def test_launcher_parses_serve_args(launcher):
    """serve subcommand should accept host / port / timeout overrides."""
    parser = launcher._build_parser()
    args = parser.parse_args(
        ["--state-root", "/tmp/state", "serve", "--host", "127.0.0.1", "--port", "9100"]
    )
    assert args.command == "serve"
    assert args.host == "127.0.0.1"
    assert args.port == 9100
    assert args.state_root == "/tmp/state"


def test_launcher_install_path_uses_real_tool_registry(launcher, tmp_path):
    """The plugin builder + install_colearn must wire into a real ToolRegistry."""
    parser = launcher._build_parser()
    args = parser.parse_args(
        [
            "--state-root",
            str(tmp_path / "state"),
            "--wiki-index-dir",
            str(tmp_path / "generated"),
            "run",
            "--message",
            "ignored",
        ]
    )

    plugin = launcher._build_plugin(args)

    class StubLoop:
        def __init__(self):
            self._extra_hooks = []
            self.tools = nanobot_tools_registry.ToolRegistry()

    loop = StubLoop()
    launcher.install_colearn(loop, plugin=plugin)

    assert len(loop._extra_hooks) == 4
    assert all(isinstance(h, nanobot_hook.AgentHook) for h in loop._extra_hooks)
    assert loop.tools.has("colearn")
