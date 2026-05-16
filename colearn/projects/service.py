"""Minimal in-memory project service for the standalone assembly workspace."""

from __future__ import annotations

from dataclasses import asdict

from colearn.storage import JsonStateStore

from .models import LearningProject


class LearningProjectService:
    def __init__(self, state_store: JsonStateStore | None = None) -> None:
        self._projects: dict[str, LearningProject] = {}
        self._state_store = state_store or JsonStateStore()
        self._load()

    def _load(self) -> None:
        raw = self._state_store.read_json("projects.json", [])
        if not isinstance(raw, list):
            return
        for item in raw:
            if not isinstance(item, dict):
                continue
            project = LearningProject(
                project_id=str(item.get("project_id") or ""),
                title=str(item.get("title") or ""),
                goal=str(item.get("goal") or ""),
                source_refs=list(item.get("source_refs") or []),
                memory_refs=list(item.get("memory_refs") or []),
                turn_mode=str(item.get("turn_mode") or "EXPLORE"),
                board_facts=dict(item.get("board_facts") or {}),
                board_version=int(item.get("board_version") or 1),
                anchor=dict(item.get("anchor") or {}),
                anchor_status=str(item.get("anchor_status") or "missing"),
                source_subset=list(item.get("source_subset") or []),
                latest_review=dict(item.get("latest_review") or {}),
                current_main_goal=str(item.get("current_main_goal") or ""),
                retrieval_profile=dict(item.get("retrieval_profile") or {}),
            )
            if project.project_id:
                self._projects[project.project_id] = project

    def _dump(self) -> None:
        self._state_store.write_json(
            "projects.json",
            [asdict(project) for project in self._projects.values()],
        )

    def create_project(self, project_id: str, title: str, goal: str = "") -> LearningProject:
        project = LearningProject(project_id=project_id, title=title, goal=goal)
        self._projects[project_id] = project
        self._dump()
        return project

    def get_project(self, project_id: str) -> LearningProject | None:
        return self._projects.get(project_id)

    def list_projects(self) -> list[LearningProject]:
        return list(self._projects.values())

    def to_payload(self, project_id: str) -> dict[str, object] | None:
        project = self.get_project(project_id)
        return asdict(project) if project else None

    def save_project(self, project: LearningProject) -> LearningProject:
        self._projects[project.project_id] = project
        self._dump()
        return project
