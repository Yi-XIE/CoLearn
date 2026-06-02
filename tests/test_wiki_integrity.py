"""Tests for Wiki question entries and schema integrity."""
from pathlib import Path

import pytest

from colearn.colearn_wiki.colearn_indexer import WikiIndexBuilder
from colearn.colearn_wiki.colearn_query import WikiQueryService


@pytest.fixture
def query_service(tmp_path):
    """Create a query service from freshly generated test indices."""
    output_dir = tmp_path / "generated"
    builder = WikiIndexBuilder(Path("knowledge/wiki"), output_dir)
    builder.scan_and_build()
    builder.write_indices()
    return WikiQueryService(output_dir)


def test_question_entries_are_indexed(query_service):
    """Stable qb.* entries should be directly resolvable from wiki_index."""
    question = query_service.get_by_id("qb.ai.ml.beginner.01")

    assert question is not None
    assert question["page_type"] == "question"
    assert question["parent_id"] == "qbank.ai.ml.beginner"
    assert "ml.model.basic" in question["related_concepts"]


def test_all_question_refs_resolve(query_service):
    """Concept and path question references should resolve to indexed entries."""
    missing = []
    for page in query_service.pages.values():
        for field in ("question_refs", "checkpoint_question_refs"):
            for ref in page.get(field, []):
                if query_service.get_by_id(ref) is None:
                    missing.append((page["id"], field, ref))

    assert missing == []


def test_duplicate_wiki_ids_fail(tmp_path):
    """Indexer should reject duplicate global page IDs instead of overwriting."""
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    content = """---
id: duplicate.id
page_type: concept
title: Duplicate
grade_band: [10-12]
domain: test
difficulty: beginner
updated_at: 2026-06-02
---

body
"""
    (wiki_root / "one.md").write_text(content, encoding="utf-8")
    (wiki_root / "two.md").write_text(content, encoding="utf-8")

    builder = WikiIndexBuilder(wiki_root, tmp_path / "generated")

    with pytest.raises(ValueError, match="Duplicate Wiki id"):
        builder.scan_and_build()
