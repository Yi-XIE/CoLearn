"""Shared service singletons for the CoLearn API layer."""

from __future__ import annotations

from pathlib import Path

from colearn.api.state import (
    KnowledgeTaskService,
    MemoryDocStateService,
    SettingsStateService,
    SettingsTestRunService,
)
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

settings_service = SettingsStateService(JsonStateStore(state_store.root), colearn_env_file())
memory_doc_service = MemoryDocStateService()
knowledge_task_service = KnowledgeTaskService(state_root=state_store.root)
settings_test_service = SettingsTestRunService()

WORKSPACE_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
