"""Smoke tests for run_colearn.py launcher."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

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
    """The launcher should expose serve / webui / run / chat parsers."""
    parser = launcher._build_parser()
    actions = {a.dest: a for a in parser._actions if a.dest == "command"}
    assert actions, "subparsers action missing"
    choices = set(actions["command"].choices.keys())
    assert {"serve", "webui", "run", "chat"}.issubset(choices)


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


def test_configure_webui_gateway_enables_local_websocket_channel(launcher):
    """webui helper should make the browser-facing websocket route available."""
    from nanobot.config.schema import Config

    config = Config()
    config.gateway.host = "0.0.0.0"
    config.gateway.port = 18790
    config.channels.__pydantic_extra__ = {
        "websocket": {"enabled": False, "path": "/ws"},
        "telegram": {"enabled": True, "token": "abc"},
    }

    resolved_port = launcher._configure_webui_gateway(config, port=18880)

    extras = config.channels.__pydantic_extra__ or {}
    assert resolved_port == 18880
    assert config.gateway.host == "127.0.0.1"
    assert config.gateway.port == 18880
    assert extras["websocket"]["enabled"] is True
    assert extras["websocket"]["host"] == "127.0.0.1"
    assert extras["websocket"]["port"] == 18880
    assert extras["websocket"]["path"] == "/ws"
    assert extras["websocket"]["allow_from"] == ["*"]
    assert extras["websocket"]["streaming"] is True
    assert extras["telegram"]["enabled"] is True


def test_cmd_webui_loads_runtime_config_and_runs_gateway(monkeypatch, launcher):
    """webui should patch Nanobot, inject websocket config, and reuse upstream gateway runtime."""
    calls: dict[str, object] = {}

    class StubConfig:
        def __init__(self) -> None:
            self.gateway = MagicMock()
            self.gateway.host = "0.0.0.0"
            self.gateway.port = 18790
            self.channels = MagicMock()
            self.channels.__pydantic_extra__ = {}

    config = StubConfig()

    def fake_enable(plugin):
        calls["plugin"] = plugin

    def fake_load_runtime_config(config_path, workspace):
        calls["load"] = (config_path, workspace)
        return config

    def fake_run_gateway(runtime_config, **kwargs):
        calls["runtime_config"] = runtime_config
        calls["run_kwargs"] = kwargs

    monkeypatch.setattr(launcher, "enable_for_nanobot", fake_enable)
    monkeypatch.setattr(launcher, "_build_plugin", lambda args: {"state_root": args.state_root})

    import nanobot.cli.commands as commands

    monkeypatch.setattr(commands, "_load_runtime_config", fake_load_runtime_config)
    monkeypatch.setattr(commands, "_run_gateway", fake_run_gateway)

    parser = launcher._build_parser()
    args = parser.parse_args(
        [
            "--config",
            "demo.json",
            "--workspace",
            "demo-workspace",
            "webui",
            "--port",
            "18880",
        ]
    )

    assert launcher.cmd_webui(args) == 0
    assert calls["load"] == ("demo.json", "demo-workspace")
    assert calls["runtime_config"] is config
    assert calls["run_kwargs"] == {"port": 18880, "health_server_enabled": False}
    extras = config.channels.__pydantic_extra__
    assert config.gateway.host == "127.0.0.1"
    assert config.gateway.port == 18880
    assert extras["websocket"]["enabled"] is True
    assert extras["websocket"]["port"] == 18880


def test_dulwich_stub_installs_minimal_gitstore_surface(launcher, tmp_path):
    """Launcher fallback should provide the dulwich bits GitStore touches at startup."""
    launcher._install_dulwich_stub()

    import dulwich.porcelain as porcelain
    from dulwich.repo import Repo

    repo_root = tmp_path / "workspace"
    porcelain.init(str(repo_root))
    porcelain.add(str(repo_root), paths=["README.md"])

    sha = porcelain.commit(str(repo_root), message=b"init")
    status = porcelain.status(str(repo_root))
    annotated = porcelain.annotate(str(repo_root), "README.md")

    assert (repo_root / ".git").is_dir()
    assert isinstance(sha, bytes)
    assert len(sha) == 20
    assert status.unstaged == []
    assert status.staged == {}
    assert annotated == []

    with Repo(str(repo_root)) as repo:
        assert repo.refs == {}
