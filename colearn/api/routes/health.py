"""Health and system status routes."""

from __future__ import annotations

import os
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


@router.get("/api/v1/system/lightrag-health")
def lightrag_health() -> dict[str, Any]:
    """Check LightRAG server connectivity by directly pinging the HTTP endpoint."""
    import json as _json
    from pathlib import Path
    from urllib.request import urlopen, Request
    from urllib.error import URLError

    repo_root = Path(os.environ.get("COLEARN_REPO_ROOT", "."))
    config_path = repo_root / ".colearn" / "lightrag.json"

    if not config_path.exists():
        return {"status": "unavailable", "reason": "no_config_file"}

    try:
        config = _json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError):
        return {"status": "unavailable", "reason": "config_parse_error"}

    if not config.get("enabled"):
        return {"status": "disabled", "reason": "lightrag_disabled_in_config"}

    provider = config.get("provider", {})
    if isinstance(provider, dict):
        provider_name = provider.get("name", "local")
        base_url = provider.get("base_url", "http://127.0.0.1:9621")
    else:
        provider_name = str(provider)
        base_url = "http://127.0.0.1:9621"

    if provider_name == "lightrag_hku":
        return {"status": "healthy", "reason": "in_process_mode"}

    try:
        req = Request(f"{base_url.rstrip('/')}/health", method="GET")
        with urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                return {"status": "healthy", "reason": ""}
            return {"status": "unreachable", "reason": f"status_{resp.status}"}
    except (URLError, OSError, TimeoutError) as exc:
        return {"status": "unreachable", "reason": str(exc)}
