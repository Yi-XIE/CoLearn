"""CoLearn slash command tool - structured blackboard snapshot and dashboard."""
from datetime import datetime
from typing import Any

from colearn.colearn_context import get_current_session_id, get_session


def format_timestamp(ts: int) -> str:
    """Format Unix timestamp to human-readable string."""
    if ts == 0:
        return "Never"
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def colearn_snapshot() -> dict[str, Any]:
    """Return a structured snapshot of the current CoLearn blackboard."""
    session_id = get_current_session_id()
    if not session_id:
        return {"ok": False, "error": "No active CoLearn session found."}

    session = get_session()
    if not session:
        return {"ok": False, "error": f"Session `{session_id}` not found in state store."}

    learning = session.blackboard.learning
    runtime = session.blackboard.runtime
    session_mode = "LEARNING" if learning.goal else "CHAT"
    turn_mode = None
    if session_mode == "LEARNING":
        if learning.pending_checks:
            turn_mode = "CHECK"
        elif learning.blockers or learning.objections:
            turn_mode = "PAUSED"
        else:
            turn_mode = "LEARN"

    return {
        "ok": True,
        "session_id": session_id,
        "session_mode": session_mode,
        "turn_mode": turn_mode,
        "runtime": {
            "current_task_status": runtime.current_task_status,
            "last_update_ts": runtime.last_update_ts,
            "last_update": format_timestamp(runtime.last_update_ts),
            "last_observed_ip": runtime.last_observed_ip,
            "active_blind_spots": list(runtime.active_blind_spots),
        },
        "learning": {
            "goal": learning.goal,
            "active_node_id": learning.active_node_id,
            "current_progress": learning.current_progress,
            "planned_nodes": list(learning.planned_nodes),
            "completed_nodes": list(learning.completed_nodes),
            "blockers": list(learning.blockers),
            "objections": list(learning.objections),
            "evidence_refs": list(learning.evidence_refs),
            "continuation": learning.continuation,
            "pending_checks": list(learning.pending_checks),
            "recall_plan": learning.recall_plan,
        },
        "updated_at": session.updated_at,
    }


def render_colearn_markdown(snapshot: dict[str, Any]) -> str:
    """Render a structured snapshot as a Markdown dashboard."""
    if not snapshot.get("ok"):
        return f"⚠️ {snapshot.get('error', 'Unknown CoLearn error')}"

    runtime = snapshot["runtime"]
    learning = snapshot["learning"]
    lines = [
        "# CoLearn Dashboard",
        "",
        f"**Session ID**: `{snapshot['session_id']}`",
        "",
        "## Mode & Status",
        "",
        f"- **Session Mode**: {snapshot['session_mode']}",
        f"- **Turn Mode**: {snapshot.get('turn_mode') or 'N/A'}",
        f"- **Runtime Status**: `{runtime['current_task_status']}`",
        f"- **Last Update**: {runtime['last_update']}",
    ]

    if runtime.get("last_observed_ip"):
        lines.append(f"- **Last Observed IP**: `{runtime['last_observed_ip']}`")
    lines.append("")

    if learning.get("goal"):
        lines.extend(["## Learning Goal", "", str(learning["goal"]), ""])
        if learning.get("active_node_id"):
            lines.extend(["## Active Node", "", f"`{learning['active_node_id']}`", ""])
        if learning.get("current_progress"):
            lines.extend(["## Progress", "", str(learning["current_progress"]), ""])
        for title, key, prefix in [
            ("Planned Nodes", "planned_nodes", "-"),
            ("Completed Nodes", "completed_nodes", "- ✓"),
            ("Blockers", "blockers", "- 🚫"),
            ("Objections", "objections", "- 💬"),
            ("Pending Checks", "pending_checks", "- ⏳"),
        ]:
            values = learning.get(key) or []
            if values:
                lines.extend([f"## {title}", ""])
                for value in values:
                    if key.endswith("nodes"):
                        lines.append(f"{prefix} `{value}`")
                    else:
                        lines.append(f"{prefix} {value}")
                lines.append("")
        if learning.get("continuation"):
            lines.extend(["## Next Steps", "", str(learning["continuation"]), ""])
    else:
        lines.extend(
            [
                "## Learning Status",
                "",
                "Currently in **CHAT** mode. No active learning goal set.",
                "",
                "Use `/learn` or start a learning session to enter **LEARNING** mode.",
                "",
            ]
        )

    blind_spots = runtime.get("active_blind_spots") or []
    if blind_spots:
        lines.extend(["## Active Blind Spots", ""])
        for spot in blind_spots:
            lines.append(f"- 👁️ {spot}")
        lines.append("")

    lines.extend(["---", "", f"*Updated: {snapshot['updated_at']}*"])
    return "\n".join(lines)


def colearn_command() -> str:
    """Generate a Markdown dashboard showing current blackboard state."""
    return render_colearn_markdown(colearn_snapshot())


TOOL_METADATA = {
    "name": "colearn",
    "description": "Display CoLearn blackboard dashboard showing learning progress, goals, and runtime status",
    "command": "/colearn",
    "handler": colearn_command,
    "snapshot_handler": colearn_snapshot,
}
