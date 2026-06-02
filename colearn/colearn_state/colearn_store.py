"""CoLearn session state store - atomic file I/O."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from colearn.colearn_state.colearn_models import LearningSession


class SessionStore:
    """Manages session.json files with atomic writes."""

    def __init__(self, state_root: Path | str = ".colearn/state/sessions"):
        """
        Initialize session store.

        Args:
            state_root: Root directory for session state files
        """
        self.state_root = Path(state_root)

    def _session_dir(self, session_id: str) -> Path:
        """Get the directory path for a session."""
        return self.state_root / session_id

    def _session_file(self, session_id: str) -> Path:
        """Get the session.json file path."""
        return self._session_dir(session_id) / "session.json"

    def _temp_file(self, session_id: str) -> Path:
        """Get the temporary file path for atomic writes."""
        return self._session_dir(session_id) / ".session.json.tmp"

    def create_session(self, session_id: str) -> LearningSession:
        """
        Create a new session with initialized blackboard.

        Args:
            session_id: Unique session identifier

        Returns:
            New LearningSession object with dual-domain blackboard
        """
        session = LearningSession(session_id=session_id)
        return session

    def load(self, session_id: str) -> LearningSession | None:
        """
        Load a session from disk.

        Args:
            session_id: Session identifier

        Returns:
            LearningSession object or None if not found
        """
        session_file = self._session_file(session_id)

        if not session_file.exists():
            return None

        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return LearningSession.from_dict(data)
        except Exception as e:
            print(f"[ERROR] Failed to load session {session_id}: {e}")
            return None

    def save(self, session: LearningSession) -> None:
        """
        Save a session to disk using atomic write.

        Implementation:
        1. Write to .session.json.tmp
        2. Rename to session.json (atomic on POSIX)
        3. Set file permissions to 0600

        Args:
            session: LearningSession to save
        """
        session_dir = self._session_dir(session.session_id)
        session_file = self._session_file(session.session_id)
        temp_file = self._temp_file(session.session_id)

        # Create session directory if needed
        session_dir.mkdir(parents=True, exist_ok=True)

        # Update timestamp
        session.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        session.blackboard.runtime.last_update_ts = int(time.time())

        # Serialize to JSON
        data = session.to_dict()

        try:
            # Write to temporary file
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename
            temp_file.rename(session_file)

            # Set file permissions to 0600 (user read/write only)
            os.chmod(session_file, 0o600)

        except Exception as e:
            # Clean up temp file if write failed
            if temp_file.exists():
                temp_file.unlink()
            raise RuntimeError(f"Failed to save session {session.session_id}: {e}") from e

    def list_sessions(self) -> list[str]:
        """
        List all session IDs.

        Returns:
            List of session IDs
        """
        if not self.state_root.exists():
            return []

        sessions = []
        for item in self.state_root.iterdir():
            if item.is_dir():
                session_file = item / "session.json"
                if session_file.exists():
                    sessions.append(item.name)

        return sorted(sessions)
