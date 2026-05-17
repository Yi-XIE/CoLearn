"""Main assembly entrypoint for a single CoLearn learning turn."""

from __future__ import annotations

from pathlib import Path
from threading import Thread
from time import time
from typing import Any, Callable
from uuid import uuid4

from colearn.compression import ProductCompressionBridge, ProductCompressionResult, RuntimeCompressionBridge
from colearn.knowledge import KnowledgeWorkspaceService
from colearn.learning.state_hooks import (
    before_turn,
    build_learning_board,
    build_state_snapshot,
    policy,
)
from colearn.memory.store import EventMemoryStore, MemoryEvent
from colearn.projects.models import LearningProject
from colearn.projects.service import LearningProjectService
from colearn.retrieval.service import RetrievalService
from colearn.runtime_v2.context_bridge import build_learning_turn_request
from colearn.runtime_v2.executor import NanobotTurnExecutor
from colearn.runtime_v2 import build_learning_closure
from colearn.sessions.store import LearningSession, SessionStore
from .source_preflight import SourceReadinessPreflight


class BackgroundTurnFinalizer:
    def __init__(
        self,
        *,
        product_compression: ProductCompressionBridge,
        on_result: Callable[..., None],
    ) -> None:
        self.product_compression = product_compression
        self.on_result = on_result

    def schedule(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        board,
        request,
        result,
    ) -> None:
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
        worker.start()

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


class LearningOrchestrator:
    def __init__(
        self,
        *,
        project_service: LearningProjectService | None = None,
        session_store: SessionStore | None = None,
        memory_store: EventMemoryStore | None = None,
        knowledge_service: KnowledgeWorkspaceService | None = None,
        retrieval_service: RetrievalService | None = None,
        executor: NanobotTurnExecutor | None = None,
        runtime_compression: RuntimeCompressionBridge | None = None,
        product_compression: ProductCompressionBridge | None = None,
    ) -> None:
        self.project_service = project_service or LearningProjectService()
        self.session_store = session_store or SessionStore()
        self.memory_store = memory_store or EventMemoryStore()
        self.knowledge_service = knowledge_service or KnowledgeWorkspaceService()
        self.retrieval_service = retrieval_service or RetrievalService()
        self.source_preflight = SourceReadinessPreflight(
            retrieval_service=self.retrieval_service,
            knowledge_service=self.knowledge_service,
        )
        self.executor = executor or NanobotTurnExecutor(
            workspace=Path.cwd(),
            retrieval_service=self.retrieval_service,
            memory_store=self.memory_store,
        )
        self.runtime_compression = runtime_compression or RuntimeCompressionBridge()
        self.product_compression = product_compression or ProductCompressionBridge()
        self.background_finalizer = BackgroundTurnFinalizer(
            product_compression=self.product_compression,
            on_result=self.apply_background_result,
        )

    def run_turn(
        self,
        *,
        session_id: str,
        user_message: str,
        project_id: str = "",
        language: str = "zh",
        attachments: list[dict[str, object]] | None = None,
    ):
        session = self._get_or_create_session(session_id=session_id, project_id=project_id)
        project = self._get_or_create_project(project_id=project_id, session=session)
        source_refs = list(session.source_refs or project.source_subset or project.source_refs)
        source_profile = self.source_preflight.run(
            project_id=project.project_id,
            source_refs=source_refs,
        )
        board = build_learning_board(
            project=project,
            session=session,
            latest_review=project.latest_review,
        )
        snapshot = build_state_snapshot(
            project=project,
            session=session,
            latest_review=project.latest_review,
        )
        project.retrieval_profile = {
            **project.retrieval_profile,
            **source_profile,
            "board": board.to_dict(),
        }
        turn_policy = policy(
            board=board,
            user_message=user_message,
        )
        request = build_learning_turn_request(
            session_id=session.session_id,
            user_message=user_message,
            project_id=project.project_id,
            project_title=project.title,
            language=language,
            turn_mode=board.current_turn_mode,
            board_facts=board,
            turn_policy=turn_policy,
            anchor=project.anchor,
            source_references=[{"source_ref": item} for item in (session.source_refs or project.source_refs)],
            memory_references=session.memory_refs or project.memory_refs,
            state_projection=snapshot,
            continuation_prompt=session.continuation_prompt,
            enabled_tools=turn_policy.enabled_tools or turn_policy.allowed_tools,
            attachments=attachments or [],
            metadata={"turn_id": str(uuid4()), "source_profile": dict(source_profile)},
        )
        prepared_request = before_turn(
            request=request,
            snapshot=snapshot,
            decision=turn_policy,
        )
        compressed = self.runtime_compression.compress(request=prepared_request)
        result = self.executor.run_turn(request=compressed.request)
        closure_payload = build_learning_closure(
            project=project,
            session=session,
            request=compressed.request,
            final_text=result.final_text,
            raw_learning_result=result.raw_learning_result,
            warnings=[
                *list(result.warnings),
                *compressed.notes,
            ],
        )
        normalized = self.executor.finalize(
            request=compressed.request,
            final_text=result.final_text,
            learning_result=closure_payload,
        )
        self._write_back(
            project=project,
            session=session,
            request=compressed.request,
            result=normalized,
        )
        self.background_finalizer.schedule(
            project=project,
            session=session,
            board=board,
            request=compressed.request,
            result=normalized,
        )
        return normalized

    def _get_or_create_session(
        self,
        *,
        session_id: str,
        project_id: str,
    ) -> LearningSession:
        session = self.session_store.get_session(session_id)
        if session is None:
            session = self.session_store.create_session(
                session_id=session_id,
                project_id=project_id,
                title="",
            )
        return session

    def _get_or_create_project(
        self,
        *,
        project_id: str,
        session: LearningSession,
    ) -> LearningProject:
        resolved_project_id = project_id or session.project_id or "default-project"
        project = self.project_service.get_project(resolved_project_id)
        if project is None:
            project = self.project_service.create_project(
                resolved_project_id,
                title=resolved_project_id,
            )
        session.project_id = resolved_project_id
        return project

    def _write_back(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        request,
        result,
    ) -> None:
        # Session Board is the runtime source of truth; project.board_facts is a
        # denormalized mirror for project lists and cross-session recovery.
        current_session = self.session_store.get_session(session.session_id)
        current_session_version = int(getattr(current_session, "board_version", session.board_version) or 1)
        base_version = int(getattr(request.board_facts, "board_version", session.board_version) or 1)
        session_conflict = current_session_version > base_version and current_session is not session
        if session_conflict and current_session is not None:
            session = current_session
        session.turn_mode = result.turn_mode_after
        warnings = list(result.warnings)
        if session_conflict:
            warnings.append("board_version_conflict_session_write_skipped")
        else:
            session.board_facts = dict(result.board_after.to_dict())
            session.board_version = int(result.board_after.board_version or 1)
        session.status = "completed"
        session.active_turn_id = None
        session.active_turns = []
        session.continuation_prompt = result.continuation_prompt
        session.last_turn_result = {
            "final_text": result.final_text,
            "warnings": warnings,
            "board_patch": result.board_patch,
            "tool_events": list(result.tool_events),
            "stream_events": list(result.stream_events),
            "raw_learning_result": dict(result.raw_learning_result or {}),
            "runtime_v2": dict((result.raw_learning_result or {}).get("runtime_v2") or {}),
            "product_compression": {
                "status": "scheduled",
                "started_at": None,
                "finished_at": None,
                "error": "",
                "base_board_version": int(base_version or 1),
            },
        }
        session.messages.extend(
            [
                {"role": "user", "content": request.user_message},
                {"role": "assistant", "content": result.final_text},
            ]
        )
        current_project = self.project_service.get_project(project.project_id)
        current_project_version = int(getattr(current_project, "board_version", project.board_version) or 1)
        project_conflict = current_project_version > base_version and current_project is not project
        if project_conflict and current_project is not None:
            project = current_project
        project.turn_mode = result.turn_mode_after
        if project_conflict:
            warnings.append("board_version_conflict_project_write_skipped")
        else:
            project.board_facts = dict(result.board_after.to_dict())
            project.board_version = int(result.board_after.board_version or 1)
        session.last_turn_result = {
            **session.last_turn_result,
            "warnings": warnings,
            "raw_learning_result": dict(result.raw_learning_result or {}),
            "runtime_v2": dict((result.raw_learning_result or {}).get("runtime_v2") or {}),
        }
        project.anchor_status = "ready" if project.anchor else "missing"
        project.current_main_goal = (
            request.turn_policy.main_goal if request.turn_policy else project.current_main_goal
        )
        project.retrieval_profile = {
            **project.retrieval_profile,
            "last_stream_events": list(result.stream_events),
            "last_tool_events": list(result.tool_events),
            "board": dict(project.board_facts or result.board_after.to_dict()),
        }
        for item in result.memory_events:
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind=str(item.get("kind") or "event"),
                    payload=dict(item.get("payload") or {}),
                )
            )
        if not session.source_refs and project.source_refs:
            session.source_refs = list(project.source_refs)
        self.session_store.save_session(session)
        self.project_service.save_project(project)

    def apply_background_result(
        self,
        *,
        session_id: str,
        project_id: str,
        request,
        board,
        product_output: ProductCompressionResult | None,
        error: BaseException | None,
        status_payload: dict[str, Any],
    ) -> None:
        session = self.session_store.get_session(session_id)
        project = self.project_service.get_project(project_id)
        if session is None or project is None:
            return

        last_turn_result = dict(session.last_turn_result or {})
        warnings = list(last_turn_result.get("warnings") or [])
        if error is not None:
            warning = f"product_compression_failed: {error}"
            if warning not in warnings:
                warnings.append(warning)
            last_turn_result["warnings"] = warnings
            last_turn_result["product_compression"] = {
                **status_payload,
                "status": "failed",
                "finished_at": int(time()),
                "error": str(error),
            }
            session.last_turn_result = last_turn_result
            self.session_store.save_session(session)
            return

        if product_output is None:
            return
        stale_board = int(session.board_version or 1) > int(board.board_version or 1) + 1
        if stale_board and "product_compression_stale_board_skipped" not in warnings:
            warnings.append("product_compression_stale_board_skipped")
        pending_review = {
            "summary": product_output.review_summary,
            "points": [request.policy_decision.main_goal] if request.policy_decision else [],
            "confusion_points": list(request.policy_decision.review_focus or []) if request.policy_decision else [],
            "status": "ready",
        }
        session.continuation_prompt = product_output.continuation_prompt
        session.pending_review = pending_review
        last_turn_result["warnings"] = warnings
        last_turn_result["product_compression"] = {
            **status_payload,
            "status": "completed",
            "finished_at": int(time()),
            "error": "",
            "stale_board": stale_board,
            "review_summary": product_output.review_summary,
            "continuation_prompt": product_output.continuation_prompt,
        }
        session.last_turn_result = last_turn_result
        project.latest_review = dict(pending_review)
        self.session_store.save_session(session)
        self.project_service.save_project(project)
