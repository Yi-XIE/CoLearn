"""NanoBot-facing plugin entry for CoLearn."""
from pathlib import Path
from typing import Any

from colearn.colearn_adapters.colearn_ui_extensions import UIExtensionRegistry
from colearn.colearn_board.colearn_context_builder import ContextBuilder
from colearn.colearn_board.colearn_writeback import BlackboardWriter
from colearn.colearn_context import set_current_session_id, set_session_store
from colearn.colearn_hooks.colearn_blackboard_monitors import BlackboardMonitorHook
from colearn.colearn_hooks.colearn_finalize import CoLearnFinalizeHook
from colearn.colearn_hooks.colearn_preflight import CoLearnPreflightHook
from colearn.colearn_hooks.colearn_session_binder import SessionBinderHook
from colearn.colearn_state.colearn_store import SessionStore
from colearn.colearn_tools.colearn_command import TOOL_METADATA
from colearn.colearn_tools.learn_command import LEARN_TOOL_METADATA
from colearn.colearn_wiki.colearn_query import WikiQueryService


class CoLearnPlugin:
    """Plugin entrypoint for registering CoLearn hooks, tools, and UI manifests."""

    name = "colearn"
    DEFAULT_STATE_ROOT = ".colearn/state/sessions"
    DEFAULT_WIKI_INDEX_DIR = "knowledge/generated"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.session_store = SessionStore(
            self.config.get("state_root", self.DEFAULT_STATE_ROOT)
        )
        self.wiki_service = WikiQueryService(
            Path(self.config.get("wiki_index_dir", self.DEFAULT_WIKI_INDEX_DIR))
        )
        self.context_builder = ContextBuilder(self.wiki_service)
        self.blackboard_writer = BlackboardWriter()
        self.ui_extensions = UIExtensionRegistry()
        self.session_binder_hook = SessionBinderHook(self.session_store, reraise=False)
        self.preflight_hook = CoLearnPreflightHook(self.context_builder, reraise=False)
        self.blackboard_monitor_hook = BlackboardMonitorHook(reraise=False)
        self.finalize_hook = CoLearnFinalizeHook(self.blackboard_writer, reraise=False)

    def setup_session(self, session_id: str) -> Any:
        """Bind a CoLearn session ID to the current turn context and return the session."""
        set_current_session_id(session_id)
        set_session_store(self.session_store)
        session = self.session_store.load(session_id)
        if session is None:
            session = self.session_store.create_session(session_id)
            self.session_store.save(session)
        return session

    def get_hooks(self) -> list[Any]:
        """Return lifecycle hooks exported by the plugin in execution order."""
        return [
            self.session_binder_hook,
            self.preflight_hook,
            self.blackboard_monitor_hook,
            self.finalize_hook,
        ]

    def get_tools(self) -> list[dict[str, Any]]:
        """Return tool metadata exported by the plugin."""
        return [TOOL_METADATA, LEARN_TOOL_METADATA]

    def list_ui_extensions(self, slot: str | None = None) -> list[dict[str, Any]]:
        """Return CoLearn UI extension manifests for host fixed slots."""
        return self.ui_extensions.list(slot)

    def host_runtime_payload(self) -> dict[str, Any]:
        """Return host-facing runtime services and settings for NanoBot wiring."""
        return {
            "plugin": self,
            "state_root": str(self.session_store.state_root),
            "wiki_index_dir": str(self.wiki_service.index_dir),
            "wiki_service": self.wiki_service,
            "session_store": self.session_store,
        }


ColearnPlugin = CoLearnPlugin
