"""Helpers for importing the bundled nanobot runtime in local CoLearn flows."""

from __future__ import annotations

import sys
from pathlib import Path

from colearn.paths import colearn_repo_root


def bundled_nanobot_roots() -> tuple[Path, ...]:
    repo_root = colearn_repo_root()
    return (
        repo_root / "third_party" / "nanobot-core",
        repo_root / "third_party" / "nanobot-0.2.0" / "nanobot-0.2.0",
    )


def ensure_nanobot_on_path() -> Path | None:
    """Make the bundled nanobot package importable without external PYTHONPATH."""
    for candidate in bundled_nanobot_roots():
        package_init = candidate / "nanobot" / "__init__.py"
        if not package_init.exists():
            continue
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
        return candidate
    return None
