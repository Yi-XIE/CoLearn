"""CoLearn session state store - atomic file I/O."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote

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

    @staticmethod
    def _session_dir_name(session_id: str) -> str:
        """Map a session id to a filesystem-safe directory name."""
        safe = quote(session_id, safe="")
        if safe == session_id and safe not in {"", ".", ".."}:
            return session_id
        return f"sid~{safe}"

    @staticmethod
    def _decode_session_dir_name(dir_name: str) -> str:
        """Recover a logical session id from an encoded directory name."""
        if dir_name.startswith("sid~"):
            return unquote(dir_name[4:])
        return dir_name

    def _session_dir(self, session_id: str) -> Path:
        """Get the directory path for a session."""
        encoded = self._session_dir_name(session_id)
        encoded_path = self.state_root / encoded
        legacy_path = self.state_root / session_id
        if encoded != session_id and legacy_path.exists() and not encoded_path.exists():
            return legacy_path
        return encoded_path

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
        2. Replace session.json atomically when the platform supports it
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

            # Replace the destination in-place so repeated saves also work on Windows.
            os.replace(temp_file, session_file)

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
                    sessions.append(self._decode_session_dir_name(item.name))

        return sorted(sessions)

    def latest_session(self, prefer_learning: bool = False) -> LearningSession | None:
        """Return the most recently updated session.

        When ``prefer_learning`` is enabled, sessions with an active learning
        goal are preferred; within that pool the newest ``updated_at`` wins.
        """
        loaded: list[LearningSession] = []
        for session_id in self.list_sessions():
            session = self.load(session_id)
            if session is not None:
                loaded.append(session)
        if not loaded:
            return None

        pool = loaded
        if prefer_learning:
            learning_sessions = [
                session for session in loaded if session.blackboard.learning.goal
            ]
            if learning_sessions:
                pool = learning_sessions

        return max(
            pool,
            key=lambda session: (
                session.updated_at or "",
                session.session_id,
            ),
        )

    def latest_session_id(self, prefer_learning: bool = False) -> str | None:
        """Return the session id chosen by :meth:`latest_session`."""
        session = self.latest_session(prefer_learning=prefer_learning)
        return session.session_id if session is not None else None
