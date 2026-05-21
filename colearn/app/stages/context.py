"""Shared state carrier for the five-stage learning turn pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from colearn.learning.state import BoardFacts
from colearn.learning.turn_contract import LearningTurnRequest
from colearn.projects.models import LearningProject
from colearn.sessions.store import LearningSession


@dataclass
class TurnContext:
    """Shared state across the 5-stage turn pipeline.

    Each stage reads what it needs and writes its outputs back here, so
    ``LearningOrchestrator.run_turn`` can stay a thin wiring layer.
    """

    # --- inputs ---------------------------------------------------------
    session_id: str
    project_id: str
    user_message: str
    language: str = "zh"
    attachments: list[dict[str, Any]] = field(default_factory=list)
    requested_skills: list[str] = field(default_factory=list)
    stream_emit: Callable[[dict[str, Any]], None] | None = None
    cancel_check: Callable[[], bool] | None = None

    # --- filled by Preflight -------------------------------------------
    session: LearningSession | None = None
    project: LearningProject | None = None
    board: BoardFacts | None = None
    snapshot: Any = None
    source_profile: dict[str, Any] = field(default_factory=dict)

    # --- filled by Retrieval -------------------------------------------
    retrieval_focus: dict[str, Any] = field(default_factory=dict)
    retrieval_reason: str = ""
    retrieval_query_context: dict[str, Any] = field(default_factory=dict)
    retrieval_bundle: Any = None
    parallel_support: dict[str, Any] = field(default_factory=dict)
    prefetched_references: list[dict[str, Any]] = field(default_factory=list)
    prompt_support_bundle: list[dict[str, Any]] = field(default_factory=list)

    # --- filled by Execute ---------------------------------------------
    turn_policy: Any = None
    request: LearningTurnRequest | None = None
    compressed: Any = None
    result: Any = None  # LearningTurnResult

    # --- filled by Finalize --------------------------------------------
    retrieval_hits: list[dict[str, Any]] = field(default_factory=list)
    retrieval_misses: list[dict[str, Any]] = field(default_factory=list)
    retrieval_evidence_map: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    request_with_metadata: LearningTurnRequest | None = None

    # --- cross-stage warnings ------------------------------------------
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    def retrieval_context(self) -> dict[str, Any]:
        """Adapter that mirrors the legacy ``retrieval_context`` dict.

        Older helpers expect a single mapping; expose a view rather than a
        second source of truth.
        """
        return {
            "retrieval_focus": self.retrieval_focus,
            "retrieval_reason": self.retrieval_reason,
            "retrieval_query_context": self.retrieval_query_context,
            "parallel_support": self.parallel_support,
            "retrieval_bundle": self.retrieval_bundle,
            "prefetched_references": self.prefetched_references,
            "prompt_support_bundle": self.prompt_support_bundle,
        }
