"""Main CoLearn v0.2 executor built on top of nanobot v0.2."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from colearn.learning.response_contract import LearningTurnResult
from colearn.learning.turn_contract import LearningTurnRequest
from colearn.memory.store import EventMemoryStore
from colearn.retrieval.service import RetrievalService

from .profile import COLEARN_NANOBOT_SLIM_CONFIG
from .prompting import build_turn_prompt
from .result_bridge import normalize_learning_turn_result
from .tooling import install_colearn_tools


@dataclass
class NanobotTurnExecutor:
    """Thin CoLearn wrapper over the nanobot v0.2 runtime."""

    workspace: Path | None = None
    config_path: Path | None = None
    retrieval_service: RetrievalService | None = None
    memory_store: EventMemoryStore | None = None
    _bot: Any = None

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

    class _StreamHook:
        def __init__(self, emit):
            self._emit = emit

        async def on_stream(self, ctx, delta: str):
            if delta:
                self._emit(NanobotTurnExecutor._coerce_stream_event("thinking", delta))

        async def emit_reasoning(self, reasoning_content: str | None):
            if reasoning_content:
                self._emit(NanobotTurnExecutor._coerce_stream_event("reasoning", reasoning_content))

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
        final_text, messages, tools_used = asyncio.run(self._run_turn_async(request=request))
        learning_result = {
            "tool_events": [{"tool_name": name} for name in tools_used],
            "raw_messages": messages,
            "stream_events": list(request.metadata.get("_stream_events") or []),
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
        stream_events: list[dict[str, Any]] = []
        install_colearn_tools(
            bot=bot,
            request=request,
            workspace=self.workspace,
            retrieval_service=self.retrieval_service,
            memory_store=self.memory_store,
        )
        if request.model_preset:
            bot._loop.set_model_preset(request.model_preset)
        result = await bot.run(
            prompt,
            session_key=f"colearn:{request.session_id}",
            hooks=[self._StreamHook(stream_events.append)],
        )
        request.metadata["_stream_events"] = stream_events
        return result.content, result.messages, result.tools_used

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
