"""
Mode Router for CoLearn Learning Logic

Encapsulates mode decision logic in a class-based interface.
Implements routing logic per 01-技术设计.md section 5.2.
"""

from typing import Any

from colearn.colearn_learning_logic.colearn_session_mode import (
    SessionMode,
    TurnMode,
    route_session_mode,
    route_turn_mode,
)


class ModeRouter:
    """
    Encapsulates mode routing decisions for CoLearn learning sessions.

    Provides a class-based interface for determining SessionMode and TurnMode
    based on session state and blackboard data.
    """

    def __init__(self, session: dict[str, Any]):
        """
        Initialize ModeRouter with session state.

        Args:
            session: Session state dictionary containing blackboard and other state
        """
        self.session = session

    def decide_session_mode(self) -> SessionMode:
        """
        Decide the current session mode.

        Logic per 01-技术设计.md section 5.4:
        - SessionMode.CHAT if no active learning goal
        - SessionMode.LEARNING if goal is set

        Returns:
            SessionMode.CHAT or SessionMode.LEARNING
        """
        return route_session_mode(self.session)

    def decide_turn_mode(self) -> TurnMode | None:
        """
        Decide the current turn mode within a LEARNING session.

        Returns None if session is in CHAT mode (TurnMode only applies to LEARNING).

        Logic per 01-技术设计.md section 5.2-5.3:
        - Based on blackboard.learning state
        - TurnMode.CHECK if pending_checks exist
        - TurnMode.PAUSED if blockers or objections exist
        - TurnMode.LEARN otherwise

        Returns:
            TurnMode or None (None if not in LEARNING mode)
        """
        return route_turn_mode(self.session)

    def get_learning_phase(self) -> str | None:
        """
        Get the current learning phase from blackboard.learning.

        Returns:
            Learning phase string or None if not set
        """
        blackboard = self.session.get("blackboard", {})
        learning = blackboard.get("learning", {})
        return learning.get("phase")

    def is_learning_active(self) -> bool:
        """
        Check if learning mode is currently active.

        Returns:
            True if SessionMode is LEARNING, False otherwise
        """
        return self.decide_session_mode() == SessionMode.LEARNING

    def get_active_goal(self) -> str | None:
        """
        Get the current active learning goal.

        Returns:
            Learning goal string or None if not set
        """
        blackboard = self.session.get("blackboard", {})
        learning = blackboard.get("learning", {})
        return learning.get("goal")
