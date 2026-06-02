"""Tests for WikiQueryService."""
import pytest

from colearn.colearn_wiki.colearn_query import WikiQueryService


@pytest.fixture
def query_service():
    """Create a query service instance."""
    return WikiQueryService()


def test_get_by_id(query_service):
    """Test get_by_id method."""
    page = query_service.get_by_id("ml.model.basic")
    assert page is not None
    assert page["title"] == "什么是模型"
    assert page["page_type"] == "concept"


def test_get_by_id_not_found(query_service):
    """Test get_by_id with non-existent ID."""
    page = query_service.get_by_id("nonexistent.id")
    assert page is None


def test_find_by_alias(query_service):
    """Test find_by_alias method."""
    results = query_service.find_by_alias("模型")
    assert len(results) > 0
    assert any(page["id"] == "ml.model.basic" for page in results)


def test_search_by_keyword(query_service):
    """Test search_by_keyword method."""
    results = query_service.search_by_keyword("模型", domain="ml")
    assert len(results) > 0
    assert all(page["domain"] == "ml" for page in results)


def test_search_by_keyword_with_filters(query_service):
    """Test search with multiple filters."""
    results = query_service.search_by_keyword(
        "力", domain="physics", difficulty="beginner"
    )
    assert len(results) > 0
    assert all(page["domain"] == "physics" for page in results)
    assert all(page["difficulty"] == "beginner" for page in results)


def test_expand_prerequisites(query_service):
    """Test expand_prerequisites method."""
    prereqs = query_service.expand_prerequisites("ml.training.basic", max_depth=1)
    assert len(prereqs) > 0
    prereq_ids = [p["id"] for p in prereqs]
    assert "ml.model.basic" in prereq_ids


def test_get_page_type_count(query_service):
    """Test get_page_type_count method."""
    counts = query_service.get_page_type_count()
    assert "concept" in counts
    assert "path" in counts
    assert counts["concept"] >= 8
    assert counts["path"] >= 2


def test_list_all_ids(query_service):
    """Test list_all_ids method."""
    ids = query_service.list_all_ids()
    assert len(ids) >= 14
    assert "ml.model.basic" in ids
    assert "physics.force.basic" in ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
