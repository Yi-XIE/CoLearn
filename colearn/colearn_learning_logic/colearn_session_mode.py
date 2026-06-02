"""
Session Mode and Turn Mode Routing for CoLearn

Implements the mode routing logic defined in 01-技术设计.md section 5.2:
- SessionMode: CHAT | LEARNING
- TurnMode: LEARN | CHECK | PAUSED (only in LEARNING mode)
- LearningPhase: INTAKE | DIAGNOSE | READY | REFLECT | RECALL
"""

from enum import Enum
from typing import Any


class SessionMode(str, Enum):
    """
    Session-level mode determining whether CoLearn learning chain is active.

    CHAT: Regular conversation, CoLearn plugin operates in lightweight mode
    LEARNING: Active learning session, full CoLearn chain is engaged
    """
    CHAT = "CHAT"
    LEARNING = "LEARNING"


class TurnMode(str, Enum):
    """
    Turn-level mode within LEARNING sessions.

    LEARN: Teaching/explaining mode
    CHECK: Assessment/verification mode
    PAUSED: Learning temporarily suspended (e.g., clarification needed)
    """
    LEARN = "LEARN"
    CHECK = "CHECK"
    PAUSED = "PAUSED"


class LearningPhase(str, Enum):
    """
    Learning flow phase within LEARNING sessions.

    INTAKE: Collecting learning goal and initial context
    DIAGNOSE: Assessing current knowledge level
    READY: Ready to proceed with learning
    REFLECT: Reviewing and consolidating learned material
    RECALL: Revisiting previously learned concepts
    """
    INTAKE = "INTAKE"
    DIAGNOSE = "DIAGNOSE"
    READY = "READY"
    REFLECT = "REFLECT"
    RECALL = "RECALL"


def route_session_mode(session: dict[str, Any]) -> SessionMode:
    """
    Determine the session mode based on session state.

    Logic per 01-技术设计.md section 5.4:
    1. If no active learning goal -> CHAT
    2. If learning goal is set -> LEARNING
    3. Session stickiness: once in LEARNING, stays in LEARNING unless explicitly exited

    Args:
        session: Session state dictionary containing blackboard and other state

    Returns:
        SessionMode.CHAT or SessionMode.LEARNING
    """
    # Extract blackboard.learning
    blackboard = session.get("blackboard", {})
    learning = blackboard.get("learning", {})

    # Check for active learning goal
    goal = learning.get("goal")

    # If goal is set and not empty, we're in LEARNING mode
    if goal:
        return SessionMode.LEARNING

    # Otherwise, we're in CHAT mode
    return SessionMode.CHAT


def route_turn_mode(session: dict[str, Any]) -> TurnMode | None:
    """
    Determine the turn mode within a LEARNING session.

    Returns None if session is in CHAT mode (TurnMode only applies to LEARNING).

    Logic per 01-技术设计.md section 5.2-5.3:
    - Based on blackboard.learning state
    - pending_checks indicates CHECK mode
    - blockers/objections indicate PAUSED mode
    - Otherwise, LEARN mode

    Args:
        session: Session state dictionary containing blackboard and other state

    Returns:
        TurnMode or None (None if not in LEARNING mode)
    """
    # First check if we're in LEARNING mode
    if route_session_mode(session) != SessionMode.LEARNING:
        return None

    # Extract blackboard.learning
    blackboard = session.get("blackboard", {})
    learning = blackboard.get("learning", {})

    # Check for pending checks
    pending_checks = learning.get("pending_checks", [])
    if pending_checks:
        return TurnMode.CHECK

    # Check for blockers or objections
    blockers = learning.get("blockers", [])
    objections = learning.get("objections", [])
    if blockers or objections:
        return TurnMode.PAUSED

    # Default to LEARN mode
    return TurnMode.LEARN
