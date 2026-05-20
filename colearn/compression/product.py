"""Product compression for continuation, summary, and board patch output."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from colearn.learning.state import BoardFacts
from colearn.learning.turn_contract import LearningTurnRequest
from colearn.projects.models import LearningProject
from colearn.sessions.store import LearningSession


@dataclass(frozen=True)
class ProductCompressionResult:
    review_summary: str
    continuation_prompt: str
    board_patch: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


from colearn.config.defaults import Defaults


class ProductCompressionBridge:
    def __init__(
        self,
        *,
        max_summary_chars: int = Defaults.PRODUCT_MAX_SUMMARY_CHARS,
        max_continuation_chars: int = Defaults.PRODUCT_MAX_CONTINUATION_CHARS,
    ) -> None:
        self.max_summary_chars = max_summary_chars
        self.max_continuation_chars = max_continuation_chars

    def compress(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        board: BoardFacts,
        request: LearningTurnRequest,
        final_text: str,
    ) -> ProductCompressionResult:
        summary = self._truncate(final_text.strip(), self.max_summary_chars)
        continuation = self._truncate(
            (
                f"Continue with {request.turn_mode.lower()} and revisit: {request.user_message.strip()}"
                if request.user_message.strip()
                else board.continuation.next_prompt_hint or session.continuation_prompt
            ),
            self.max_continuation_chars,
        )
        board_patch = {
            "current_turn_mode": request.turn_mode,
            "board_version": board.board_version,
            "updated_at": board.updated_at,
            "continuation": {
                "next_prompt_hint": continuation,
                "last_completed_turn_id": request.turn_id,
            },
            "current_progress": asdict(board.current_progress),
            "student_snapshot": asdict(board.student_snapshot),
            "gaps_and_blockers": asdict(board.gaps_and_blockers),
            "latest_review": {
                "summary": summary,
                "points": [request.policy_decision.main_goal] if request.policy_decision else [],
                "confusion_points": list(request.policy_decision.review_focus or [])
                if request.policy_decision
                else [],
            },
            "evidence_refs": list(board.evidence_refs),
        }
        return ProductCompressionResult(
            review_summary=summary,
            continuation_prompt=continuation,
            board_patch=board_patch,
            metadata={
                "project_id": project.project_id,
                "session_id": session.session_id,
                "board_snapshot": asdict(board),
            },
        )

    def _truncate(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3].rstrip()}..."
