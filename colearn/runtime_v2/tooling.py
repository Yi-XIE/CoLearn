"""CoLearn tool wiring for the nanobot v0.2 runtime line."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from typing import Any, Protocol

from colearn.learning.turn_contract import LearningTurnRequest
from colearn.memory.store import EventMemoryStore
from colearn.retrieval.adapters import get_lightrag_client
from colearn.retrieval.service import RetrievalService
from colearn.runtime_v2.tool_adapters import normalize_enabled_tools

from .profile import DEFAULT_ENABLED_TOOLS

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.context import ContextAware, RequestContext


class ToolRegistryLike(Protocol):
    def has(self, name: str) -> bool: ...

    def register(self, tool: Tool) -> None: ...

    def unregister(self, name: str) -> None: ...

    def get(self, name: str) -> Tool | None: ...


def _append_runtime_warning(request: LearningTurnRequest, warning: str) -> None:
    request.metadata.setdefault("_runtime_warnings", []).append(warning)


def _registry_get(registry: ToolRegistryLike, name: str) -> Tool | None:
    getter = getattr(registry, "get", None)
    if callable(getter):
        return getter(name)
    items = getattr(registry, "registered", None)
    if isinstance(items, dict):
        return items.get(name)
    items = getattr(registry, "items", None)
    if isinstance(items, dict):
        return items.get(name)
    return None


def _normalize_evidence_rows(
    *,
    source_rows: list[dict[str, Any]],
    active_node_id: str,
) -> dict[str, Any]:
    evidence_refs: list[dict[str, Any]] = []
    evidence_map: dict[str, list[dict[str, Any]]] = {}
    for idx, row in enumerate(source_rows):
        raw_ref = str(row.get("source_ref") or row.get("source_path") or row.get("path") or "").strip()
        if not raw_ref:
            continue
        chunk_id = str(row.get("chunk_id") or f"tool_{idx}")
        support_type = str(row.get("support_type") or "reference")
        target_id = str(row.get("target_id") or active_node_id or "").strip()
        target_type = str(row.get("target_type") or ("node" if target_id else "")).strip()
        target_label = str(row.get("target_label") or target_id).strip()
        try:
            confidence = float(row.get("confidence") or row.get("score") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        evidence = {
            "source_ref": raw_ref,
            "source_path": str(row.get("source_path") or ""),
            "chunk_id": chunk_id,
            "support_type": support_type,
            "active_node_id": active_node_id,
            "target_type": target_type,
            "target_id": target_id,
            "target_label": target_label,
            "support_target": {"type": target_type, "id": target_id, "label": target_label},
            "support_targets": [target for target in [target_id] if target],
            "support_reason": str(row.get("support_reason") or ""),
            "confidence": confidence,
            "text": str(row.get("text") or "").strip(),
        }
        evidence_refs.append(evidence)
        for key in [active_node_id, f"chunk:{chunk_id}"]:
            if key:
                evidence_map.setdefault(key, []).append(evidence)
    return {
        "evidence_refs": evidence_refs,
        "evidence_map": evidence_map,
    }


def _resolve_tool_registry(*, bot: Any, request: LearningTurnRequest) -> ToolRegistryLike:
    registry = getattr(bot, "tools", None)
    if registry is not None:
        return registry

    loop = getattr(bot, "_loop", None)
    registry = getattr(loop, "tools", None)
    if registry is not None:
        _append_runtime_warning(request, "tool_registry_private_api_fallback")
        return registry

    raise RuntimeError(
        "CoLearn tools requested but nanobot exposes no compatible tool registry. "
        "Expected bot.tools or bot._loop.tools."
    )


@tool_parameters(
    {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
)
class ColearnMemoryTool(Tool):
    def __init__(
        self,
        *,
        request: LearningTurnRequest,
        memory_store: EventMemoryStore | None = None,
    ) -> None:
        self._request_var: ContextVar[LearningTurnRequest] = ContextVar("colearn_memory_request", default=request)
        self._memory_store = memory_store

    def bind_request(
        self,
        *,
        request: LearningTurnRequest,
        memory_store: EventMemoryStore | None = None,
    ) -> None:
        self._request_var.set(request)
        self._memory_store = memory_store

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "Read relevant CoLearn memory references for the current turn."

    async def execute(self, **kwargs: Any) -> Any:
        request = self._request_var.get()
        try:
            query = str(kwargs.get("query") or "").strip() or request.user_message
            if self._memory_store is not None:
                events = self._memory_store.search_events(
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
                evidence = _normalize_evidence_rows(
                    source_rows=[
                        {"source_ref": item, "chunk_id": f"memory_{idx}"}
                        for idx, item in enumerate(refs)
                    ],
                    active_node_id=str(request.board_facts.current_progress.active_node_id or ""),
                )
                return evidence
            return {
                "status": "empty",
                "evidence_refs": [],
                "evidence_map": {},
                "message": "No memory references are attached for this turn.",
            }
        except (RuntimeError, ValueError, KeyError, OSError) as exc:
            return {
                "status": "error",
                "evidence_refs": [],
                "evidence_map": {},
                "message": f"Memory context unavailable: {exc}",
            }


@tool_parameters(
    {
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
    }
)
class ColearnLightRAGTool(Tool, ContextAware):
    def __init__(
        self,
        *,
        request: LearningTurnRequest,
        workspace: Path | None = None,
        retrieval_service: RetrievalService | None = None,
    ) -> None:
        self._request_var: ContextVar[LearningTurnRequest] = ContextVar("colearn_lightrag_request", default=request)
        self._workspace = workspace or Path.cwd()
        self._retrieval_service = retrieval_service
        self._context_var: ContextVar[RequestContext | None] = ContextVar("colearn_lightrag_context", default=None)

    def bind_request(
        self,
        *,
        request: LearningTurnRequest,
        workspace: Path | None = None,
        retrieval_service: RetrievalService | None = None,
    ) -> None:
        self._request_var.set(request)
        if workspace is not None:
            self._workspace = workspace
        self._retrieval_service = retrieval_service

    def set_context(self, ctx: RequestContext) -> None:
        self._context_var.set(ctx)

    @property
    def name(self) -> str:
        return "lightrag"

    @property
    def description(self) -> str:
        return "Retrieve project knowledge context with LightRAG when the current turn needs external knowledge."

    async def execute(self, **kwargs: Any) -> Any:
        request = self._request_var.get()
        try:
            question = str(kwargs.get("question") or "").strip() or request.user_message
            if self._retrieval_service is not None:
                bundle = await self._retrieval_service.async_build_bundle_for_source_refs(
                    project_id=request.project_id,
                    query=question,
                    source_refs=[
                        str(item.get("source_ref") or item.get("source_path") or "")
                        for item in request.source_references
                        if str(item.get("source_ref") or item.get("source_path") or "")
                    ],
                )
                evidence = _normalize_evidence_rows(
                    source_rows=list(bundle.references or []),
                    active_node_id=str(request.board_facts.current_progress.active_node_id or ""),
                )
                return {
                    "status": bundle.retrieval_status,
                    "source_refs": len(bundle.references or []),
                    "warnings": list(bundle.warnings or []),
                    "fallback_reason": bundle.fallback_reason,
                    "text": bundle.text,
                    **evidence,
                }

            client = get_lightrag_client(workspace=self._workspace)
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
            evidence = _normalize_evidence_rows(
                source_rows=list(result.references or []),
                active_node_id=str(request.board_facts.current_progress.active_node_id or ""),
            )
            return {
                "status": result.retrieval_status,
                "source_refs": len(result.references or []),
                "warnings": warnings,
                "fallback_reason": result.fallback_reason,
                "text": result.text,
                **evidence,
            }
        except (RuntimeError, ValueError, KeyError, OSError, ConnectionError) as exc:
            return {
                "status": "error",
                "source_refs": 0,
                "warnings": [str(exc)],
                "fallback_reason": "tool_exception",
                "text": "",
                "evidence_refs": [],
                "evidence_map": {},
                "message": f"LightRAG context unavailable: {exc}",
            }


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Number of results (max 5)", "default": 5},
        },
        "required": ["query"],
    }
)
class ColearnWebSearchTool(Tool):
    def __init__(self, *, request: LearningTurnRequest) -> None:
        self._request_var: ContextVar[LearningTurnRequest] = ContextVar("colearn_websearch_request", default=request)

    def bind_request(self, *, request: LearningTurnRequest) -> None:
        self._request_var.set(request)

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for current information using Brave Search. Use when the user asks about recent events or when local knowledge is insufficient."

    async def execute(self, **kwargs: Any) -> Any:
        import os
        import httpx

        query = str(kwargs.get("query") or "").strip()
        if not query:
            return {"status": "error", "message": "Empty query", "results": []}

        api_key = os.environ.get("BRAVE_API_KEY", "")
        if not api_key:
            from colearn.api.state import SettingsStateService
            import colearn.api.dependencies as _deps
            svc = getattr(_deps, "settings_service", None)
            if isinstance(svc, SettingsStateService):
                env_block = svc.web_search_env()
                api_key = str(env_block.get("BRAVE_API_KEY") or "")

        if not api_key:
            return {
                "status": "unavailable",
                "message": "Brave Search API key not configured. Answer using general knowledge.",
                "results": [],
            }

        count = min(int(kwargs.get("count") or 5), 5)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": count},
                    headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
                )
                if resp.status_code != 200:
                    return {
                        "status": "error",
                        "message": f"Brave API returned {resp.status_code}",
                        "results": [],
                    }
                data = resp.json()
                web_results = data.get("web", {}).get("results", [])
                results = [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "description": r.get("description", ""),
                    }
                    for r in web_results[:count]
                ]
                return {"status": "success", "query": query, "results": results}
        except (httpx.HTTPError, OSError, ValueError) as exc:
            return {
                "status": "error",
                "message": f"Web search failed: {exc}",
                "results": [],
            }


def install_colearn_tools(
    *,
    bot: Any,
    request: LearningTurnRequest,
    workspace: Path | None = None,
    retrieval_service: RetrievalService | None = None,
    memory_store: EventMemoryStore | None = None,
) -> None:
    register_colearn_tools(
        bot=bot,
        request=request,
        workspace=workspace,
        retrieval_service=retrieval_service,
        memory_store=memory_store,
    )
    bind_colearn_tools(
        bot=bot,
        request=request,
        workspace=workspace,
        retrieval_service=retrieval_service,
        memory_store=memory_store,
    )


def register_colearn_tools(
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
    if not {"memory", "lightrag", "web_search"} & enabled:
        return

    registry = _resolve_tool_registry(bot=bot, request=request)

    if "memory" in enabled:
        existing_memory = _registry_get(registry, "memory")
        if existing_memory is None:
            registry.register(
                ColearnMemoryTool(
                    request=request,
                    memory_store=memory_store,
                )
            )
        elif not isinstance(existing_memory, ColearnMemoryTool):
            registry.unregister("memory")
            registry.register(
                ColearnMemoryTool(
                    request=request,
                    memory_store=memory_store,
                )
            )
    elif registry.has("memory"):
        registry.unregister("memory")

    if "lightrag" in enabled:
        existing_lightrag = _registry_get(registry, "lightrag")
        if existing_lightrag is None:
            registry.register(
                ColearnLightRAGTool(
                    request=request,
                    workspace=workspace,
                    retrieval_service=retrieval_service,
                )
            )
        elif not isinstance(existing_lightrag, ColearnLightRAGTool):
            registry.unregister("lightrag")
            registry.register(
                ColearnLightRAGTool(
                    request=request,
                    workspace=workspace,
                    retrieval_service=retrieval_service,
                )
            )
    elif registry.has("lightrag"):
        registry.unregister("lightrag")

    if "web_search" in enabled:
        existing_ws = _registry_get(registry, "web_search")
        if existing_ws is None:
            registry.register(ColearnWebSearchTool(request=request))
        elif not isinstance(existing_ws, ColearnWebSearchTool):
            registry.unregister("web_search")
            registry.register(ColearnWebSearchTool(request=request))
    elif registry.has("web_search"):
        registry.unregister("web_search")


def bind_colearn_tools(
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
    if not {"memory", "lightrag", "web_search"} & enabled:
        return

    registry = _resolve_tool_registry(bot=bot, request=request)

    if "memory" in enabled:
        memory_tool = _registry_get(registry, "memory")
        if isinstance(memory_tool, ColearnMemoryTool):
            memory_tool.bind_request(
                request=request,
                memory_store=memory_store,
            )

    if "lightrag" in enabled:
        lightrag_tool = _registry_get(registry, "lightrag")
        if isinstance(lightrag_tool, ColearnLightRAGTool):
            lightrag_tool.bind_request(
                request=request,
                workspace=workspace,
                retrieval_service=retrieval_service,
            )

    if "web_search" in enabled:
        ws_tool = _registry_get(registry, "web_search")
        if isinstance(ws_tool, ColearnWebSearchTool):
            ws_tool.bind_request(request=request)
