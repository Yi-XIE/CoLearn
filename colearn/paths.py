"""Stable local path helpers for CoLearn runtime processes."""

from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str) -> Path | None:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()


def colearn_repo_root() -> Path:
    """Return the repository root regardless of the current process cwd."""
    return _env_path("COLEARN_REPO_ROOT") or Path(__file__).resolve().parents[1]


def colearn_state_root() -> Path:
    """Return the canonical JSON state root for local CoLearn data."""
    return _env_path("COLEARN_STATE_ROOT") or colearn_repo_root() / ".colearn" / "state"


def colearn_nanobot_workspace() -> Path:
    """Return the nanobot workspace used by the CoLearn v0.2 runtime."""
    return _env_path("COLEARN_NANOBOT_WORKSPACE") or colearn_repo_root() / ".colearn" / "nanobot-workspace"


def colearn_env_file() -> Path:
    """Return the local environment file used by CoLearn services."""
    return colearn_repo_root() / ".env"


def colearn_slim_config() -> Path:
    """Return the CoLearn nanobot slim config path."""
    return colearn_repo_root() / ".colearn" / "nanobot-v0.2-slim.config.json"
