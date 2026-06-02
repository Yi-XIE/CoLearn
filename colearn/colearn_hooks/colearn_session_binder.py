"""Hook that binds the current NanoBot turn to a CoLearn session id."""
from __future__ import annotations

from typing import Any

from colearn.colearn_context import set_current_session_id, set_session_store
from colearn.colearn_hooks.colearn_hook_base import AgentHook, AgentHookContext
from colearn.colearn_state.colearn_store import SessionStore


class SessionBinderHook(AgentHook):
    """Resolve host context to a stable CoLearn session id before each turn."""

    def __init__(self, session_store: SessionStore | None = None, reraise: bool = False) -> None:
        super().__init__(reraise=reraise)
        self.session_store = session_store or SessionStore()

    async def before_iteration(self, context: AgentHookContext) -> None:
        try:
            session_id = resolve_session_id(context)
            set_current_session_id(session_id)
            set_session_store(self.session_store)
            if self.session_store.load(session_id) is None:
                self.session_store.save(self.session_store.create_session(session_id))
        except Exception:
            if self._reraise:
                raise


def resolve_session_id(context: AgentHookContext | dict[str, Any]) -> str:
    """Resolve a session id from hook context, dict context, or fallback."""
    if isinstance(context, dict):
        return str(context.get("session_id") or context.get("session_key") or context.get("user_id") or "default")
    for attr in ("session_id", "session_key", "user_id"):
        value = getattr(context, attr, None)
        if value:
            return str(value)
    return "default"
