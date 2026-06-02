"""CoLearn Wiki query service - load and query Wiki indices."""
import json
from pathlib import Path
from typing import Any


class WikiQueryService:
    """Query service for Wiki pages using pre-built indices."""

    def __init__(self, index_dir: Path | str = "knowledge/generated"):
        self.index_dir = Path(index_dir)
        self.pages: dict[str, dict[str, Any]] = {}
        self.link_graph: dict[str, list[str]] = {}
        self.search_index: dict[str, dict[str, Any]] = {}
        self._load_indices()

    def _load_indices(self) -> None:
        """Load indices from JSON files."""
        index_file = self.index_dir / "wiki_index.json"
        graph_file = self.index_dir / "wiki_link_graph.json"
        search_file = self.index_dir / "wiki_search_index.json"

        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                self.pages = json.load(f)
        else:
            print(f"[WARN] Index file not found: {index_file}")

        if graph_file.exists():
            with open(graph_file, "r", encoding="utf-8") as f:
                self.link_graph = json.load(f)
        else:
            print(f"[WARN] Link graph file not found: {graph_file}")

        if search_file.exists():
            with open(search_file, "r", encoding="utf-8") as f:
                self.search_index = json.load(f)

    def get_by_id(self, page_id: str) -> dict[str, Any] | None:
        """Get a page by its ID."""
        return self.pages.get(page_id)

    def find_by_alias(self, alias: str) -> list[dict[str, Any]]:
        """Find pages by alias (case-insensitive partial match)."""
        alias_lower = alias.lower()
        results = []
        for page in self.pages.values():
            for page_alias in page.get("aliases", []):
                if alias_lower in page_alias.lower():
                    results.append(page)
                    break
        return results

    def search_by_keyword(
        self,
        keyword: str,
        domain: str | None = None,
        grade_band: list[str] | None = None,
        difficulty: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search pages by keyword with optional filters."""
        keyword_lower = keyword.lower()
        results = []

        for page_id, page in self.pages.items():
            search_entry = self.search_index.get(page_id, {})
            searchable_parts = [
                page.get("title", ""),
                page.get("summary", ""),
                search_entry.get("summary", ""),
                search_entry.get("body_snippet", ""),
                " ".join(page.get("aliases", [])),
                " ".join(search_entry.get("headings", [])),
            ]
            searchable = " ".join(searchable_parts).lower()
            if keyword_lower not in searchable:
                continue
            if domain and page.get("domain") != domain:
                continue
            if grade_band:
                page_bands = page.get("grade_band", [])
                if not any(band in page_bands for band in grade_band):
                    continue
            if difficulty and page.get("difficulty") != difficulty:
                continue
            results.append(page)
        return results

    def expand_prerequisites(self, page_id: str, max_depth: int = 2) -> list[dict[str, Any]]:
        """Expand prerequisites recursively (BFS) with cycle detection."""
        if page_id not in self.link_graph:
            return []

        visited = set()
        queue = [(page_id, 0)]
        results = []

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)
            linked_ids = self.link_graph.get(current_id, [])
            for linked_id in linked_ids:
                if linked_id not in visited:
                    page = self.get_by_id(linked_id)
                    if page:
                        results.append(page)
                    queue.append((linked_id, depth + 1))
        return results

    def get_page_type_count(self) -> dict[str, int]:
        """Get count of pages by type."""
        counts: dict[str, int] = {}
        for page in self.pages.values():
            page_type = page.get("page_type", "unknown")
            counts[page_type] = counts.get(page_type, 0) + 1
        return counts

    def list_all_ids(self) -> list[str]:
        """Get list of all page IDs."""
        return list(self.pages.keys())
