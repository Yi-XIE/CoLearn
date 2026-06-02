"""CoLearn startup integration for a NanoBot host.

Usage in your own launcher (e.g. run_colearn.py)::

    import asyncio
    from nanobot import Nanobot
    from nanobot.agent.loop import AgentLoop
    from colearn.colearn_runtime import install_colearn

    # Build the host loop however you normally do:
    bot = Nanobot.from_config("~/.nanobot/config.json")
    install_colearn(bot)                       # attach hooks + /colearn tool
    result = asyncio.run(bot.run("我想学机器学习", session_key="user-42"))
    print(result.content)

`install_colearn` accepts either a `Nanobot` facade, an `AgentLoop`, or any object
that exposes `_extra_hooks` (hook list) and/or `tools` (a ToolRegistry). It is
idempotent: calling it twice will not double-register the CoLearn tool or hooks.
"""
from __future__ import annotations

from typing import Any

from colearn.colearn_adapters.colearn_tool_registry import ToolRegistryAdapter
from colearn.colearn_plugin import CoLearnPlugin
from colearn.colearn_tools.colearn_command import TOOL_METADATA

_COLEARN_INSTALLED_FLAG = "_colearn_installed"


def _resolve_loop(host: Any) -> Any:
    """Return the underlying AgentLoop-like object from a Nanobot facade or loop."""
    loop = getattr(host, "_loop", None)
    return loop if loop is not None else host


def install_colearn(host: Any, plugin: CoLearnPlugin | None = None) -> CoLearnPlugin:
    """Attach CoLearn hooks and the /colearn tool to a NanoBot host.

    Args:
        host: A `Nanobot` facade, an `AgentLoop`, or a compatible object exposing
            `_extra_hooks` and/or `tools`.
        plugin: Optional pre-configured CoLearnPlugin. A default one is created
            when omitted.

    Returns:
        The CoLearnPlugin instance that was installed.
    """
    plugin = plugin or CoLearnPlugin()
    loop = _resolve_loop(host)

    if getattr(loop, _COLEARN_INSTALLED_FLAG, False):
        return plugin

    _install_hooks(loop, plugin)
    _install_tools(loop, plugin)

    try:
        setattr(loop, _COLEARN_INSTALLED_FLAG, True)
    except Exception:
        pass
    return plugin


def _install_hooks(loop: Any, plugin: CoLearnPlugin) -> None:
    """Append CoLearn resident hooks to the host's extra-hook list."""
    hooks = list(plugin.get_hooks())
    existing = getattr(loop, "_extra_hooks", None)
    if existing is None:
        try:
            loop._extra_hooks = list(hooks)
        except Exception:
            return
        return
    existing_types = {type(h) for h in existing}
    for hook in hooks:
        if type(hook) not in existing_types:
            existing.append(hook)


def _install_tools(loop: Any, plugin: CoLearnPlugin) -> None:
    """Explicitly register CoLearn tools into the host tool registry."""
    registry = getattr(loop, "tools", None)
    if registry is None:
        return
    has = getattr(registry, "has", None)
    if callable(has) and has(TOOL_METADATA["name"]):
        return
    ToolRegistryAdapter(registry).register(TOOL_METADATA)
