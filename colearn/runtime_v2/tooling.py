"""CoLearn tool wiring for the nanobot v0.2 runtime line."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from colearn.learning.turn_contract import LearningTurnRequest
from colearn.memory.store import EventMemoryStore
from colearn.retrieval.adapters import get_lightrag_client
from colearn.retrieval.service import RetrievalService
from colearn.runtime_v2.tool_adapters import normalize_enabled_tools

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
                except Exception as exc:
                    return {
                        "status": "error",
                        "evidence_refs": [],
                        "evidence_map": {},
                        "message": f"Memory context unavailable: {exc}",
                    }

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
                except Exception as exc:
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

        registry.register(ColearnLightRAGTool())
