"""Standalone nanobot-aligned executor seam for CoLearn."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from colearn.learning.response_contract import LearningTurnResult
from colearn.learning.turn_contract import LearningTurnRequest
from colearn.memory.store import EventMemoryStore
from colearn.retrieval.adapters import get_lightrag_client
from colearn.retrieval.service import RetrievalService

from .nanobot_bridge import normalize_learning_turn_result
from .tool_adapters import normalize_enabled_tools


@dataclass
class NanobotTurnExecutor:
    """Current minimal executor wrapper around the reduced nanobot core."""

    workspace: Path | None = None
    config_path: Path | None = None
    retrieval_service: RetrievalService | None = None
    memory_store: EventMemoryStore | None = None
    _bot: Any = None

    def run_turn(self, *, request: LearningTurnRequest) -> LearningTurnResult:
        final_text, messages, tools_used = asyncio.run(self._run_turn_async(request=request))
        learning_result = {
            "tool_events": [{"tool_name": name} for name in tools_used],
            "raw_messages": messages,
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
        prompt = self._build_prompt(request)
        bot = self._get_bot()
        self._install_colearn_tools(bot=bot, request=request)
        result = await bot.run(prompt, session_key=f"colearn:{request.session_id}")
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
            if self.config_path is not None:
                kwargs["config_path"] = self.config_path
            if self.workspace is not None:
                kwargs["workspace"] = self.workspace
            self._bot = Nanobot.from_config(**kwargs)
        return self._bot

    def _build_prompt(self, request: LearningTurnRequest) -> str:
        lines = [
            f"Project: {request.project_title or request.project_id or 'Untitled Project'}",
            f"Turn mode: {request.turn_mode}",
        ]
        policy = request.turn_policy or request.policy_decision
        if policy and getattr(policy, "main_goal", ""):
            lines.append(f"Main goal: {policy.main_goal}")
        if request.continuation_prompt:
            lines.append(f"Continuation: {request.continuation_prompt}")
        source_profile = dict(request.metadata.get("source_profile") or {})
        if source_profile:
            sync = dict(source_profile.get("sync") or {})
            warnings = list(source_profile.get("warnings") or sync.get("warnings") or [])
            readiness = str(source_profile.get("readiness") or "unknown")
            sync_status = str(source_profile.get("sync_status") or sync.get("sync_status") or "unknown")
            source_count = int(source_profile.get("source_count") or len(source_profile.get("sources") or []))
            hint = (
                f"Source readiness: readiness={readiness}; sync_status={sync_status}; "
                f"available_sources={source_count}"
            )
            if warnings:
                hint = f"{hint}; warnings={'; '.join(str(item) for item in warnings[:3])}"
            lines.append(hint)
        restrictions = list(request.metadata.get("policy_restrictions") or [])
        if not restrictions and policy is not None:
            restrictions = list(getattr(policy, "restrictions", []) or [])
        if restrictions:
            lines.append(f"Restrictions: {', '.join(restrictions)}")
        if request.anchor:
            lines.append(f"Anchor: {request.anchor}")
        lines.append("User message:")
        lines.append(request.user_message)
        return "\n\n".join(line for line in lines if line)

    def _install_colearn_tools(self, *, bot: Any, request: LearningTurnRequest) -> None:
        enabled = set(normalize_enabled_tools(request.enabled_tools))
        if not enabled:
            return
        loop = getattr(bot, "_loop", None)
        registry = getattr(loop, "tools", None)
        if registry is None:
            return

        from nanobot.agent.tools.base import Tool, tool_parameters

        self_outer = self

        if registry.has("memory"):
            registry.unregister("memory")
        if registry.has("lightrag"):
            registry.unregister("lightrag")

        if "memory" in enabled:

            @tool_parameters(
                {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                }
            )
            class ColearnMemoryTool(Tool):
                @property
                def name(self) -> str:
                    return "memory"

                @property
                def description(self) -> str:
                    return "Read relevant CoLearn memory references for the current turn."

                async def execute(self, **kwargs: Any) -> Any:
                    try:
                        query = str(kwargs.get("query") or "").strip() or request.user_message
                        if self_outer.memory_store is not None:
                            events = self_outer.memory_store.search_events(
                                query=query,
                                session_id=request.session_id,
                                project_id=request.project_id,
                            )
                            if events:
                                return "\n".join(
                                    "- "
                                    f"id={event.event_id}; kind={event.kind}; "
                                    f"summary={event.payload.get('summary') or event.payload}"
                                    for event in events
                                )
                        refs = request.memory_references or []
                        if refs:
                            return "\n".join(f"- {item}" for item in refs)
                        return "No memory references are attached for this turn."
                    except Exception as exc:
                        return f"Memory context unavailable: {exc}"

            registry.register(ColearnMemoryTool())

        if "lightrag" in enabled:
            workspace = self.workspace or Path.cwd()

            @tool_parameters(
                {
                    "type": "object",
                    "properties": {"question": {"type": "string"}},
                    "required": ["question"],
                }
            )
            class ColearnLightRAGTool(Tool):
                @property
                def name(self) -> str:
                    return "lightrag"

                @property
                def description(self) -> str:
                    return "Retrieve project knowledge context with LightRAG when the current turn needs external knowledge."

                async def execute(self, **kwargs: Any) -> Any:
                    try:
                        question = str(kwargs.get("question") or "").strip() or request.user_message
                        if self_outer.retrieval_service is not None:
                            bundle = await self_outer.retrieval_service.async_build_bundle_for_source_refs(
                                project_id=request.project_id,
                                query=question,
                                source_refs=[
                                    str(item.get("source_ref") or item.get("source_path") or "")
                                    for item in request.source_references
                                    if str(item.get("source_ref") or item.get("source_path") or "")
                                ],
                            )
                            status_line = (
                                f"retrieval_status={bundle.retrieval_status}; "
                                f"source_refs={len(bundle.source_refs or [])}; "
                                f"warnings={'; '.join(bundle.warnings or [])}"
                            )
                            if bundle.text:
                                return f"{status_line}\n\n{bundle.text}"
                            if bundle.warnings:
                                return f"LightRAG context unavailable: {'; '.join(bundle.warnings)}"
                            return "LightRAG context is not ready for this turn."

                        client = get_lightrag_client(workspace=workspace)
                        normalized_refs = []
                        for item in request.source_references:
                            raw = str(item.get("source_path") or item.get("source_ref") or item.get("path") or "").strip()
                            payload = dict(item)
                            if raw and "source_path" not in payload:
                                candidate = Path(raw)
                                if candidate.exists():
                                    payload["source_path"] = str(candidate.resolve())
                                    payload.setdefault("source_id", str(candidate.resolve()))
                            normalized_refs.append(payload)
                        result = await client.async_retrieve_project_context(
                            project_id=request.project_id,
                            query=question,
                            source_refs=normalized_refs,
                        )
                        warnings = list(result.warnings or [])
                        status_line = (
                            f"retrieval_status={result.retrieval_status}; "
                            f"source_refs={len(result.references or [])}; "
                            f"warnings={'; '.join(warnings)}"
                        )
                        if result.text:
                            return f"{status_line}\n\n{result.text}"
                        if warnings:
                            return f"LightRAG context unavailable: {'; '.join(warnings)}"
                        return "LightRAG context is not ready for this turn."
                    except Exception as exc:
                        return f"LightRAG context unavailable: {exc}"

            registry.register(ColearnLightRAGTool())
