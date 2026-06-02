"""NanoBot session mirror adapter.

CoLearn state remains in `.colearn/state/...`; this adapter only reads and writes
the host session mirror layer.
"""
from __future__ import annotations

from typing import Any


class HostSessionAdapter:
    """Adapter around NanoBot's SessionManager-like object."""

    def __init__(self, session_manager: Any) -> None:
        self.session_manager = session_manager

    def get_or_create(self, key: str) -> Any:
        """Return an existing host session or create one through the host manager."""
        return self.session_manager.get_or_create(key)

    def save(self, session: Any, *, fsync: bool = False) -> None:
        """Persist the host session mirror if the host exposes save()."""
        save = getattr(self.session_manager, "save", None)
        if callable(save):
            save(session, fsync=fsync)


def project_colearn_session_metadata(host_session: Any, colearn_session_id: str) -> None:
    """Mirror the active CoLearn session id into host metadata without making it truth."""
    metadata = getattr(host_session, "metadata", None)
    if metadata is None:
        metadata = {}
        setattr(host_session, "metadata", metadata)
    metadata["colearn_session_id"] = colearn_session_id
