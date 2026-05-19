"""Skill management routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from colearn.api.dependencies import skill_service, WORKSPACE_SKILLS_DIR
from colearn.api.schemas import SkillPayload, SkillTagPayload, SkillUpdatePayload

router = APIRouter()


def _parse_skill_frontmatter(markdown: str) -> dict[str, Any]:
    if not markdown.startswith("---"):
        return {}
    parts = markdown.split("---", 2)
    if len(parts) < 3:
        return {}
    metadata: dict[str, Any] = {}
    for raw_line in parts[1].splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip("\"'")
    return metadata


def _load_disk_skills() -> dict[str, dict[str, Any]]:
    if not WORKSPACE_SKILLS_DIR.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for skill_path in sorted(WORKSPACE_SKILLS_DIR.glob("*/SKILL.md")):
        try:
            content = skill_path.read_text(encoding="utf-8")
        except OSError:
            continue
        metadata = _parse_skill_frontmatter(content)
        name = str(metadata.get("name") or skill_path.parent.name).strip()
        if not name:
            continue
        records[name] = {
            "description": str(metadata.get("description") or ""),
            "content": content,
            "tags": ["personal"],
        }
    return records


def list_available_skills() -> list[dict[str, Any]]:
    merged = _load_disk_skills()
    for record in skill_service.list_skills():
        merged[str(record["name"])] = {
            "description": str(record.get("description") or ""),
            "content": "",
            "tags": list(record.get("tags") or []),
        }
    return [
        {
            "name": name,
            "description": str(record.get("description") or ""),
            "tags": list(record.get("tags") or []),
        }
        for name, record in sorted(merged.items())
    ]


def get_available_skill(name: str) -> dict[str, Any]:
    record = skill_service.get_skill(name)
    if record:
        return dict(record)
    return _load_disk_skills().get(name, {})


@router.get("/api/v1/skills/list")
def list_skills() -> dict[str, Any]:
    return {"skills": list_available_skills()}


@router.get("/api/v1/skills/{name}")
def get_skill(name: str) -> dict[str, Any]:
    record = get_available_skill(name)
    if not record:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {
        "name": name,
        "description": str(record.get("description") or ""),
        "content": str(record.get("content") or ""),
        "tags": list(record.get("tags") or []),
    }


@router.post("/api/v1/skills/create")
def create_skill(payload: SkillPayload) -> dict[str, Any]:
    skill_service.save_skill(payload.name, {
        "description": payload.description,
        "content": payload.content,
        "tags": list(payload.tags),
    })
    return {
        "name": payload.name,
        "description": payload.description,
        "content": payload.content,
        "tags": list(payload.tags),
    }


@router.put("/api/v1/skills/{name}")
def update_skill(name: str, payload: SkillUpdatePayload) -> dict[str, Any]:
    record = skill_service.get_skill(name)
    if not record:
        raise HTTPException(status_code=404, detail="Skill not found")
    new_name = payload.rename_to or name
    record["description"] = payload.description if payload.description is not None else record.get("description", "")
    record["content"] = payload.content if payload.content is not None else record.get("content", "")
    record["tags"] = list(payload.tags) if payload.tags else list(record.get("tags") or [])
    if new_name != name:
        skill_service.delete_skill(name)
    skill_service.save_skill(new_name, record)
    return {"name": new_name, **record}


@router.delete("/api/v1/skills/{name}")
def delete_skill(name: str) -> dict[str, Any]:
    skill_service.delete_skill(name)
    return {"deleted": True}


@router.get("/api/v1/skills/tags/list")
def list_skill_tags() -> dict[str, Any]:
    return {"tags": skill_service.list_tags()}


@router.post("/api/v1/skills/tags/create")
def create_skill_tag(payload: SkillTagPayload) -> dict[str, Any]:
    skill_service.save_tag(payload.name)
    return {"name": payload.name}


@router.put("/api/v1/skills/tags/{old_name}")
def rename_skill_tag(old_name: str, payload: SkillTagPayload) -> dict[str, Any]:
    new_name = payload.rename_to or payload.name or old_name
    skill_service.rename_tag(old_name, new_name)
    return {"name": new_name}


@router.delete("/api/v1/skills/tags/{name}")
def delete_skill_tag(name: str) -> dict[str, Any]:
    skill_service.delete_tag(name)
    return {"deleted": True}