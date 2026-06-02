"""CoLearn Wiki indexer - scans Wiki pages and generates indices."""
import json
from pathlib import Path
from typing import Any

from colearn.colearn_wiki.colearn_models import LinkGraph, WikiIndex, WikiPage
from colearn.colearn_wiki.colearn_parser import (
    normalize_list_field,
    parse_wiki_page,
    validate_required_fields,
)


class WikiIndexBuilder:
    """Builds Wiki index and link graph from markdown files."""

    def __init__(self, wiki_root: Path, output_dir: Path):
        """
        Initialize the index builder.

        Args:
            wiki_root: Root directory containing Wiki pages (knowledge/wiki/)
            output_dir: Directory to write generated indices (knowledge/generated/)
        """
        self.wiki_root = Path(wiki_root)
        self.output_dir = Path(output_dir)
        self.index = WikiIndex()
        self.link_graph = LinkGraph()

    def scan_and_build(self) -> tuple[int, int]:
        """
        Scan all .md files under wiki_root and build indices.

        Returns:
            Tuple of (pages_indexed, pages_skipped)
        """
        if not self.wiki_root.exists():
            print(f"[ERROR] Wiki root does not exist: {self.wiki_root}")
            return 0, 0

        md_files = list(self.wiki_root.rglob("*.md"))
        pages_indexed = 0
        pages_skipped = 0

        for md_file in md_files:
            result = parse_wiki_page(md_file)
            if result is None:
                pages_skipped += 1
                continue

            frontmatter, _body = result

            # Validate required fields
            if not validate_required_fields(frontmatter, md_file):
                pages_skipped += 1
                continue

            # Build WikiPage object
            page = self._build_page(frontmatter, md_file)
            if page is None:
                pages_skipped += 1
                continue

            # Add to index
            self.index.add_page(page)

            # Extract links for graph
            self._extract_links(page)

            pages_indexed += 1

        return pages_indexed, pages_skipped

    def _build_page(self, frontmatter: dict[str, Any], file_path: Path) -> WikiPage | None:
        """Build a WikiPage object from frontmatter."""
        try:
            # Extract required fields
            page = WikiPage(
                id=frontmatter["id"],
                page_type=frontmatter["page_type"],
                title=frontmatter["title"],
                grade_band=normalize_list_field(frontmatter["grade_band"]),
                domain=frontmatter["domain"],
                difficulty=frontmatter["difficulty"],
                updated_at=frontmatter["updated_at"],
                file_path=str(file_path.relative_to(self.wiki_root.parent)),
            )

            # Extract optional common fields
            page.aliases = normalize_list_field(frontmatter.get("aliases"))
            page.summary = frontmatter.get("summary")
            page.tags = normalize_list_field(frontmatter.get("tags"))
            page.status = frontmatter.get("status")
            page.source_refs = normalize_list_field(frontmatter.get("source_refs"))

            # Extract type-specific fields
            if page.page_type == "concept":
                page.prerequisites = normalize_list_field(frontmatter.get("prerequisites"))
                page.learning_objectives = normalize_list_field(frontmatter.get("learning_objectives"))
                page.misconceptions = normalize_list_field(frontmatter.get("misconceptions"))
                page.experiment_refs = normalize_list_field(frontmatter.get("experiment_refs"))
                page.question_refs = normalize_list_field(frontmatter.get("question_refs"))
                page.path_refs = normalize_list_field(frontmatter.get("path_refs"))

            elif page.page_type == "path":
                page.entry_concepts = normalize_list_field(frontmatter.get("entry_concepts"))
                page.ordered_concepts = normalize_list_field(frontmatter.get("ordered_concepts"))
                page.checkpoint_question_refs = normalize_list_field(
                    frontmatter.get("checkpoint_question_refs")
                )

            elif page.page_type == "experiment":
                page.concept_refs = normalize_list_field(frontmatter.get("concept_refs"))
                page.materials = normalize_list_field(frontmatter.get("materials"))
                page.duration_minutes = frontmatter.get("duration_minutes")
                page.safety_level = frontmatter.get("safety_level")

            elif page.page_type == "question_bank":
                page.concept_refs = normalize_list_field(frontmatter.get("concept_refs"))
                page.question_count = frontmatter.get("question_count")

            return page

        except KeyError as e:
            print(f"[WARN] Missing required field {e} in {file_path}")
            return None
        except Exception as e:
            print(f"[WARN] Failed to build page from {file_path}: {e}")
            return None

    def _extract_links(self, page: WikiPage) -> None:
        """Extract all reference links from a page and add to link graph."""
        from_id = page.id

        # Prerequisites (concept pages)
        if page.prerequisites:
            self.link_graph.add_links(from_id, page.prerequisites)

        # Concept refs (experiment and question_bank pages)
        if page.concept_refs:
            self.link_graph.add_links(from_id, page.concept_refs)

        # Experiment refs (concept pages)
        if page.experiment_refs:
            self.link_graph.add_links(from_id, page.experiment_refs)

        # Question refs (concept pages)
        if page.question_refs:
            self.link_graph.add_links(from_id, page.question_refs)

        # Path refs (concept pages)
        if page.path_refs:
            self.link_graph.add_links(from_id, page.path_refs)

        # Ordered concepts (path pages)
        if page.ordered_concepts:
            self.link_graph.add_links(from_id, page.ordered_concepts)

        # Entry concepts (path pages)
        if page.entry_concepts:
            self.link_graph.add_links(from_id, page.entry_concepts)

        # Checkpoint questions (path pages)
        if page.checkpoint_question_refs:
            self.link_graph.add_links(from_id, page.checkpoint_question_refs)

    def write_indices(self) -> None:
        """Write index and link graph to JSON files."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Write wiki_index.json
        index_file = self.output_dir / "wiki_index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(self.index.pages, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Wrote {index_file}")

        # Write wiki_link_graph.json
        graph_file = self.output_dir / "wiki_link_graph.json"
        with open(graph_file, "w", encoding="utf-8") as f:
            json.dump(self.link_graph.links, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Wrote {graph_file}")


def main():
    """CLI entry point: python -m colearn.colearn_wiki.colearn_indexer"""
    import sys

    # Default paths
    wiki_root = Path("knowledge/wiki")
    output_dir = Path("knowledge/generated")

    # Allow override via command line
    if len(sys.argv) > 1:
        wiki_root = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_dir = Path(sys.argv[2])

    print(f"[INFO] Scanning Wiki pages in: {wiki_root}")
    print(f"[INFO] Output directory: {output_dir}")

    builder = WikiIndexBuilder(wiki_root, output_dir)
    indexed, skipped = builder.scan_and_build()

    print(f"\n[SUMMARY] Indexed: {indexed} pages, Skipped: {skipped} pages")

    if indexed > 0:
        builder.write_indices()
        print("[SUCCESS] Wiki index generation complete!")
    else:
        print("[WARN] No pages indexed. Check your Wiki directory.")


if __name__ == "__main__":
    main()
