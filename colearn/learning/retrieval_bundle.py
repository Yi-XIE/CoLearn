"""Retrieval bundle contracts for standalone CoLearn turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from typing import Any

RetrievalStatus = Literal["ready", "empty", "unavailable", "indexing", "error"]


@dataclass(frozen=True)
class RetrievalChunk:
    text: str
    source_ref: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalBundle:
    query: str
    text: str
    references: list[dict[str, Any]] = field(default_factory=list)
    chunks: list[RetrievalChunk] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    retrieval_status: RetrievalStatus = "unavailable"
    fallback_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_hits(self) -> bool:
        return bool(self.text.strip() or self.chunks or self.references)


def empty_retrieval_bundle(
    *,
    query: str = "",
    warning: str | None = None,
    status: RetrievalStatus = "unavailable",
    fallback_reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> RetrievalBundle:
    warnings = [warning] if warning else []
    return RetrievalBundle(
        query=query,
        text="",
        warnings=warnings,
        retrieval_status=status,
        fallback_reason=fallback_reason,
        metadata=metadata or {},
    )
