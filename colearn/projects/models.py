"""Minimal project models for standalone CoLearn assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LearningProject:
    project_id: str
    title: str
    goal: str = ""
    source_refs: list[str] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)
    turn_mode: str = "EXPLORE"
    board_facts: dict[str, Any] = field(default_factory=dict)
    board_version: int = 1
    anchor: dict[str, str] = field(default_factory=dict)
    anchor_status: str = "missing"
    source_subset: list[str] = field(default_factory=list)
    latest_review: dict[str, Any] = field(default_factory=dict)
    current_main_goal: str = ""
    retrieval_profile: dict[str, Any] = field(default_factory=dict)
