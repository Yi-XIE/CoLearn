"""Settings routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from colearn.api.dependencies import settings_service
from colearn.api.schemas import SettingsCatalogPayload, SettingsUiPayload

router = APIRouter()


def _message_sse(events: list[dict[str, Any]]):
    def generate():
        for item in events:
            payload = json.dumps(item, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/api/v1/settings")
def get_settings() -> dict[str, Any]:
    return settings_service.settings()


@router.get("/api/v1/settings/catalog")
def get_settings_catalog() -> dict[str, Any]:
    return {"catalog": settings_service.catalog()}


@router.get("/api/v1/settings/providers")
def get_settings_providers() -> dict[str, Any]:
    return {"providers": settings_service.providers()}


@router.get("/api/v1/settings/llm-options")
def get_llm_options() -> dict[str, Any]:
    catalog = settings_service.catalog()
    llm = dict((catalog.get("services") or {}).get("llm") or {})
    profiles = list(llm.get("profiles") or [])
    active = {
        "profile_id": str(llm.get("active_profile_id") or ""),
        "model_id": str(llm.get("active_model_id") or ""),
    }
    options: list[dict[str, Any]] = []
    for profile in profiles:
        for model in list(profile.get("models") or []):
            options.append(
                {
                    "profile_id": str(profile.get("id") or ""),
                    "profile_label": str(profile.get("name") or ""),
                    "model_id": str(model.get("id") or ""),
                    "model_label": str(model.get("name") or model.get("model") or ""),
                    "provider": str(profile.get("binding") or "openai"),
                    "is_default": (
                        str(profile.get("id") or "") == active["profile_id"]
                        and str(model.get("id") or "") == active["model_id"]
                    ),
                }
            )
    return {"active": active, "options": options}


@router.put("/api/v1/settings/ui")
def update_settings_ui(payload: SettingsUiPayload) -> dict[str, Any]:
    return {"ui": settings_service.update_ui(theme=payload.theme, language=payload.language)}


@router.put("/api/v1/settings/catalog")
def update_settings_catalog(payload: SettingsCatalogPayload) -> dict[str, Any]:
    catalog = payload.catalog
    if isinstance(catalog, dict):
        return {"catalog": settings_service.update_catalog(catalog)}
    return {"catalog": settings_service.catalog()}


@router.post("/api/v1/settings/apply")
def apply_settings_catalog(payload: SettingsCatalogPayload) -> dict[str, Any]:
    catalog = payload.catalog
    return {"catalog": settings_service.apply_catalog(catalog if isinstance(catalog, dict) else None), "applied": True}
