"""Shared service singletons for the CoLearn API layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from colearn.api.state import (
    AuthStateService,
    KnowledgeTaskService,
    MemoryDocStateService,
    SettingsStateService,
    SettingsTestRunService,
)
from colearn.api.turn_cache import RecentTurnReplayCache
from colearn.app.learning_orchestrator import LearningOrchestrator
from colearn.paths import colearn_env_file
from colearn.projects.service import LearningProjectService
from colearn.sessions.store import SessionStore
from colearn.storage import JsonStateStore
from colearn.storage.project_session_store import (
    build_stateful_memory_store,
    build_stateful_project_service,
    build_stateful_session_store,
)

state_store = JsonStateStore()
project_service = build_stateful_project_service(state_store.root)
session_store = build_stateful_session_store(state_store.root)
orchestrator = LearningOrchestrator(
    project_service=project_service,
    session_store=session_store,
    memory_store=build_stateful_memory_store(state_store.root),
)

turn_cache = RecentTurnReplayCache(max_turns=128)

# Tracks in-flight turns for cancellation. Maps turn_id → cancel flag dict
# {"cancelled": bool}. When user sends cancel_turn, the flag flips and the
# WebSocket loop stops forwarding events even though the orchestrator thread
# may still be running (nanobot doesn't expose mid-run cancellation).
active_turns: dict[str, dict[str, Any]] = {}

settings_service = SettingsStateService(JsonStateStore(state_store.root), colearn_env_file())
memory_doc_service = MemoryDocStateService()
auth_service = AuthStateService(JsonStateStore(state_store.root))
knowledge_task_service = KnowledgeTaskService(state_root=state_store.root)
settings_test_service = SettingsTestRunService()

AUTH_COOKIE_NAME = "colearn_session"
WORKSPACE_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
