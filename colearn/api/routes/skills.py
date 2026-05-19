"""Skill listing routes — read-only, disk SKILL.md files are the single source."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from colearn.api.dependencies import WORKSPACE_SKILLS_DIR

router = APIRouter()


def _load_disk_skills() -> dict[str, dict[str, Any]]:
    """Scan workspace/skills for SKILL.md files and parse YAML frontmatter."""
    if not WORKSPACE_SKILLS_DIR.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for skill_path in sorted(WORKSPACE_SKILLS_DIR.glob("*/SKILL.md")):
        try:
            content = skill_path.read_text(encoding="utf-8")
        except OSError:
            continue
        metadata = _parse_frontmatter(content)
        name = str(metadata.get("name") or skill_path.parent.name).strip()
        if not name:
            continue
        records[name] = {
            "name": name,
            "description": str(metadata.get("description") or ""),
            "content": content,
            "always": bool(metadata.get("always") or False),
            "path": str(skill_path),
        }
    return records


def _parse_frontmatter(markdown: str) -> dict[str, Any]:
    """Minimal YAML-ish frontmatter parser (key: value, supports always: true)."""
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
        val = value.strip().strip("\"'")
        if val.lower() in ("true", "yes"):
            metadata[key.strip()] = True
        elif val.lower() in ("false", "no"):
            metadata[key.strip()] = False
        else:
            metadata[key.strip()] = val
    return metadata


@router.get("/api/v1/skills/list")
def list_skills() -> dict[str, Any]:
    skills = _load_disk_skills()
    return {
        "skills": [
            {"name": r["name"], "description": r["description"], "always": r["always"]}
            for r in skills.values()
        ]
    }


@router.get("/api/v1/skills/{name}")
def get_skill(name: str) -> dict[str, Any]:
    skills = _load_disk_skills()
    record = skills.get(name)
    if not record:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {
        "name": record["name"],
        "description": record["description"],
        "content": record["content"],
        "always": record["always"],
    }
