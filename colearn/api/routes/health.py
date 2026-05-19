"""Health and system status routes."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from colearn.api.dependencies import settings_service

router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@router.get("/api/v1/system/status")
def system_status() -> dict[str, Any]:
    catalog = settings_service.catalog()
    services = dict(catalog.get("services") or {})
    llm_profile, llm_model = settings_service._resolve_active_selection(services.get("llm"))
    embedding_profile, embedding_model = settings_service._resolve_active_selection(services.get("embedding"))
    return {
        "backend": {"status": "running", "timestamp": str(int(time.time()))},
        "llm": {"status": "ready", "model": str(llm_model.get("model") or "")},
        "embeddings": {"status": "ready", "model": str(embedding_model.get("model") or "")},
        "search": {"status": "ready", "provider": "brave"},
        "services": {
            "api": "ready",
            "sessions": "in_memory",
            "projects": "in_memory",
            "retrieval": "tool_mode",
        },
    }
