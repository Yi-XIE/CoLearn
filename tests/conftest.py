from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NANOBOT_CORE = ROOT / "third_party" / "nanobot-core"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if str(NANOBOT_CORE) not in sys.path:
    sys.path.insert(0, str(NANOBOT_CORE))

import pytest

from colearn.learning.constants import CognitiveLoad
from colearn.learning.response_contract import LearningTurnResult
from colearn.learning.state import BoardFacts, GapsAndBlockers, ProgressFacts, StudentSnapshot
from colearn.learning.turn_contract import LearningTurnRequest
from colearn.runtime_v2.result_bridge import normalize_learning_turn_result


@pytest.fixture
def anyio_backend() -> str:
    # ``anyio_mode = auto`` (pytest.ini) runs every ``async def`` test through
    # anyio's pytest plugin; this fixture pins the backend to asyncio.
    return "asyncio"


@dataclass
class FakeExecutor:
    last_request: Any = None
    workspace: Any = None

    def _make_result(self, request: LearningTurnRequest) -> LearningTurnResult:
        self.last_request = request
        return LearningTurnResult(
            final_text=f"Answering: {request.user_message}",
            board_before=request.board_facts,
            board_after=request.board_facts,
            turn_mode_before=request.metadata.get("turn_mode_before", "LEARN"),
            turn_mode_after=request.turn_mode,
            retrieval_bundle=request.retrieval_bundle,
            raw_learning_result={"tool_events": [], "raw_messages": []},
        )

    async def run_turn_async(self, *, request: LearningTurnRequest) -> LearningTurnResult:
        return self._make_result(request)

    def finalize(
        self,
        *,
        request: LearningTurnRequest,
        final_text: str,
        learning_result: dict | None = None,
    ) -> LearningTurnResult:
        return normalize_learning_turn_result(
            request=request,
            final_text=final_text,
            learning_result=learning_result,
        )

    def sync_sustained_goal(self, *, session_id: str, objective: str, ui_summary: str = "") -> dict:
        return {"status": "active_started", "session_id": session_id, "objective": objective}

    def complete_sustained_goal(self, *, session_id: str, recap: str = "") -> dict:
        return {"status": "completed", "session_id": session_id, "recap": recap}


class FakeRetrievalService:
    def __init__(self) -> None:
        self.last_bundle_query = ""

    def sync_source_refs(self, *, project_id: str, source_refs: list[str], libraries=None):
        return {
            "project_id": project_id,
            "enabled": True,
            "synced": bool(source_refs),
            "source_count": len(source_refs),
            "indexed_paths": list(source_refs),
            "sync_status": "synced" if source_refs else "empty",
            "warnings": [],
        }

    async def async_sync_source_refs(self, *, project_id: str, source_refs: list[str], libraries=None):
        return self.sync_source_refs(
            project_id=project_id, source_refs=source_refs, libraries=libraries
        )

    def build_bundle(self, *, project, session, query: str, libraries=None):
        self.last_bundle_query = query
        return SimpleNamespace(
            query=query,
            text="prefetched support",
            references=[{"source_ref": "source-1", "source_path": "/fake/source-1.md", "title": "Source 1"}],
            chunks=[],
            warnings=[],
            retrieval_status="ready",
            fallback_reason=None,
            metadata={},
        )

    def build_bundle_for_source_refs(self, *, project_id, query, source_refs, libraries=None):
        return self.build_bundle(project=None, session=None, query=query, libraries=libraries)

    async def async_build_bundle_for_source_refs(self, *, project_id, query, source_refs, libraries=None):
        return self.build_bundle(project=None, session=None, query=query, libraries=libraries)


def make_board(**overrides) -> BoardFacts:
    """Create a BoardFacts with sensible defaults for testing."""
    defaults = {
        "board_version": 1,
        "current_turn_mode": "LEARN",
        "current_progress": ProgressFacts(active_node_id="node-1"),
        "gaps_and_blockers": GapsAndBlockers(critical_blockers=[]),
        "student_snapshot": StudentSnapshot(mastery_level=0.3, cognitive_load=CognitiveLoad.NORMAL),
        "evidence_refs": [],
    }
    defaults.update(overrides)
    return BoardFacts(**defaults)


@pytest.fixture
def fake_executor():
    return FakeExecutor()


@pytest.fixture
def fake_retrieval():
    return FakeRetrievalService()


@pytest.fixture
def board():
    return make_board()
