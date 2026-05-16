"""CoLearn tool wiring for the nanobot v0.2 runtime line."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from colearn.learning.turn_contract import LearningTurnRequest
from colearn.memory.store import EventMemoryStore
from colearn.retrieval.adapters import get_lightrag_client
from colearn.retrieval.service import RetrievalService
from colearn.runtime.tool_adapters import normalize_enabled_tools

from .profile import DEFAULT_ENABLED_TOOLS


def install_colearn_tools(
    *,
    bot: Any,
    request: LearningTurnRequest,
    workspace: Path | None = None,
    retrieval_service: RetrievalService | None = None,
    memory_store: EventMemoryStore | None = None,
) -> None:
    enabled = set(normalize_enabled_tools(request.enabled_tools or DEFAULT_ENABLED_TOOLS))
    if not enabled:
        return
    loop = getattr(bot, "_loop", None)
    registry = getattr(loop, "tools", None)
    if registry is None:
        return

    from nanobot.agent.tools.base import Tool, tool_parameters

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
                    if memory_store is not None:
                        events = memory_store.search_events(
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
        resolved_workspace = workspace or Path.cwd()

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
                    if retrieval_service is not None:
                        bundle = await retrieval_service.async_build_bundle_for_source_refs(
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

                    client = get_lightrag_client(workspace=resolved_workspace)
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
