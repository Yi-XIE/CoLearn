"""Daemon-thread runner for post-turn product compression.

The finalizer owns scheduling and the compression call only. Persistence stays
with WritebackStage through a minimal callback payload.
"""

from __future__ import annotations

from threading import Thread
from typing import Callable

from colearn.compression import ProductCompressionBridge
from colearn.logging_config import get_logger
from colearn.projects.models import LearningProject
from colearn.sessions.store import LearningSession

logger = get_logger(__name__)


class BackgroundTurnFinalizer:
    def __init__(
        self,
        *,
        product_compression: ProductCompressionBridge,
        on_result: Callable[..., None],
    ) -> None:
        self.product_compression = product_compression
        self.on_result = on_result
        self._threads: list[Thread] = []

    def schedule(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        board,
        request,
        result,
    ) -> None:
        """Spawn a daemon thread for auxiliary compression."""
        self._threads = [t for t in self._threads if t.is_alive()]
        worker = Thread(
            target=self._run,
            kwargs={
                "project": project,
                "session": session,
                "board": board,
                "request": request,
                "result": result,
                "base_board_version": int(board.board_version or 1),
            },
            daemon=True,
        )
        self._threads.append(worker)
        worker.start()

    def shutdown(self, timeout: float = 5.0) -> None:
        for t in self._threads:
            t.join(timeout=timeout)
        self._threads = [t for t in self._threads if t.is_alive()]

    def _run(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        board,
        request,
        result,
        base_board_version: int,
    ) -> None:
        try:
            product_output = self.product_compression.compress(
                project=project,
                session=session,
                board=board,
                request=request,
                final_text=result.final_text,
            )
            self.on_result(
                session_id=session.session_id,
                project_id=project.project_id,
                base_board_version=base_board_version,
                status="completed",
                review_summary=product_output.review_summary,
                continuation_prompt=product_output.continuation_prompt,
                error="",
            )
        except Exception as exc:
            logger.warning(
                "background product compression failed for session %s: %s",
                session.session_id,
                exc,
            )
            try:
                self.on_result(
                    session_id=session.session_id,
                    project_id=project.project_id,
                    base_board_version=base_board_version,
                    status="failed",
                    review_summary="",
                    continuation_prompt="",
                    error=str(exc),
                )
            except Exception:
                logger.exception(
                    "background finalizer error callback failed for session %s",
                    session.session_id,
                )
