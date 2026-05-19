"""Minimal FastAPI + WebSocket entrypoint for the CoLearn backend."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

import colearn.api.dependencies as _deps
from colearn.api.dependencies import (
    auth_service,
    knowledge_task_service,
    memory_doc_service,
    orchestrator,
    project_service,
    session_store,
    settings_service,
    settings_test_service,
    state_store,
    turn_cache,
    AUTH_COOKIE_NAME,
    WORKSPACE_SKILLS_DIR,
)
from colearn.api.routes.auth import router as auth_router
from colearn.api.routes.health import router as health_router
from colearn.api.routes.knowledge import router as knowledge_router
from colearn.api.routes.memory import router as memory_router
from colearn.api.routes.projects import router as projects_router
from colearn.api.routes.sessions import router as sessions_router
from colearn.api.routes.settings import router as settings_router
from colearn.api.routes.skills import router as skills_router
from colearn.api.routes.websocket import (
    router as websocket_router,
    WS_HANDLERS,
    handle_ping,
    handle_subscribe_turn,
    _prepare_runtime_stream_events,
)
from colearn.logging_config import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    try:
        _deps.orchestrator.shutdown(timeout=5.0)
    except Exception as exc:
        logger.warning("orchestrator.shutdown failed: %s", exc)
    try:
        _deps.turn_cache.clear()
    except Exception as exc:
        logger.warning("turn_cache.clear failed: %s", exc)


app = FastAPI(title="CoLearn API", version="0.1.0", lifespan=lifespan)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(skills_router)
app.include_router(memory_router)
app.include_router(projects_router)
app.include_router(sessions_router)
app.include_router(knowledge_router)
app.include_router(websocket_router)


# Support test monkey-patching: when tests set `app_module.orchestrator = X`,
# propagate the change to the dependencies module so route handlers see it.
_SYNCED_ATTRS = frozenset({"orchestrator", "session_store", "turn_cache", "project_service"})
_this = sys.modules[__name__]


class _ModuleProxy(sys.modules[__name__].__class__):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if name in _SYNCED_ATTRS:
            setattr(_deps, name, value)


_this.__class__ = _ModuleProxy