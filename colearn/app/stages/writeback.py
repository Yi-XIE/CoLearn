"""WritebackStage — persists turn results, runs board/dream consolidation."""

from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from colearn.logging_config import get_logger
from colearn.memory.store import EventMemoryStore, MemoryEvent
from colearn.projects.models import LearningProject
from colearn.projects.service import LearningProjectService
from colearn.runtime_v2.executor import NanobotTurnExecutor
from colearn.sessions.store import LearningSession, SessionStore

from .context import TurnContext
from colearn.learning.events import MemoryEventKind
from .utils import (
    append_session_warning,
    build_compaction_summary,
    memory_excerpt,
    nanobot_history_entry,
    run_async_or_value,
    runtime_loop,
)

logger = get_logger(__name__)


class WritebackStage:
    """Pure refactor of the legacy ``_write_back`` family.

    Tunables (autocompact thresholds, dream / board snapshot intervals) are
    constructor-injected to keep the orchestrator's public constants as the
    single source of truth.
    """

    def __init__(
        self,
        *,
        project_service: LearningProjectService,
        session_store: SessionStore,
        memory_store: EventMemoryStore,
        executor: NanobotTurnExecutor,
        background_finalizer: Any,
        build_last_turn_result: Callable[..., dict[str, Any]],
        owner: Any,
    ) -> None:
        self.project_service = project_service
        self.session_store = session_store
        self.memory_store = memory_store
        self.executor = executor
        self.background_finalizer = background_finalizer
        # Borrowed from FinalizeStage so we don't cross-import it.
        self._build_last_turn_result = build_last_turn_result
        # Back-ref to the orchestrator; lets us read mutable tunables
        # (autocompact thresholds, board_deriver, …) at call time so tests can
        # tweak them after construction.
        self._owner = owner

    # ------------------------------------------------------------------
    # Tunables read live from the orchestrator (`_owner`) so tests can mutate
    # them after construction without re-wiring stages.
    # ------------------------------------------------------------------
    @property
    def board_deriver(self) -> Any:
        return self._owner.board_deriver

    @property
    def SESSION_AUTOCOMPACT_MAX_MESSAGES(self) -> int:
        return self._owner.SESSION_AUTOCOMPACT_MAX_MESSAGES

    @property
    def SESSION_AUTOCOMPACT_KEEP_TAIL(self) -> int:
        return self._owner.SESSION_AUTOCOMPACT_KEEP_TAIL

    @property
    def SESSION_AUTOCOMPACT_SUMMARY_MAX_CHARS(self) -> int:
        return self._owner.SESSION_AUTOCOMPACT_SUMMARY_MAX_CHARS

    @property
    def DREAM_CONSOLIDATION_EVENT_INTERVAL(self) -> int:
        return self._owner.DREAM_CONSOLIDATION_EVENT_INTERVAL

    @property
    def BOARD_DERIVATION_EVENT_INTERVAL(self) -> int:
        return self._owner.BOARD_DERIVATION_EVENT_INTERVAL

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def run(self, ctx: TurnContext) -> None:
        self._write_back(
            project=ctx.project,
            session=ctx.session,
            request=ctx.request_with_metadata,
            result=ctx.result,
        )
        # Background product compression must see the *pre-finalize* request,
        # exactly as before — that's what the executor produced from compression.
        self.background_finalizer.schedule(
            project=ctx.project,
            session=ctx.session,
            board=ctx.board,
            request=ctx.compressed.request,
            result=ctx.result,
        )

    # ------------------------------------------------------------------
    # Internals (lifted verbatim from LearningOrchestrator)
    # ------------------------------------------------------------------
    def _write_back(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        request,
        result,
    ) -> None:
        """Persist turn output with board-version conflict protection.

        Rejects writes whose ``board_before.board_version`` is older than the
        current session board — protects concurrent turns / background
        finalizers from clobbering newer state. The dropped result still emits
        a warning in ``warnings``.
        """
        # Session Board is the runtime source of truth; project.board_facts is
        # a denormalized mirror for project lists and cross-session recovery.
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
        session.last_turn_result = self._build_last_turn_result(
            request=request,
            result=result,
            warnings=warnings,
            base_version=base_version,
            include_product_compression=True,
        )
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
        session.last_turn_result = self._build_last_turn_result(
            request=request,
            result=result,
            warnings=warnings,
            base_version=base_version,
            include_product_compression=True,
        )
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
        # P2: Persist learning_events (incl. signal_extractor output) to event store
        for item in result.learning_events:
            if hasattr(item, "event_id"):
                self.memory_store.append(item)
            elif isinstance(item, dict) and item.get("kind"):
                self.memory_store.append(
                    MemoryEvent(
                        event_id=str(item.get("event_id") or uuid4()),
                        kind=str(item["kind"]),
                        payload=dict(item.get("payload") or {}),
                    )
                )
        # P1: Record board_patch application as event for consolidation input
        board_patch = result.board_patch
        if board_patch and not session_conflict:
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind=MemoryEventKind.BOARD_PATCH_APPLIED,
                    payload={
                        "session_id": session.session_id,
                        "project_id": project.project_id,
                        "patch_keys": list(board_patch.keys()),
                        "board_version": int(result.board_after.board_version or 1),
                    },
                )
            )
        self._append_nanobot_history(project=project, session=session, result=result)
        self._maybe_compact_session(session)
        self._maybe_consolidate_memory(project, session, result)
        self._maybe_derive_board_snapshot(project=project, session=session, result=result)
        if not session.source_refs and project.source_refs:
            session.source_refs = list(project.source_refs)
        self.session_store.save_session(session)
        self.project_service.save_project(project)

    def _maybe_compact_session(self, session: LearningSession) -> None:
        max_messages = self.SESSION_AUTOCOMPACT_MAX_MESSAGES
        if len(session.messages) <= max_messages:
            return
        keep_tail = session.messages[-self.SESSION_AUTOCOMPACT_KEEP_TAIL :]
        old_messages = session.messages[: -self.SESSION_AUTOCOMPACT_KEEP_TAIL]
        summary, source = self._archive_compacted_messages(old_messages)
        session.messages = [
            {
                "role": "system",
                "content": f"[compacted history] {summary}",
                "metadata": {
                    "colearn_compacted": True,
                    "compacted_count": len(old_messages),
                    "compaction_source": source,
                },
            },
            *keep_tail,
        ]

    def _maybe_consolidate_memory(
        self,
        project: LearningProject,
        session: LearningSession,
        result,
    ) -> None:
        event_count = len(self.memory_store.list_events())
        if event_count == 0 or event_count % self.DREAM_CONSOLIDATION_EVENT_INTERVAL != 0:
            return
        loop = runtime_loop(self.executor)
        dream = getattr(loop, "dream", None) if loop is not None else None
        if dream is None or not hasattr(dream, "run"):
            summary = self._consolidate_dream_events(
                project=project,
                session=session,
                recent_events=self.memory_store.list_events()[-self.DREAM_CONSOLIDATION_EVENT_INTERVAL :],
                fallback_text=result.review_summary or result.final_text,
            )
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind=MemoryEventKind.PROFILE_CONSOLIDATED,
                    payload=summary,
                )
            )
            return
        try:
            did_work = run_async_or_value(dream.run())
            if not did_work:
                return
            store = getattr(dream, "store", None) or getattr(getattr(loop, "context", None), "memory", None)
            excerpt = memory_excerpt(store)
            dream_cursor = (
                store.get_last_dream_cursor()
                if store is not None and hasattr(store, "get_last_dream_cursor")
                else None
            )
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind=MemoryEventKind.PROFILE_CONSOLIDATED,
                    payload={
                        "source": "nanobot_dream",
                        "session_id": session.session_id,
                        "project_id": project.project_id,
                        "dream_cursor": dream_cursor,
                        "memory_excerpt": excerpt,
                        "recent_event_count": self.DREAM_CONSOLIDATION_EVENT_INTERVAL,
                    },
                )
            )
        except Exception as exc:
            warning = f"dream_consolidation_failed:{type(exc).__name__}"
            append_session_warning(session, warning)
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind=MemoryEventKind.PROFILE_CONSOLIDATION_FAILED,
                    payload={
                        "source": "nanobot_dream",
                        "session_id": session.session_id,
                        "project_id": project.project_id,
                        "error": str(exc),
                    },
                )
            )

    def _maybe_derive_board_snapshot(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        result,
    ) -> None:
        """Q3: Periodically re-derive BoardFacts from event stream via LLM.

        Runs synchronously after writeback. If ``board_deriver`` is None
        (default), no-op — preserves backward compat. On success, overwrites
        ``session.board_facts`` and emits ``board_snapshot_derived`` for audit.
        """
        if self.board_deriver is None:
            return
        session_events = self.memory_store.list_events_for_session(session.session_id)
        if (
            len(session_events) == 0
            or len(session_events) % self.BOARD_DERIVATION_EVENT_INTERVAL != 0
        ):
            return
        from colearn.learning.state_hooks import build_learning_board

        current_board = build_learning_board(session=session, project=project)
        project_summary = (
            f"{project.title}: anchor={project.anchor or {}}; "
            f"sources={len(project.source_refs or [])}"
        )
        try:
            new_board, diff = self.board_deriver.derive_snapshot(
                events=session_events,
                current_board=current_board,
                project_summary=project_summary,
            )
        except Exception as exc:
            logger.warning("board_deriver.derive_snapshot raised: %s", exc)
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind=MemoryEventKind.BOARD_SNAPSHOT_FAILED,
                    payload={
                        "session_id": session.session_id,
                        "project_id": project.project_id,
                        "error": str(exc),
                    },
                )
            )
            return

        if diff.get("status") != "ok":
            self.memory_store.append(
                MemoryEvent(
                    event_id=str(uuid4()),
                    kind=MemoryEventKind.BOARD_SNAPSHOT_FAILED,
                    payload={
                        "session_id": session.session_id,
                        "project_id": project.project_id,
                        "diff_status": diff.get("status"),
                    },
                )
            )
            return

        session.board_facts = new_board.to_dict()
        session.board_version = int(new_board.board_version or 1)
        self.session_store.save_session(session)
        self.memory_store.append(
            MemoryEvent(
                event_id=str(uuid4()),
                kind=MemoryEventKind.BOARD_SNAPSHOT_DERIVED,
                payload={
                    "session_id": session.session_id,
                    "project_id": project.project_id,
                    "board_version": int(new_board.board_version or 1),
                    "event_count": diff.get("event_count", 0),
                    "changes": diff.get("changes", {}),
                },
            )
        )

    def _archive_compacted_messages(self, messages: list[dict[str, Any]]) -> tuple[str, str]:
        loop = runtime_loop(self.executor)
        consolidator = getattr(loop, "consolidator", None) if loop is not None else None
        if consolidator is not None and hasattr(consolidator, "archive"):
            try:
                summary = run_async_or_value(consolidator.archive(messages))
                if summary:
                    return (
                        str(summary)[: self.SESSION_AUTOCOMPACT_SUMMARY_MAX_CHARS],
                        "nanobot_consolidator",
                    )
            except (RuntimeError, TypeError, ValueError) as exc:
                logger.warning("consolidator.archive failed: %s", exc)
        return (
            build_compaction_summary(messages, self.SESSION_AUTOCOMPACT_SUMMARY_MAX_CHARS),
            "fallback",
        )

    def _append_nanobot_history(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        result,
    ) -> None:
        loop = runtime_loop(self.executor)
        store = getattr(getattr(loop, "context", None), "memory", None) if loop is not None else None
        if store is None or not hasattr(store, "append_history"):
            return
        try:
            store.append_history(
                nanobot_history_entry(project=project, session=session, result=result),
                max_chars=4000,
            )
        except Exception:
            append_session_warning(session, "nanobot_history_append_failed")

    def _consolidate_dream_events(
        self,
        *,
        project: LearningProject,
        session: LearningSession,
        recent_events: list[MemoryEvent],
        fallback_text: str,
    ) -> dict[str, Any]:
        facts = [
            str(event.payload.get("summary") or event.payload.get("content") or event.kind).strip()
            for event in recent_events
            if str(event.payload.get("summary") or event.payload.get("content") or event.kind).strip()
        ]
        combined = " | ".join(facts) or fallback_text[:240]
        return {
            "summary": combined[:240],
            "session_id": session.session_id,
            "project_id": project.project_id,
            "source": "dream_consolidation",
            "recent_event_count": len(recent_events),
            "recent_event_kinds": [event.kind for event in recent_events],
        }
