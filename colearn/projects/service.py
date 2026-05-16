"""Minimal in-memory project service for the standalone assembly workspace."""

from __future__ import annotations

from colearn.storage import JsonStateStore
from colearn.storage.records import project_from_record, project_to_record

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
            project = project_from_record(item)
            if project.project_id:
                self._projects[project.project_id] = project

    def _dump(self) -> None:
        self._state_store.write_json(
            "projects.json",
            [project_to_record(project) for project in self._projects.values()],
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
        return project_to_record(project) if project else None

    def save_project(self, project: LearningProject) -> LearningProject:
        self._projects[project.project_id] = project
        self._dump()
        return project
