"""Tests for SessionMode and TurnMode routing logic."""
import pytest

from colearn.colearn_learning_logic.colearn_session_mode import (
    SessionMode,
    TurnMode,
    route_session_mode,
    route_turn_mode,
)
from colearn.colearn_learning_logic.colearn_mode_router import ModeRouter


def test_route_session_mode_chat_when_no_goal():
    """SessionMode should be CHAT when no learning goal is set."""
    session = {
        "blackboard": {
            "learning": {"goal": None},
            "runtime": {},
        }
    }
    assert route_session_mode(session) == SessionMode.CHAT


def test_route_session_mode_learning_when_goal_set():
    """SessionMode should be LEARNING when a learning goal exists."""
    session = {
        "blackboard": {
            "learning": {"goal": "学习机器学习基础"},
            "runtime": {},
        }
    }
    assert route_session_mode(session) == SessionMode.LEARNING


def test_route_turn_mode_returns_none_in_chat():
    """TurnMode should return None when in CHAT mode."""
    session = {
        "blackboard": {
            "learning": {"goal": None},
            "runtime": {},
        }
    }
    assert route_turn_mode(session) is None


def test_route_turn_mode_check_when_pending_checks():
    """TurnMode should be CHECK when pending_checks exist."""
    session = {
        "blackboard": {
            "learning": {
                "goal": "学习机器学习基础",
                "pending_checks": ["验证模型理解"],
                "blockers": [],
                "objections": [],
            },
            "runtime": {},
        }
    }
    assert route_turn_mode(session) == TurnMode.CHECK


def test_route_turn_mode_paused_when_blockers():
    """TurnMode should be PAUSED when blockers exist."""
    session = {
        "blackboard": {
            "learning": {
                "goal": "学习机器学习基础",
                "pending_checks": [],
                "blockers": ["需要先理解数据概念"],
                "objections": [],
            },
            "runtime": {},
        }
    }
    assert route_turn_mode(session) == TurnMode.PAUSED


def test_route_turn_mode_paused_when_objections():
    """TurnMode should be PAUSED when objections exist."""
    session = {
        "blackboard": {
            "learning": {
                "goal": "学习机器学习基础",
                "pending_checks": [],
                "blockers": [],
                "objections": ["我不理解这个例子"],
            },
            "runtime": {},
        }
    }
    assert route_turn_mode(session) == TurnMode.PAUSED


def test_route_turn_mode_learn_by_default():
    """TurnMode should be LEARN when no blockers/checks/objections."""
    session = {
        "blackboard": {
            "learning": {
                "goal": "学习机器学习基础",
                "pending_checks": [],
                "blockers": [],
                "objections": [],
            },
            "runtime": {},
        }
    }
    assert route_turn_mode(session) == TurnMode.LEARN


def test_mode_router_decide_session_mode():
    """ModeRouter should correctly decide session mode."""
    session = {
        "blackboard": {
            "learning": {"goal": "学习物理"},
            "runtime": {},
        }
    }
    router = ModeRouter(session)
    assert router.decide_session_mode() == SessionMode.LEARNING
    assert router.is_learning_active() is True


def test_mode_router_get_active_goal():
    """ModeRouter should retrieve the active learning goal."""
    session = {
        "blackboard": {
            "learning": {"goal": "学习物理"},
            "runtime": {},
        }
    }
    router = ModeRouter(session)
    assert router.get_active_goal() == "学习物理"


def test_mode_router_decide_turn_mode():
    """ModeRouter should correctly decide turn mode."""
    session = {
        "blackboard": {
            "learning": {
                "goal": "学习物理",
                "pending_checks": ["检查理解"],
                "blockers": [],
                "objections": [],
            },
            "runtime": {},
        }
    }
    router = ModeRouter(session)
    assert router.decide_turn_mode() == TurnMode.CHECK
