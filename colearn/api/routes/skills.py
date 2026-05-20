"""Skill listing routes — delegates to nanobot's native SkillsLoader."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from nanobot.agent.skills import SkillsLoader

from colearn.api.dependencies import WORKSPACE_SKILLS_DIR

router = APIRouter()

_loader = SkillsLoader(workspace=WORKSPACE_SKILLS_DIR.parent)


@router.get("/api/v1/skills/list")
def list_skills() -> dict[str, Any]:
    entries = _loader.list_skills(filter_unavailable=False)
    skills = []
    for entry in entries:
        meta = _loader.get_skill_metadata(entry["name"]) or {}
        always = bool(meta.get("always", False))
        desc = str(meta.get("description") or entry["name"])
        skills.append({"name": entry["name"], "description": desc, "always": always})
    return {"skills": skills}


@router.get("/api/v1/skills/{name}")
def get_skill(name: str) -> dict[str, Any]:
    content = _loader.load_skill(name)
    if content is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    meta = _loader.get_skill_metadata(name) or {}
    return {
        "name": name,
        "description": str(meta.get("description") or name),
        "content": content,
        "always": bool(meta.get("always", False)),
    }
