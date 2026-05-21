"""Main CoLearn v0.2 executor built on top of nanobot v0.2."""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from nanobot.agent.hook import AgentHook

from colearn.learning.response_contract import LearningTurnResult
from colearn.learning.turn_contract import LearningTurnRequest
from colearn.logging_config import get_logger
from colearn.memory.store import EventMemoryStore
from colearn.retrieval.service import RetrievalService

from .profile import COLEARN_NANOBOT_SLIM_CONFIG
from .prompting import build_turn_prompt
from .result_bridge import normalize_learning_turn_result
from .tooling import install_colearn_tools

logger = get_logger(__name__)


class TurnTimeoutError(TimeoutError):
    """Raised when a turn exceeds the configured timeout."""


class TurnCancelledError(RuntimeError):
    """Raised when a turn is cancelled cooperatively."""


from colearn.utils.async_guards import reject_sync_inside_event_loop as _reject_sync_inside_event_loop


@dataclass
class NanobotTurnExecutor:
    """Thin CoLearn wrapper over the nanobot v0.2 runtime."""

    workspace: Path | None = None
    config_path: Path | None = None
    retrieval_service: RetrievalService | None = None
    memory_store: EventMemoryStore | None = None
    _bot: Any = None
    _active_loops_by_session: dict[str, asyncio.AbstractEventLoop] | None = None
    _active_loops_lock: Lock = Lock()

    def __post_init__(self) -> None:
        if self._active_loops_by_session is None:
            self._active_loops_by_session = {}

    @staticmethod
    def _coerce_stream_event(event_type: str, content: str = "", **metadata: Any) -> dict[str, Any]:
        payload = {
            "type": event_type,
            "source": "assistant",
            "stage": "turn",
            "content": content,
            "metadata": {"phase": event_type, **metadata},
        }
        return payload

    class _StreamHook(AgentHook):
        def __init__(self, emit):
            super().__init__()
            self._emit = emit

        def wants_streaming(self) -> bool:
            return True

        async def on_stream(self, ctx, delta: str):
            if delta:
                self._emit(NanobotTurnExecutor._coerce_stream_event("content_delta", delta))

        async def emit_reasoning(self, reasoning_content: str | None):
            if reasoning_content:
                self._emit(NanobotTurnExecutor._coerce_stream_event("reasoning_delta", reasoning_content))

        async def emit_reasoning_end(self):
            self._emit(NanobotTurnExecutor._coerce_stream_event("reasoning_end", ""))

        async def on_stream_end(self, ctx, *, resuming: bool):
            self._emit(NanobotTurnExecutor._coerce_stream_event("stream_end", "", resuming=bool(resuming)))

        async def before_execute_tools(self, ctx):
            for tool_call in list(getattr(ctx, "tool_calls", []) or []):
                self._emit(
                    NanobotTurnExecutor._coerce_stream_event(
                        "tool_call",
                        "",
                        tool_name=str(getattr(tool_call, "name", "") or ""),
                        args=getattr(tool_call, "arguments", {}),
                    )
                )

        async def after_iteration(self, ctx):
            if getattr(ctx, "tool_events", None):
                for item in list(ctx.tool_events or []):
                    self._emit(
                        NanobotTurnExecutor._coerce_stream_event(
                            str(item.get("type") or "tool_event"),
                            str(item.get("content") or ""),
                            **{k: v for k, v in item.items() if k not in {"type", "content"}},
                        )
                    )

    def run_turn(self, *, request: LearningTurnRequest) -> LearningTurnResult:
        """Sync entry that wraps the async nanobot run in `asyncio.run`.

        Refuses to execute inside an active event loop (`_reject_sync_inside_event_loop`)
        because `asyncio.run` cannot be nested. Async callers must invoke
        `run_turn_async` directly or use `to_thread.run_sync`.
        """
        _reject_sync_inside_event_loop("NanobotTurnExecutor.run_turn")
        final_text, messages, tools_used = asyncio.run(self._run_turn_async(request=request))
        learning_result = {
            "tool_events": [{"tool_name": name} for name in tools_used],
            "raw_messages": messages,
            "stream_events": list(request.metadata.get("_stream_events") or []),
            "warnings": list(request.metadata.get("_runtime_warnings") or []),
        }
        return self.finalize(
            request=request,
            final_text=final_text,
            learning_result=learning_result,
        )

    async def run_turn_async(self, *, request: LearningTurnRequest) -> LearningTurnResult:
        """Async entry — drives nanobot directly without creating a new event loop."""
        final_text, messages, tools_used = await self._run_turn_async(request=request)
        learning_result = {
            "tool_events": [{"tool_name": name} for name in tools_used],
            "raw_messages": messages,
            "stream_events": list(request.metadata.get("_stream_events") or []),
            "warnings": list(request.metadata.get("_runtime_warnings") or []),
        }
        return self.finalize(
            request=request,
            final_text=final_text,
            learning_result=learning_result,
        )

    async def _run_turn_async(
        self,
        *,
        request: LearningTurnRequest,
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        prompt = build_turn_prompt(request)
        bot = self._get_bot()
        session_key = f"colearn:{request.session_id}"
        stream_events: list[dict[str, Any]] = []
        event_index = 0
        active_loop = asyncio.get_running_loop()
        self._register_session_loop(request.session_id, active_loop)

        def emit_stream_event(event: dict[str, Any]) -> None:
            nonlocal event_index
            payload = dict(event)
            payload["metadata"] = {
                **dict(payload.get("metadata") or {}),
                "runtime_event_index": event_index,
            }
            event_index += 1
            stream_events.append(payload)
            if request.stream_emit is not None:
                try:
                    request.stream_emit(dict(payload))
                except Exception as exc:
                    request.metadata.setdefault("_runtime_warnings", []).append(
                        f"stream_emit_failed:{type(exc).__name__}"
                    )

        install_colearn_tools(
            bot=bot,
            request=request,
            workspace=self.workspace,
            retrieval_service=self.retrieval_service,
            memory_store=self.memory_store,
        )
        if request.model_preset:
            self._apply_model_preset(bot=bot, preset=request.model_preset, request=request)
        import os
        os.environ["COLEARN_SESSION_ID"] = request.session_id
        os.environ["COLEARN_PROJECT_ID"] = request.project_id or ""
        timeout = request.metadata.get("turn_timeout_seconds")
        bot_coroutine = bot.run(
            prompt,
            session_key=session_key,
            hooks=[self._StreamHook(emit_stream_event)],
        )
        try:
            if request.cancel_check is not None and request.cancel_check():
                raise TurnCancelledError(f"turn {request.turn_id or '?'} cancelled before runtime start")
            if timeout is not None and float(timeout) > 0:
                result = await asyncio.wait_for(bot_coroutine, timeout=float(timeout))
            else:
                result = await bot_coroutine
        except asyncio.CancelledError as exc:
            raise TurnCancelledError(f"turn {request.turn_id or '?'} cancelled") from exc
        except asyncio.TimeoutError as exc:
            raise TurnTimeoutError(
                f"turn {request.turn_id or '?'} exceeded timeout of {timeout}s"
            ) from exc
        finally:
            request.metadata["_stream_events"] = stream_events
            self._unregister_session_loop(request.session_id, active_loop)
        return result.content, result.messages, result.tools_used

    def cancel_session(self, session_id: str) -> bool:
        with self._active_loops_lock:
            loop = (self._active_loops_by_session or {}).get(session_id)
        if loop is None or loop.is_closed() or self._bot is None:
            return False
        bot_loop = getattr(self._bot, "_loop", None)
        if bot_loop is None or not hasattr(bot_loop, "_cancel_active_tasks"):
            return False
        future = asyncio.run_coroutine_threadsafe(
            bot_loop._cancel_active_tasks(f"colearn:{session_id}"),
            loop,
        )
        try:
            return bool(future.result(timeout=2.0))
        except (TimeoutError, concurrent.futures.TimeoutError, RuntimeError):
            future.cancel()
            return False

    def _register_session_loop(self, session_id: str, loop: asyncio.AbstractEventLoop) -> None:
        with self._active_loops_lock:
            assert self._active_loops_by_session is not None
            self._active_loops_by_session[session_id] = loop

    def _unregister_session_loop(self, session_id: str, loop: asyncio.AbstractEventLoop) -> None:
        with self._active_loops_lock:
            if self._active_loops_by_session is None:
                return
            current = self._active_loops_by_session.get(session_id)
            if current is loop:
                self._active_loops_by_session.pop(session_id, None)

    def _apply_model_preset(self, *, bot: Any, preset: str, request: LearningTurnRequest) -> None:
        loop = getattr(bot, "_loop", None)
        if loop is None or not hasattr(loop, "set_model_preset"):
            request.metadata.setdefault("_runtime_warnings", []).append("model_preset_runtime_unavailable")
            return
        available = set((getattr(loop, "model_presets", {}) or {}).keys())
        resolved = preset
        if available and preset not in available:
            request.metadata.setdefault("_runtime_warnings", []).append(f"model_preset_missing:{preset}")
            resolved = "default" if "default" in available else ""
        if not resolved:
            return
        try:
            loop.set_model_preset(resolved)
        except Exception as exc:
            request.metadata.setdefault("_runtime_warnings", []).append(
                f"model_preset_apply_failed:{resolved}:{type(exc).__name__}"
            )

    def finalize(
        self,
        *,
        request: LearningTurnRequest,
        final_text: str,
        learning_result: dict[str, Any] | None = None,
    ) -> LearningTurnResult:
        return normalize_learning_turn_result(
            request=request,
            final_text=final_text,
            learning_result=learning_result,
        )

    def _get_bot(self) -> Any:
        if self._bot is None:
            from nanobot.nanobot import Nanobot

            kwargs: dict[str, Any] = {}
            resolved_config = self.config_path
            if resolved_config is None and COLEARN_NANOBOT_SLIM_CONFIG.exists():
                resolved_config = COLEARN_NANOBOT_SLIM_CONFIG
            if resolved_config is not None:
                kwargs["config_path"] = resolved_config
            if self.workspace is not None:
                kwargs["workspace"] = self.workspace
            self._bot = Nanobot.from_config(**kwargs)
        return self._bot

    def _build_prompt(self, request: LearningTurnRequest) -> str:
        return build_turn_prompt(request)
