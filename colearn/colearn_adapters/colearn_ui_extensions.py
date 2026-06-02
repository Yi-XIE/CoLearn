"""UI extension declarations for CoLearn host integration."""
from __future__ import annotations

from typing import Any


COLEARN_UI_EXTENSIONS: list[dict[str, Any]] = [
    {
        "id": "colearn.graph.entry",
        "slot": "apps",
        "kind": "utility_entry",
        "title": "CoLearn 图谱",
        "icon": "share-2",
        "target": "colearn.knowledge-graph",
        "visibility": {"modes": ["learning", "chat"]},
    },
    {
        "id": "colearn.knowledge-graph",
        "slot": "page",
        "container": "graph",
        "title": "知识图谱",
        "icon": "share-2",
        "data_endpoint": "/api/v1/colearn/graph/current",
        "visibility": {"modes": ["learning", "chat"]},
    },
    {
        "id": "colearn.dashboard.panel",
        "slot": "thread_toolbar",
        "container": "panel",
        "title": "CoLearn 看板",
        "icon": "activity",
        "data_endpoint": "/api/v1/colearn/blackboard/current",
        "visibility": {"modes": ["learning"]},
    },
]


class UIExtensionRegistry:
    """In-memory registry for CoLearn fixed-slot UI extension manifests."""

    def __init__(self, extensions: list[dict[str, Any]] | None = None) -> None:
        self.extensions = list(extensions or COLEARN_UI_EXTENSIONS)

    def list(self, slot: str | None = None) -> list[dict[str, Any]]:
        """List extension manifests, optionally filtered by slot."""
        if slot is None:
            return list(self.extensions)
        return [ext for ext in self.extensions if ext.get("slot") == slot]

    def resolve(self, extension_id: str) -> dict[str, Any] | None:
        """Resolve one extension manifest by id."""
        for ext in self.extensions:
            if ext.get("id") == extension_id:
                return dict(ext)
        return None
