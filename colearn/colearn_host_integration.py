"""Minimal NanoBot host integration helpers for CoLearn Demo wiring."""
from __future__ import annotations

from typing import Any

from nanobot.apps.protocol import app_manifest
from nanobot.bus.events import OutboundMessage

from colearn.colearn_api import blackboard_payload, current_session_payload, graph_payload
from colearn.colearn_context import set_current_session_id, set_session_store
from colearn.colearn_plugin import CoLearnPlugin
from colearn.colearn_runtime import get_active_colearn_plugin
from colearn.colearn_tools.colearn_command import colearn_command
from colearn.colearn_tools.learn_command import learn_command


def _runtime_payload(loop: Any) -> dict[str, Any]:
    payload = getattr(loop, "_colearn_runtime", None)
    if isinstance(payload, dict):
        return payload
    plugin = getattr(loop, "_colearn_plugin", None)
    if plugin is None:
        plugin = get_active_colearn_plugin()
    if plugin is None:
        plugin = CoLearnPlugin()
        try:
            setattr(loop, "_colearn_plugin", plugin)
            setattr(loop, "_colearn_runtime", plugin.host_runtime_payload())
        except Exception:
            pass
        return plugin.host_runtime_payload()
    if isinstance(plugin, CoLearnPlugin):
        return plugin.host_runtime_payload()
    return {}


def _bind_command_session(loop: Any, key: str) -> None:
    payload = _runtime_payload(loop)
    store = payload.get("session_store")
    if store is not None:
        set_session_store(store)
    set_current_session_id(key or "default")


def _plugin(loop: Any) -> CoLearnPlugin:
    payload = _runtime_payload(loop)
    plugin = payload.get("plugin")
    return plugin if isinstance(plugin, CoLearnPlugin) else CoLearnPlugin()


def command_palette_entries() -> list[dict[str, str]]:
    """Return CoLearn slash commands for the WebUI command palette."""
    return [
        {
            "command": "/colearn",
            "title": "Show CoLearn dashboard",
            "description": "Display current CoLearn blackboard and learning status.",
            "icon": "share-2",
            "arg_hint": "",
        },
        {
            "command": "/learn",
            "title": "Enter CoLearn learning mode",
            "description": "Create or continue a CoLearn learning session with a goal.",
            "icon": "graduation-cap",
            "arg_hint": "<goal>",
        },
    ]


async def cmd_colearn(ctx: Any) -> OutboundMessage:
    """NanoBot slash command handler for `/colearn`."""
    _bind_command_session(ctx.loop, ctx.key)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=colearn_command(),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_learn(ctx: Any) -> OutboundMessage:
    """NanoBot slash command handler for `/learn`."""
    goal = (ctx.args or "").strip()
    if not goal:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Usage: /learn <goal>",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )
    _bind_command_session(ctx.loop, ctx.key)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=learn_command(goal),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def colearn_blackboard_api(loop: Any) -> dict[str, Any]:
    """Return read-only current blackboard payload for the host HTTP surface."""
    payload = _runtime_payload(loop)
    store = payload.get("session_store")
    if store is not None:
        set_session_store(store)
    return blackboard_payload()


def colearn_graph_api(loop: Any) -> dict[str, Any]:
    """Return read-only current graph payload for the host HTTP surface."""
    payload = _runtime_payload(loop)
    store = payload.get("session_store")
    wiki_service = payload.get("wiki_service")
    if store is not None:
        set_session_store(store)
    return graph_payload(wiki_service=wiki_service)


def colearn_session_api(loop: Any) -> dict[str, Any]:
    """Return lightweight current-session metadata for debugging."""
    payload = _runtime_payload(loop)
    store = payload.get("session_store")
    if store is not None:
        set_session_store(store)
    return current_session_payload()


def colearn_apps_payload(loop: Any) -> dict[str, Any]:
    """Return a read-only Apps catalog payload entry for CoLearn."""
    payload = _runtime_payload(loop)
    store = payload.get("session_store")
    wiki_service = payload.get("wiki_service")
    plugin = _plugin(loop)
    if store is not None:
        set_session_store(store)

    current = current_session_payload()
    blackboard = blackboard_payload()
    graph = graph_payload(wiki_service=wiki_service)
    manifest = app_manifest(
        app_id="colearn",
        display_name="CoLearn",
        description="Read-only learning dashboard and graph for CoLearn sessions.",
        category="learning",
        source="colearn",
        version="0.1.0-demo",
        brand_color="#2563eb",
        capabilities=[
            {
                "type": "page",
                "path": "/api/v1/colearn/graph/current",
            },
            {
                "type": "panel",
                "path": "/api/v1/colearn/blackboard/current",
            },
        ],
        install={
            "supported": False,
            "strategy": "bundled",
            "verification": [
                "python run_colearn.py webui --port 8080",
                "Open Settings > Apps > CoLearn",
            ],
        },
        remove={
            "supported": False,
            "strategy": "bundled",
        },
        trust={
            "registry": "colearn",
            "level": "first_party",
            "review_status": "demo",
        },
    )
    app = {
        "name": "colearn",
        "display_name": "CoLearn",
        "category": "learning",
        "description": "Read-only CoLearn blackboard and graph view.",
        "requires": "run_colearn.py webui",
        "source": "colearn",
        "entry_point": "run_colearn.py",
        "install_supported": False,
        "installed": True,
        "available": True,
        "status": "installed",
        "logo_url": None,
        "brand_color": "#2563eb",
        "skill_installed": True,
        "manifest": manifest,
        "read_only": True,
        "session_mode": current.get("session_mode", "CHAT"),
        "session_id": current.get("session_id"),
        "state_root": current.get("state_root"),
        "blackboard_endpoint": "/api/v1/colearn/blackboard/current",
        "graph_endpoint": "/api/v1/colearn/graph/current",
        "session_endpoint": "/api/v1/colearn/session/current",
        "blackboard": blackboard,
        "graph": graph,
        "ui_extensions": plugin.list_ui_extensions(),
    }
    return {
        "apps": [app],
        "installed_count": 1,
        "catalog_updated_at": current.get("updated_at"),
    }
