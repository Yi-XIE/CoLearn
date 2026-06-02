"""CoLearn Wiki indexer - scans Wiki pages and generates indices."""
import json
import re
from pathlib import Path
from typing import Any

from colearn.colearn_wiki.colearn_models import LinkGraph, WikiIndex, WikiPage
from colearn.colearn_wiki.colearn_parser import (
    normalize_list_field,
    parse_wiki_page,
    validate_required_fields,
)

_QUESTION_HEADING_RE = re.compile(r"^###\s+(qb\.[\w.-]+)\s*$", re.MULTILINE)
_FIELD_RE = re.compile(r"\*\*(?P<label>[^*]+)\*\*[:：]\s*(?P<value>.*)")


class WikiIndexBuilder:
    """Builds Wiki index and link graph from markdown files."""

    def __init__(self, wiki_root: Path, output_dir: Path):
        self.wiki_root = Path(wiki_root)
        self.output_dir = Path(output_dir)
        self.index = WikiIndex()
        self.link_graph = LinkGraph()
        self.search_index: dict[str, dict[str, Any]] = {}
        self._seen_ids: dict[str, Path] = {}

    def scan_and_build(self) -> tuple[int, int]:
        """Scan all .md files under wiki_root and build indices."""
        if not self.wiki_root.exists():
            print(f"[ERROR] Wiki root does not exist: {self.wiki_root}")
            return 0, 0

        md_files = sorted(self.wiki_root.rglob("*.md"))
        pages_indexed = 0
        pages_skipped = 0

        for md_file in md_files:
            result = parse_wiki_page(md_file)
            if result is None:
                pages_skipped += 1
                continue

            frontmatter, body = result

            if not validate_required_fields(frontmatter, md_file):
                pages_skipped += 1
                continue

            page = self._build_page(frontmatter, md_file)
            if page is None:
                pages_skipped += 1
                continue

            self._add_unique_page(page, md_file, body)
            self._extract_links(page)
            pages_indexed += 1

            if page.page_type == "question_bank":
                question_pages = self._extract_question_entries(page, body, md_file)
                for question_page in question_pages:
                    self._add_unique_page(question_page, md_file, question_page.title or "")
                    self._extract_links(question_page)
                    self.link_graph.add_link(page.id, question_page.id)
                    pages_indexed += 1

        return pages_indexed, pages_skipped

    def _add_unique_page(self, page: WikiPage, file_path: Path, body: str = "") -> None:
        """Add page and fail loudly if a global ID is duplicated."""
        if page.id in self._seen_ids:
            first_path = self._seen_ids[page.id]
            raise ValueError(
                f"Duplicate Wiki id '{page.id}' in {file_path}; first seen in {first_path}"
            )
        self._seen_ids[page.id] = file_path
        self.index.add_page(page)
        self.search_index[page.id] = self._build_search_entry(page, body)

    def _build_search_entry(self, page: WikiPage, body: str) -> dict[str, Any]:
        """Build lightweight search entry with headings and body snippet."""
        headings = [
            line.lstrip("#").strip()
            for line in body.splitlines()
            if line.startswith("#")
        ]
        plain = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
        plain = re.sub(r"[#*_`>\-]+", " ", plain)
        plain = re.sub(r"\s+", " ", plain).strip()
        return {
            "id": page.id,
            "page_type": page.page_type,
            "title": page.title,
            "aliases": list(page.aliases),
            "summary": page.summary or "",
            "domain": page.domain,
            "difficulty": page.difficulty,
            "headings": headings,
            "body_snippet": plain[:1000],
        }

    def _build_page(self, frontmatter: dict[str, Any], file_path: Path) -> WikiPage | None:
        """Build a WikiPage object from frontmatter."""
        try:
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

            page.aliases = normalize_list_field(frontmatter.get("aliases"))
            page.summary = frontmatter.get("summary")
            page.tags = normalize_list_field(frontmatter.get("tags"))
            page.status = frontmatter.get("status")
            page.source_refs = normalize_list_field(frontmatter.get("source_refs"))

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

    def _extract_question_entries(
        self, bank_page: WikiPage, body: str, file_path: Path
    ) -> list[WikiPage]:
        """Extract stable `qb.*` question entries from a question bank body."""
        matches = list(_QUESTION_HEADING_RE.finditer(body))
        questions: list[WikiPage] = []
        for index, match in enumerate(matches):
            question_id = match.group(1)
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            block = body[start:end]
            fields = self._parse_question_fields(block)
            related = normalize_list_field(fields.get("关联概念"))
            question = WikiPage(
                id=question_id,
                page_type="question",
                title=fields.get("题目", question_id),
                grade_band=bank_page.grade_band,
                domain=bank_page.domain,
                difficulty=fields.get("难度") or bank_page.difficulty,
                updated_at=bank_page.updated_at,
                parent_id=bank_page.id,
                question_type=fields.get("题目类型"),
                related_concepts=related,
                answer=fields.get("答案"),
                explanation=fields.get("解释"),
                file_path=str(file_path.relative_to(self.wiki_root.parent)),
            )
            questions.append(question)
        return questions

    def _parse_question_fields(self, block: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        lines = [line.strip() for line in block.splitlines()]
        current_label: str | None = None
        body_lines: list[str] = []

        for line in lines:
            if not line or line == "---":
                continue
            field_match = _FIELD_RE.match(line)
            if field_match:
                label = field_match.group("label").strip()
                value = field_match.group("value").strip().rstrip("  ")
                fields[label] = value
                current_label = label
                if label == "题目":
                    body_lines = [value]
                continue
            if current_label == "题目":
                body_lines.append(line)

        if body_lines:
            fields["题目"] = "\n".join(body_lines).strip()
        return fields

    def _extract_links(self, page: WikiPage) -> None:
        """Extract all reference links from a page and add to link graph."""
        from_id = page.id
        link_fields = [
            page.prerequisites,
            page.concept_refs,
            page.experiment_refs,
            page.question_refs,
            page.path_refs,
            page.ordered_concepts,
            page.entry_concepts,
            page.checkpoint_question_refs,
            page.related_concepts,
        ]
        if page.parent_id:
            self.link_graph.add_link(from_id, page.parent_id)
        for links in link_fields:
            if links:
                self.link_graph.add_links(from_id, links)

    def write_indices(self) -> None:
        """Write index and link graph to JSON files."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        index_file = self.output_dir / "wiki_index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(self.index.pages, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Wrote {index_file}")

        graph_file = self.output_dir / "wiki_link_graph.json"
        with open(graph_file, "w", encoding="utf-8") as f:
            json.dump(self.link_graph.links, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Wrote {graph_file}")

        search_file = self.output_dir / "wiki_search_index.json"
        with open(search_file, "w", encoding="utf-8") as f:
            json.dump(self.search_index, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Wrote {search_file}")


def main():
    """CLI entry point: python -m colearn.colearn_wiki.colearn_indexer"""
    import sys

    wiki_root = Path("knowledge/wiki")
    output_dir = Path("knowledge/generated")

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
