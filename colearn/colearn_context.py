"""Turn-scoped context helpers for CoLearn."""
import time
from contextvars import ContextVar
from typing import Any

from colearn.colearn_state.colearn_models import LearningSession
from colearn.colearn_state.colearn_store import SessionStore

_session_id_var: ContextVar[str | None] = ContextVar("colearn_session_id", default=None)
_session_store_var: ContextVar[SessionStore | None] = ContextVar(
    "colearn_session_store", default=None
)
_default_session_store = SessionStore()


def get_current_session_id() -> str | None:
    """Get the current session ID from ContextVar."""
    return _session_id_var.get()


def set_current_session_id(session_id: str) -> None:
    """Set the current session ID in ContextVar."""
    _session_id_var.set(session_id)


def set_session_store(session_store: SessionStore) -> None:
    """Bind the SessionStore used by this turn."""
    _session_store_var.set(session_store)


def get_session_store() -> SessionStore:
    """Return the configured turn store or the default local store."""
    return _session_store_var.get() or _default_session_store


def get_blackboard(domain: str | None = None) -> dict[str, Any] | None:
    """Get blackboard data from the current session."""
    session = get_session()
    if not session:
        return None

    blackboard_data = session.to_dict()["blackboard"]
    if domain is None:
        return blackboard_data
    return blackboard_data.get(domain, {})


def update_blackboard(domain: str, key: str, value: Any) -> None:
    """Update a key in the specified blackboard domain and persist it."""
    session_id = get_current_session_id()
    if not session_id:
        return

    store = get_session_store()
    session = store.load(session_id)
    if not session:
        session = store.create_session(session_id)

    if domain == "learning":
        setattr(session.blackboard.learning, key, value)
    elif domain == "runtime":
        setattr(session.blackboard.runtime, key, value)
        session.blackboard.runtime.last_update_ts = int(time.time())
    else:
        raise ValueError(f"Invalid blackboard domain: {domain}")

    store.save(session)


def get_session() -> LearningSession | None:
    """Get the current session object."""
    session_id = get_current_session_id()
    if not session_id:
        return None
    return get_session_store().load(session_id)


def save_session(session: LearningSession) -> None:
    """Save a session to disk."""
    get_session_store().save(session)


def bind_latest_session(prefer_learning: bool = True) -> LearningSession | None:
    """Bind the most relevant persisted session into the current turn context."""
    store = get_session_store()
    session = store.latest_session(prefer_learning=prefer_learning)
    if session is None:
        return None
    set_current_session_id(session.session_id)
    return session
