"""FinalizeStage — pure data shaping; no service calls."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from colearn.learning.state_hooks import build_retrieval_evidence_map
from colearn.runtime_v2.result_bridge import normalize_learning_turn_result

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
        retrieval_hits, retrieval_misses, retrieval_evidence_map = self._build_retrieval_writeback_fields(
            request=ctx.compressed.request,
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
        ctx.result = normalize_learning_turn_result(
            request=request_with_metadata,
            final_text=ctx.result.final_text,
            learning_result=dict(ctx.result.raw_learning_result or {}),
        )
        ctx.retrieval_hits = retrieval_hits
        ctx.retrieval_misses = retrieval_misses
        ctx.retrieval_evidence_map = retrieval_evidence_map
        ctx.request_with_metadata = request_with_metadata
        return ctx

    # ------------------------------------------------------------------
    # Internals (lifted verbatim from LearningOrchestrator)
    # ------------------------------------------------------------------
    def _build_retrieval_writeback_fields(
        self,
        *,
        request,
        retrieval_context: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
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
        return retrieval_hits, retrieval_misses, retrieval_evidence_map

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
        retrieval_metadata = {
            "focus": retrieval_focus,
            "query_context": retrieval_query_context,
            "reason": retrieval_reason,
            "prefetched_references": prefetched_references,
            "parallel_support": parallel_support,
            "prompt_support_bundle": prompt_support_bundle,
            "hits": retrieval_hits,
            "misses": retrieval_misses,
            "evidence_map": retrieval_evidence_map,
        }
        return replace(
            request,
            metadata={
                **dict(request.metadata or {}),
                "retrieval": retrieval_metadata,
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
            "runtime_v2": runtime_v2,
            "continuation_retrieval_hint": dict(retrieval_payload.get("continuation_retrieval_hint") or {}),
        }
