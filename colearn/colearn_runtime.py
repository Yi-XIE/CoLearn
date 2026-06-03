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
_COLEARN_INSTALLED_FLAG = "_colearn_installed"
_ACTIVE_PLUGIN: CoLearnPlugin | None = None


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
    global _ACTIVE_PLUGIN
    plugin = plugin or CoLearnPlugin()
    _ACTIVE_PLUGIN = plugin
    loop = _resolve_loop(host)

    if getattr(loop, _COLEARN_INSTALLED_FLAG, False):
        return plugin

    _install_hooks(loop, plugin)
    _install_tools(loop, plugin)
    _install_runtime_metadata(loop, plugin)

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
    adapter = ToolRegistryAdapter(registry)
    has = getattr(registry, "has", None)
    for tool in plugin.get_tools():
        name = str(tool.get("name") or "").strip()
        if callable(has) and name and has(name):
            continue
        adapter.register(tool)


def _install_runtime_metadata(loop: Any, plugin: CoLearnPlugin) -> None:
    """Expose the installed plugin instance and config to host-side adapters."""
    payload = plugin.host_runtime_payload()
    for attr, value in {
        "_colearn_plugin": plugin,
        "_colearn_runtime": payload,
        "_colearn_session_store": plugin.session_store,
        "_colearn_wiki_service": plugin.wiki_service,
    }.items():
        try:
            setattr(loop, attr, value)
        except Exception:
            continue


_PATCHED_FROM_CONFIG_FLAG = "_colearn_patched_from_config"


def enable_for_nanobot(plugin: CoLearnPlugin | None = None) -> CoLearnPlugin:
    """Patch ``AgentLoop.from_config`` so every loop NanoBot builds gets CoLearn.

    Use this before invoking the NanoBot CLI (``serve``, ``gateway``, ``agent``)
    so the WebUI, HTTP API, and CLI all run with CoLearn already installed. The
    patch is idempotent; calling this twice is a no-op.

    Returns the shared CoLearnPlugin instance the patched factory will install.
    """
    from nanobot.agent.loop import AgentLoop

    if getattr(AgentLoop.from_config, _PATCHED_FROM_CONFIG_FLAG, False):
        return getattr(AgentLoop.from_config, "_colearn_plugin")

    global _ACTIVE_PLUGIN
    shared_plugin = plugin or CoLearnPlugin()
    _ACTIVE_PLUGIN = shared_plugin
    original = AgentLoop.from_config

    def patched_from_config(*args: Any, **kwargs: Any) -> Any:
        loop = original(*args, **kwargs)
        try:
            install_colearn(loop, plugin=shared_plugin)
        except Exception:
            # Never break NanoBot startup if CoLearn install hits a snag.
            pass
        return loop

    setattr(patched_from_config, _PATCHED_FROM_CONFIG_FLAG, True)
    setattr(patched_from_config, "_colearn_plugin", shared_plugin)
    AgentLoop.from_config = patched_from_config  # type: ignore[method-assign]
    return shared_plugin


def get_active_colearn_plugin() -> CoLearnPlugin | None:
    """Return the last plugin installed or prepared for NanoBot startup."""
    return _ACTIVE_PLUGIN

