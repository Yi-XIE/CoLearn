"""Runtime compression for turn context capacity control."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from colearn.learning.retrieval_bundle import RetrievalBundle, RetrievalChunk
from colearn.learning.turn_contract import LearningTurnRequest


@dataclass(frozen=True)
class RuntimeCompressionResult:
    request: LearningTurnRequest
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeCompressionBridge:
    def __init__(
        self,
        *,
        max_retrieval_chars: int = 4000,
        max_chunk_chars: int = 1200,
        max_user_message_chars: int = 3000,
    ) -> None:
        self.max_retrieval_chars = max_retrieval_chars
        self.max_chunk_chars = max_chunk_chars
        self.max_user_message_chars = max_user_message_chars

    def compress(self, *, request: LearningTurnRequest) -> RuntimeCompressionResult:
        notes: list[str] = []
        metadata = dict(request.metadata)

        user_message = request.user_message
        if len(user_message) > self.max_user_message_chars:
            user_message = f"{user_message[: self.max_user_message_chars].rstrip()}..."
            notes.append("user_message_truncated")

        retrieval_bundle = request.retrieval_bundle
        compressed_bundle = retrieval_bundle
        if retrieval_bundle.text and len(retrieval_bundle.text) > self.max_retrieval_chars:
            compressed_text = f"{retrieval_bundle.text[: self.max_retrieval_chars].rstrip()}..."
            compressed_chunks = [
                RetrievalChunk(
                    text=(
                        f"{chunk.text[: self.max_chunk_chars].rstrip()}..."
                        if len(chunk.text) > self.max_chunk_chars
                        else chunk.text
                    ),
                    source_ref=chunk.source_ref,
                    source_path=chunk.source_path,
                    score=chunk.score,
                    metadata=chunk.metadata,
                )
                for chunk in retrieval_bundle.chunks
            ]
            compressed_bundle = RetrievalBundle(
                query=retrieval_bundle.query,
                text=compressed_text,
                references=retrieval_bundle.references,
                chunks=compressed_chunks,
                warnings=[*retrieval_bundle.warnings, "retrieval_text_truncated"],
                retrieval_status=retrieval_bundle.retrieval_status,
                fallback_reason=retrieval_bundle.fallback_reason,
                metadata={
                    **retrieval_bundle.metadata,
                    "runtime_compressed": True,
                },
            )
            notes.append("retrieval_truncated")

        metadata["runtime_compression_notes"] = notes
        compressed_request = LearningTurnRequest(
            session_id=request.session_id,
            turn_id=request.turn_id,
            user_message=user_message,
            language=request.language,
            project_id=request.project_id,
            project_title=request.project_title,
            turn_mode=request.turn_mode,
            board_facts=request.board_facts,
            turn_policy=request.turn_policy,
            anchor=request.anchor,
            source_references=request.source_references,
            memory_references=request.memory_references,
            retrieval_bundle=compressed_bundle,
            state_projection=request.state_projection,
            policy_decision=request.policy_decision,
            continuation_prompt=request.continuation_prompt,
            model_preset=request.model_preset,
            enabled_tools=request.enabled_tools,
            attachments=request.attachments,
            requested_skills=request.requested_skills,
            metadata=metadata,
        )
        return RuntimeCompressionResult(
            request=compressed_request,
            notes=notes,
            metadata={"retrieval_status": compressed_bundle.retrieval_status},
        )
