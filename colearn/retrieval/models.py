"""Retrieval-facing source reference models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceRef:
    ref_id: str
    title: str = ""
    path: str = ""
    kind: str = "file"
    metadata: dict[str, Any] = field(default_factory=dict)
