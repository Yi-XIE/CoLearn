"""BackgroundTurnFinalizer — daemon-thread runner for post-turn product compression.

Extracted from LearningOrchestrator: lets the orchestrator focus on the
synchronous 5-stage pipeline while heavyweight compression runs out-of-band.
All dependencies are injected via the constructor.
"""

from __future__ import annotations

from threading import Thread
from time import time
from typing import Any, Callable

from colearn.compression import ProductCompressionBridge
from colearn.projects.models import LearningProject
from colearn.sessions.store import LearningSession


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
        """Spawn a daemon Thread for product compression that may outlive the turn."""
        self._threads = [t for t in self._threads if t.is_alive()]
        status_payload = {
            "status": "scheduled",
            "started_at": int(time()),
            "finished_at": None,
            "error": "",
            "base_board_version": int(board.board_version or 1),
        }
        worker = Thread(
            target=self._run,
            kwargs={
                "project": project,
                "session": session,
                "board": board,
                "request": request,
                "result": result,
                "status_payload": status_payload,
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
        status_payload: dict[str, Any],
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
                request=request,
                board=board,
                product_output=product_output,
                error=None,
                status_payload=status_payload,
            )
        except Exception as exc:
            self.on_result(
                session_id=session.session_id,
                project_id=project.project_id,
                request=request,
                board=board,
                product_output=None,
                error=exc,
                status_payload=status_payload,
            )
