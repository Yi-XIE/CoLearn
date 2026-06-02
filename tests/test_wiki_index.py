"""Tests for WikiIndexBuilder."""
import json
from pathlib import Path

import pytest

from colearn.colearn_wiki.colearn_indexer import WikiIndexBuilder


def test_scan_and_build():
    """Test that indexer can scan and build indices from sample pages."""
    wiki_root = Path("knowledge/wiki")
    output_dir = Path("knowledge/generated")

    builder = WikiIndexBuilder(wiki_root, output_dir)
    indexed, skipped = builder.scan_and_build()

    assert indexed >= 14
    assert skipped == 0


def test_generate_index():
    """Test that wiki_index.json is generated and valid."""
    index_file = Path("knowledge/generated/wiki_index.json")
    assert index_file.exists()

    with open(index_file) as f:
        index = json.load(f)

    assert len(index) >= 14

    ml_model = index.get("ml.model.basic")
    assert ml_model is not None
    assert ml_model["page_type"] == "concept"
    assert ml_model["title"] == "什么是模型"


def test_generate_link_graph():
    """Test that wiki_link_graph.json is generated and valid."""
    graph_file = Path("knowledge/generated/wiki_link_graph.json")
    assert graph_file.exists()

    with open(graph_file) as f:
        graph = json.load(f)

    ml_model_links = graph.get("ml.model.basic", [])
    assert "ml.data.basic" in ml_model_links


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
