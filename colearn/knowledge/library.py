"""Minimal source-library model for standalone CoLearn knowledge assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceLibrary:
    library_id: str
    name: str
    source_paths: list[str] = field(default_factory=list)
    retrieval_status: str = "unavailable"
    warnings: list[str] = field(default_factory=list)
    indexed_paths: list[str] = field(default_factory=list)
    source_status: dict[str, dict[str, Any]] = field(default_factory=dict)
