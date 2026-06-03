"""CoLearn learning-mode command helpers and tool metadata."""
from __future__ import annotations

from typing import Any

from colearn.colearn_context import get_current_session_id, get_session_store, save_session
from colearn.colearn_state.colearn_models import LearningSession


def _ensure_session() -> LearningSession:
    session_id = get_current_session_id() or "default"
    store = get_session_store()
    session = store.load(session_id)
    if session is None:
        session = store.create_session(session_id)
    return session


def _normalize_lines(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def learn_snapshot(
    goal: str,
    active_node_id: str | None = None,
    action: str = "start",
) -> dict[str, Any]:
    """Create/update the current learning session and return a structured result."""
    clean_goal = goal.strip()
    if not clean_goal:
        raise ValueError("goal is required")

    clean_action = (action or "start").strip().lower()
    if clean_action not in {"start", "continue"}:
        raise ValueError("action must be 'start' or 'continue'")

    session = _ensure_session()
    learning = session.blackboard.learning
    learning.goal = clean_goal
    if active_node_id:
        learning.active_node_id = active_node_id.strip() or None
    if clean_action == "start":
        learning.current_progress = ""
        learning.pending_checks = []
        learning.blockers = []
        learning.objections = []
        learning.continuation = "继续当前学习路径，围绕当前目标推进。"
    elif not learning.continuation:
        learning.continuation = "继续当前学习路径。"

    if learning.active_node_id and learning.active_node_id not in learning.planned_nodes:
        learning.planned_nodes.append(learning.active_node_id)

    save_session(session)
    return {
        "ok": True,
        "session_id": session.session_id,
        "session_mode": "LEARNING",
        "action": clean_action,
        "goal": learning.goal,
        "active_node_id": learning.active_node_id,
        "continuation": learning.continuation,
    }


def render_learn_markdown(result: dict[str, Any]) -> str:
    """Render a `/learn` result as Markdown."""
    if not result.get("ok"):
        return f"⚠️ {result.get('error', 'Unknown CoLearn error')}"

    lines = [
        "# CoLearn Learning Session",
        "",
        f"**Session ID**: `{result['session_id']}`",
        f"**Mode**: {result['session_mode']}",
        f"**Action**: {result['action']}",
        "",
        "## Goal",
        "",
        str(result["goal"]),
        "",
    ]
    if result.get("active_node_id"):
        lines.extend(["## Active Node", "", f"`{result['active_node_id']}`", ""])
    if result.get("continuation"):
        lines.extend(["## Next Step", "", str(result["continuation"]), ""])
    return "\n".join(lines)


def learn_command(
    goal: str,
    active_node_id: str | None = None,
    action: str = "start",
) -> str:
    """Create/update LEARNING mode for the current CoLearn session."""
    return render_learn_markdown(learn_snapshot(goal, active_node_id, action))


LEARN_TOOL_METADATA = {
    "name": "learn",
    "description": "Enter CoLearn learning mode for the current session and set the active learning goal",
    "command": "/learn",
    "title": "Start CoLearn learning mode",
    "icon": "graduation-cap",
    "arg_hint": "<goal>",
    "handler": learn_command,
    "snapshot_handler": learn_snapshot,
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "The learning goal to pursue in this session",
            },
            "active_node_id": {
                "type": ["string", "null"],
                "description": "Optional Wiki node id to focus the learning session",
            },
            "action": {
                "type": "string",
                "enum": ["start", "continue"],
                "description": "Whether to start a fresh learning thread or continue the current one",
            },
        },
        "required": ["goal"],
        "additionalProperties": False,
    },
}
