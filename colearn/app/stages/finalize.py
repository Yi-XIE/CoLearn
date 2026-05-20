"""FinalizeStage — pure data shaping; no service calls."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from colearn.learning.state_hooks import build_retrieval_evidence_map

from .context import TurnContext


class FinalizeStage:
    """Enrich the executor's result and decorate the request with retrieval metadata.

    Holds no services — every method here transforms in-memory dicts.
    """

    def __init__(self) -> None:  # placeholder for symmetry with the other stages
        pass

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def run(self, ctx: TurnContext) -> TurnContext:
        retrieval_context = ctx.retrieval_context()
        normalized, retrieval_hits, retrieval_misses, retrieval_evidence_map = self._enrich_turn_result(
            request=ctx.compressed.request,
            result=ctx.result,
            retrieval_context=retrieval_context,
        )
        request_with_metadata = self._attach_retrieval_metadata(
            ctx.compressed.request,
            retrieval_focus=retrieval_context["retrieval_focus"],
            retrieval_query_context=retrieval_context["retrieval_query_context"],
            retrieval_reason=retrieval_context["retrieval_reason"],
            prefetched_references=retrieval_context["prefetched_references"],
            parallel_support=retrieval_context["parallel_support"],
            prompt_support_bundle=retrieval_context["prompt_support_bundle"],
            retrieval_hits=retrieval_hits,
            retrieval_misses=retrieval_misses,
            retrieval_evidence_map=retrieval_evidence_map,
        )
        ctx.result = normalized
        ctx.retrieval_hits = retrieval_hits
        ctx.retrieval_misses = retrieval_misses
        ctx.retrieval_evidence_map = retrieval_evidence_map
        ctx.request_with_metadata = request_with_metadata
        return ctx

    # ------------------------------------------------------------------
    # Internals (lifted verbatim from LearningOrchestrator)
    # ------------------------------------------------------------------
    def _enrich_turn_result(
        self,
        *,
        request,
        result,
        retrieval_context: dict[str, Any],
    ) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        retrieval_evidence_map = build_retrieval_evidence_map(
            board=request.board_facts,
            prefetched_references=retrieval_context["prefetched_references"],
            prompt_support_bundle=retrieval_context["prompt_support_bundle"],
        )
        retrieval_hits, retrieval_misses, retrieval_evidence_map = self._build_retrieval_writeback(
            request=request,
            retrieval_focus=retrieval_context["retrieval_focus"],
            retrieval_evidence_map=retrieval_evidence_map,
        )
        runtime_v2 = dict((result.raw_learning_result or {}).get("runtime_v2") or {})
        runtime_v2["retrieval"] = self._build_runtime_retrieval_payload(
            board=request.board_facts,
            retrieval_context=retrieval_context,
            retrieval_hits=retrieval_hits,
            retrieval_misses=retrieval_misses,
            retrieval_evidence_map=retrieval_evidence_map,
        )
        runtime_v2["parallel_support"] = retrieval_context["parallel_support"]
        enriched_learning_result = {
            **dict(result.raw_learning_result or {}),
            "retrieval_hits": retrieval_hits,
            "retrieval_misses": retrieval_misses,
            "retrieval_evidence_map": retrieval_evidence_map,
            "prompt_support_bundle": retrieval_context["prompt_support_bundle"],
            "retrieval_query_context": retrieval_context["retrieval_query_context"],
            "runtime_v2": runtime_v2,
        }
        return (
            replace(result, raw_learning_result=enriched_learning_result),
            retrieval_hits,
            retrieval_misses,
            retrieval_evidence_map,
        )

    def _build_runtime_retrieval_payload(
        self,
        *,
        board,
        retrieval_context: dict[str, Any],
        retrieval_hits: list[dict[str, Any]],
        retrieval_misses: list[dict[str, Any]],
        retrieval_evidence_map: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        return {
            "prefetched_references": retrieval_context["prefetched_references"],
            "prompt_support_bundle": retrieval_context["prompt_support_bundle"],
            "retrieval_focus": retrieval_context["retrieval_focus"],
            "retrieval_query_context": retrieval_context["retrieval_query_context"],
            "retrieval_reason": retrieval_context["retrieval_reason"],
            "retrieval_hits": retrieval_hits,
            "retrieval_misses": retrieval_misses,
            "retrieval_evidence_map": retrieval_evidence_map,
            "knowledge_support_summary": {
                "active_node_id": board.current_progress.active_node_id,
                "critical_blockers": [blocker.id for blocker in board.gaps_and_blockers.critical_blockers],
                "evidence_ref_count": len(board.evidence_refs or []),
                "retrieval_hit_count": len(retrieval_hits),
            },
            "blocker_support_refs": {
                blocker.id: list(retrieval_evidence_map.get(blocker.id, []))
                for blocker in board.gaps_and_blockers.critical_blockers
            },
            "continuation_retrieval_hint": {
                "active_node_id": board.current_progress.active_node_id,
                "evidence_refs": list(board.evidence_refs or []),
                "retrieval_focus": retrieval_context["retrieval_focus"],
                "retrieval_query_context": retrieval_context["retrieval_query_context"],
            },
        }

    def _build_retrieval_writeback(
        self,
        *,
        request,
        retrieval_focus: dict[str, Any],
        retrieval_evidence_map: dict[str, list[dict[str, Any]]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        evidence_map = {key: list(value or []) for key, value in retrieval_evidence_map.items()}
        hits: list[dict[str, Any]] = []
        misses: list[dict[str, Any]] = []
        board = request.board_facts
        active_node_id = str(board.current_progress.active_node_id or "").strip()
        blocker_ids = [
            str(item.id or "").strip()
            for item in board.gaps_and_blockers.critical_blockers
            if str(item.id or "").strip()
        ]
        ordered_keys = [active_node_id, *blocker_ids]
        for key in ordered_keys:
            for item in evidence_map.get(key, []):
                if item not in hits:
                    hits.append(item)
        if not hits:
            for key, values in evidence_map.items():
                if str(key).startswith("chunk:"):
                    continue
                for item in values:
                    if item not in hits:
                        hits.append(item)
        if not hits:
            misses.append(
                {
                    "reason": "no_prefetched_references",
                    "retrieval_focus": retrieval_focus,
                }
            )
        ordered_evidence_map: dict[str, list[dict[str, Any]]] = {}
        for key in [*ordered_keys, *sorted(k for k in evidence_map.keys() if k.startswith("chunk:"))]:
            if key in evidence_map:
                ordered_evidence_map[key] = list(evidence_map[key])
        for key in sorted(k for k in evidence_map.keys() if k not in ordered_evidence_map):
            ordered_evidence_map[key] = list(evidence_map[key])
        return hits, misses, ordered_evidence_map

    def _attach_retrieval_metadata(
        self,
        request,
        *,
        retrieval_focus: dict[str, Any],
        retrieval_query_context: dict[str, Any],
        retrieval_reason: str,
        prefetched_references: list[dict[str, Any]],
        parallel_support: dict[str, Any],
        prompt_support_bundle: list[dict[str, Any]],
        retrieval_hits: list[dict[str, Any]],
        retrieval_misses: list[dict[str, Any]],
        retrieval_evidence_map: dict[str, list[dict[str, Any]]],
    ):
        return replace(
            request,
            metadata={
                **dict(request.metadata or {}),
                "retrieval_focus": retrieval_focus,
                "retrieval_query_context": retrieval_query_context,
                "retrieval_reason": retrieval_reason,
                "prefetched_references": prefetched_references,
                "parallel_support": parallel_support,
                "prompt_support_bundle": prompt_support_bundle,
                "retrieval_hits": retrieval_hits,
                "retrieval_misses": retrieval_misses,
                "retrieval_evidence_map": retrieval_evidence_map,
            },
        )

    # ------------------------------------------------------------------
    # Used by WritebackStage to populate `session.last_turn_result`.
    # ------------------------------------------------------------------
    def build_last_turn_result(
        self,
        *,
        request,
        result,
        warnings: list[str],
        base_version: int,
        include_product_compression: bool,
    ) -> dict[str, Any]:
        payload = self._build_retrieval_result_fields(
            request=request,
            result=result,
        )
        last_turn_result = {
            "final_text": result.final_text,
            "warnings": warnings,
            "board_patch": result.board_patch,
            "tool_events": list(result.tool_events),
            "stream_events": list(result.stream_events),
            **payload,
            "turn_mode_before": result.turn_mode_before,
            "turn_mode_after": result.turn_mode_after,
            "base_board_version": int(getattr(request.board_facts, "board_version", base_version) or 1),
            "resolved_board_version": int(getattr(result.board_after, "board_version", base_version) or 1),
        }
        if include_product_compression:
            last_turn_result["product_compression"] = {
                "status": "scheduled",
                "started_at": None,
                "finished_at": None,
                "error": "",
                "base_board_version": int(base_version or 1),
            }
        return last_turn_result

    def _build_retrieval_result_fields(
        self,
        *,
        request,
        result,
    ) -> dict[str, Any]:
        runtime_v2 = dict((result.raw_learning_result or {}).get("runtime_v2") or {})
        retrieval_payload = dict(runtime_v2.get("retrieval") or {})
        return {
            "raw_learning_result": dict(result.raw_learning_result or {}),
            "runtime_v2": runtime_v2,
            "prompt_support_bundle": list(
                retrieval_payload.get("prompt_support_bundle")
                or (result.raw_learning_result or {}).get("prompt_support_bundle")
                or []
            ),
            "retrieval_query_context": dict(
                retrieval_payload.get("retrieval_query_context")
                or (result.raw_learning_result or {}).get("retrieval_query_context")
                or {}
            ),
            "knowledge_support_summary": dict(
                retrieval_payload.get("knowledge_support_summary")
                or (result.raw_learning_result or {}).get("knowledge_support_summary")
                or {}
            ),
            "blocker_support_refs": dict(
                retrieval_payload.get("blocker_support_refs")
                or (result.raw_learning_result or {}).get("blocker_support_refs")
                or {}
            ),
            "continuation_retrieval_hint": dict(
                retrieval_payload.get("continuation_retrieval_hint")
                or (result.raw_learning_result or {}).get("continuation_retrieval_hint")
                or {}
            ),
            "retrieval_hits": list(
                retrieval_payload.get("retrieval_hits")
                or (result.raw_learning_result or {}).get("retrieval_hits")
                or []
            ),
            "retrieval_misses": list(
                retrieval_payload.get("retrieval_misses")
                or (result.raw_learning_result or {}).get("retrieval_misses")
                or []
            ),
            "retrieval_evidence_map": dict(
                retrieval_payload.get("retrieval_evidence_map")
                or (result.raw_learning_result or {}).get("retrieval_evidence_map")
                or {}
            ),
            "writeback_envelope": dict((result.raw_learning_result or {}).get("writeback_envelope") or {}),
        }
