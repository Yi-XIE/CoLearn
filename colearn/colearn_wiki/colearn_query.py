"""CoLearn Wiki query service - load and query Wiki indices."""
import json
from pathlib import Path
from typing import Any


class WikiQueryService:
    """Query service for Wiki pages using pre-built indices."""

    def __init__(self, index_dir: Path | str = "knowledge/generated"):
        """
        Initialize query service.

        Args:
            index_dir: Directory containing wiki_index.json and wiki_link_graph.json
        """
        self.index_dir = Path(index_dir)
        self.pages: dict[str, dict[str, Any]] = {}
        self.link_graph: dict[str, list[str]] = {}
        self._load_indices()

    def _load_indices(self) -> None:
        """Load indices from JSON files."""
        index_file = self.index_dir / "wiki_index.json"
        graph_file = self.index_dir / "wiki_link_graph.json"

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

    def get_by_id(self, page_id: str) -> dict[str, Any] | None:
        """
        Get a page by its ID.

        Args:
            page_id: Page ID (e.g., "ml.model.basic")

        Returns:
            Page metadata dict or None if not found
        """
        return self.pages.get(page_id)

    def find_by_alias(self, alias: str) -> list[dict[str, Any]]:
        """
        Find pages by alias (case-insensitive partial match).

        Args:
            alias: Alias to search for

        Returns:
            List of matching pages
        """
        alias_lower = alias.lower()
        results = []

        for page in self.pages.values():
            page_aliases = page.get("aliases", [])
            for page_alias in page_aliases:
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
        """
        Search pages by keyword in title or summary, with optional filters.

        Args:
            keyword: Keyword to search in title/summary (case-insensitive)
            domain: Filter by domain (e.g., "ml", "physics")
            grade_band: Filter by grade band overlap (e.g., ["10-12"])
            difficulty: Filter by difficulty (e.g., "beginner")

        Returns:
            List of matching pages
        """
        keyword_lower = keyword.lower()
        results = []

        for page in self.pages.values():
            # Keyword match
            title = page.get("title", "").lower()
            summary = page.get("summary", "").lower()
            if keyword_lower not in title and keyword_lower not in summary:
                continue

            # Domain filter
            if domain and page.get("domain") != domain:
                continue

            # Grade band filter (check overlap)
            if grade_band:
                page_bands = page.get("grade_band", [])
                if not any(band in page_bands for band in grade_band):
                    continue

            # Difficulty filter
            if difficulty and page.get("difficulty") != difficulty:
                continue

            results.append(page)

        return results

    def expand_prerequisites(self, page_id: str, max_depth: int = 2) -> list[dict[str, Any]]:
        """
        Expand prerequisites recursively (BFS) with cycle detection.

        Args:
            page_id: Starting page ID
            max_depth: Maximum depth to expand (default 2)

        Returns:
            List of prerequisite pages in BFS order
        """
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

            # Get linked pages (prerequisites and refs)
            linked_ids = self.link_graph.get(current_id, [])

            for linked_id in linked_ids:
                if linked_id not in visited:
                    page = self.get_by_id(linked_id)
                    if page:
                        results.append(page)
                    queue.append((linked_id, depth + 1))

        return results

    def get_page_type_count(self) -> dict[str, int]:
        """
        Get count of pages by type.

        Returns:
            Dict of page_type -> count
        """
        counts: dict[str, int] = {}
        for page in self.pages.values():
            page_type = page.get("page_type", "unknown")
            counts[page_type] = counts.get(page_type, 0) + 1
        return counts

    def list_all_ids(self) -> list[str]:
        """Get list of all page IDs."""
        return list(self.pages.keys())
