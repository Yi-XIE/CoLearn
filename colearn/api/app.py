"""Minimal FastAPI entrypoint for the CoLearn backend."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

import colearn.api.dependencies as _deps
from colearn.api.dependencies import (
    knowledge_task_service,
    memory_doc_service,
    orchestrator,
    project_service,
    session_store,
    settings_service,
    state_store,
)
from colearn.api.routes.health import router as health_router
from colearn.api.routes.knowledge import router as knowledge_router
from colearn.api.routes.memory import router as memory_router
from colearn.api.routes.projects import router as projects_router
from colearn.api.routes.sessions import router as sessions_router
from colearn.api.routes.settings import router as settings_router
from colearn.api.routes.skills import router as skills_router
from colearn.api.ws_handler import router as ws_router
from colearn.logging_config import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    try:
        _deps.orchestrator.shutdown(timeout=5.0)
    except (RuntimeError, OSError) as exc:
        logger.warning("orchestrator.shutdown failed: %s", exc)


app = FastAPI(title="CoLearn API", version="0.1.0", lifespan=lifespan)

from colearn.api.middleware import RequestIdMiddleware
app.add_middleware(RequestIdMiddleware)

app.include_router(health_router)
app.include_router(settings_router)
app.include_router(skills_router)
app.include_router(memory_router)
app.include_router(projects_router)
app.include_router(sessions_router)
app.include_router(knowledge_router)
app.include_router(ws_router)


def override_dependency(name: str, value: object) -> None:
    """Explicitly sync a dependency override to the shared deps module.

    Use in tests instead of monkey-patching module attributes directly.
    """
    _SYNCED_ATTRS = {"orchestrator", "session_store", "project_service"}
    if name not in _SYNCED_ATTRS:
        raise ValueError(f"unknown dependency: {name!r}")
    setattr(_deps, name, value)
    globals()[name] = value