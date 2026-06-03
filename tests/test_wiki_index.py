"""Tests for WikiIndexBuilder."""
import json
from pathlib import Path

import pytest

from colearn.colearn_wiki.colearn_indexer import WikiIndexBuilder


@pytest.fixture
def built_indices(tmp_path):
    """Build wiki indices into an isolated temporary output directory."""
    wiki_root = Path("knowledge/wiki")
    output_dir = tmp_path / "generated"
    builder = WikiIndexBuilder(wiki_root, output_dir)
    indexed, skipped = builder.scan_and_build()
    builder.write_indices()
    return indexed, skipped, output_dir


def test_scan_and_build(built_indices):
    """Test that indexer can scan and build indices from sample pages."""
    indexed, skipped, _output_dir = built_indices

    assert indexed >= 21
    assert skipped == 0


def test_generate_index(built_indices):
    """Test that wiki_index.json is generated and valid."""
    _indexed, _skipped, output_dir = built_indices
    index_file = output_dir / "wiki_index.json"
    assert index_file.exists()

    with open(index_file, encoding="utf-8") as f:
        index = json.load(f)

    assert len(index) >= 21

    ml_model = index.get("ml.model.basic")
    assert ml_model is not None
    assert ml_model["page_type"] == "concept"
    assert ml_model["title"] == "什么是模型"


def test_generate_link_graph(built_indices):
    """Test that wiki_link_graph.json is generated and valid."""
    _indexed, _skipped, output_dir = built_indices
    graph_file = output_dir / "wiki_link_graph.json"
    assert graph_file.exists()

    with open(graph_file, encoding="utf-8") as f:
        graph = json.load(f)

    ml_model_links = graph.get("ml.model.basic", [])
    assert "ml.data.basic" in ml_model_links


def test_generate_search_index(built_indices):
    """Test that wiki_search_index.json is generated and contains snippets."""
    _indexed, _skipped, output_dir = built_indices
    search_file = output_dir / "wiki_search_index.json"
    assert search_file.exists()

    with open(search_file, encoding="utf-8") as f:
        search_index = json.load(f)

    ml_model = search_index.get("ml.model.basic")
    assert ml_model is not None
    assert ml_model["title"] == "什么是模型"
    assert "headings" in ml_model
    assert "body_snippet" in ml_model


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
