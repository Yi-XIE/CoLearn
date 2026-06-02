"""CoLearn Wiki data models."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WikiPage:
    """Represents a Wiki page with its metadata."""

    # Required fields (通用必填)
    id: str
    page_type: str
    title: str
    grade_band: list[str]
    domain: str
    difficulty: str
    updated_at: str

    # Optional common fields (通用可选)
    aliases: list[str] = field(default_factory=list)
    summary: str | None = None
    tags: list[str] = field(default_factory=list)
    status: str | None = None
    source_refs: list[str] = field(default_factory=list)

    # Type-specific fields (页面类型专属字段)
    # Concept page
    prerequisites: list[str] = field(default_factory=list)
    learning_objectives: list[str] = field(default_factory=list)
    misconceptions: list[str] = field(default_factory=list)
    experiment_refs: list[str] = field(default_factory=list)
    question_refs: list[str] = field(default_factory=list)
    path_refs: list[str] = field(default_factory=list)

    # Path page
    entry_concepts: list[str] = field(default_factory=list)
    ordered_concepts: list[str] = field(default_factory=list)
    checkpoint_question_refs: list[str] = field(default_factory=list)

    # Experiment page
    concept_refs: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    duration_minutes: int | None = None
    safety_level: str | None = None

    # Question entry (indexed from question bank body)
    parent_id: str | None = None
    question_type: str | None = None
    related_concepts: list[str] = field(default_factory=list)
    answer: str | None = None
    explanation: str | None = None

    # File metadata (索引器自动添加)
    file_path: str | None = None


@dataclass
class WikiIndex:
    """Index of all Wiki pages, keyed by page ID."""
    pages: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_page(self, page: WikiPage) -> None:
        """Add a page to the index."""
        self.pages[page.id] = self._page_to_dict(page)

    def _page_to_dict(self, page: WikiPage) -> dict[str, Any]:
        """Convert WikiPage to dict, excluding None values and empty lists."""
        result = {}
        for key, value in page.__dict__.items():
            if value is None:
                continue
            if isinstance(value, list) and len(value) == 0:
                continue
            # Convert date objects to strings for JSON serialization
            if hasattr(value, 'isoformat'):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result


@dataclass
class LinkGraph:
    """Graph of page relationships (prerequisites, references, etc.)."""
    links: dict[str, list[str]] = field(default_factory=dict)

    def add_link(self, from_id: str, to_id: str) -> None:
        """Add a directed link from one page to another."""
        if from_id not in self.links:
            self.links[from_id] = []
        if to_id not in self.links[from_id]:
            self.links[from_id].append(to_id)

    def add_links(self, from_id: str, to_ids: list[str]) -> None:
        """Add multiple links from one page to others."""
        for to_id in to_ids:
            self.add_link(from_id, to_id)
