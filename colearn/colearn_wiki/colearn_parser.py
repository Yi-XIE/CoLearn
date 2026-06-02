"""CoLearn Wiki page parser - extracts frontmatter and content."""
import re
from pathlib import Path
from typing import Any

import yaml


# Regex pattern to extract YAML frontmatter (from nanobot pattern)
_FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?",
    re.DOTALL,
)


def parse_wiki_page(file_path: Path) -> tuple[dict[str, Any], str] | None:
    """
    Parse a Wiki page file and extract frontmatter + content.

    Args:
        file_path: Path to the .md file

    Returns:
        Tuple of (frontmatter_dict, content_body) or None if parsing fails
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Failed to read {file_path}: {e}")
        return None

    # Extract frontmatter
    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        print(f"[WARN] No frontmatter found in {file_path}")
        return None

    try:
        frontmatter = yaml.safe_load(match.group(1))
        if not isinstance(frontmatter, dict):
            print(f"[WARN] Invalid frontmatter structure in {file_path}")
            return None
    except yaml.YAMLError as e:
        print(f"[WARN] YAML parse error in {file_path}: {e}")
        return None

    # Extract content body (everything after frontmatter)
    body = content[match.end() :]

    return frontmatter, body


def validate_required_fields(frontmatter: dict[str, Any], file_path: Path) -> bool:
    """
    Validate that frontmatter contains all required fields.

    Required fields per 04-Wiki-Schema.md:
    - id
    - page_type
    - title
    - grade_band
    - domain
    - difficulty
    - updated_at

    Returns:
        True if all required fields present, False otherwise
    """
    required = ["id", "page_type", "title", "grade_band", "domain", "difficulty", "updated_at"]
    missing = [f for f in required if f not in frontmatter]

    if missing:
        print(f"[WARN] Missing required fields in {file_path}: {', '.join(missing)}")
        return False

    return True


def normalize_list_field(value: Any) -> list:
    """
    Normalize a field that should be a list.

    Handles both single values and lists.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
