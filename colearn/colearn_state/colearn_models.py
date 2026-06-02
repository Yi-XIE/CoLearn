"""CoLearn session state data models."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class BlackboardLearning:
    """Learning domain of the blackboard (only in LEARNING mode)."""

    goal: str | None = None
    active_node_id: str | None = None
    current_progress: str = ""
    planned_nodes: list[str] = field(default_factory=list)
    completed_nodes: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    objections: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    continuation: str = ""
    pending_checks: list[str] = field(default_factory=list)
    recall_plan: dict[str, Any] | None = None


@dataclass
class BlackboardRuntime:
    """Runtime domain of the blackboard (always present)."""

    current_task_status: str = "IDLE"  # IDLE / RUNNING / PAUSED / ERROR
    last_observed_ip: str | None = None
    active_blind_spots: list[str] = field(default_factory=list)
    last_update_ts: int = 0  # Unix timestamp


@dataclass
class Blackboard:
    """Dual-domain blackboard structure."""

    learning: BlackboardLearning = field(default_factory=BlackboardLearning)
    runtime: BlackboardRuntime = field(default_factory=BlackboardRuntime)


@dataclass
class LearningSession:
    """Complete session state structure."""

    session_id: str
    profile: dict[str, Any] = field(default_factory=dict)
    board_facts: dict[str, Any] = field(default_factory=dict)
    blackboard: Blackboard = field(default_factory=Blackboard)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "session_id": self.session_id,
            "profile": self.profile,
            "board_facts": self.board_facts,
            "blackboard": {
                "learning": self.blackboard.learning.__dict__,
                "runtime": self.blackboard.runtime.__dict__,
            },
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearningSession":
        """Create LearningSession from dict."""
        blackboard_data = data.get("blackboard", {})
        learning_data = blackboard_data.get("learning", {})
        runtime_data = blackboard_data.get("runtime", {})

        blackboard = Blackboard(
            learning=BlackboardLearning(**learning_data),
            runtime=BlackboardRuntime(**runtime_data),
        )

        return cls(
            session_id=data["session_id"],
            profile=data.get("profile", {}),
            board_facts=data.get("board_facts", {}),
            blackboard=blackboard,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
