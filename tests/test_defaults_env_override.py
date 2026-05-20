"""Tests for Defaults env override and logging context."""

from __future__ import annotations

import importlib
import os


def test_defaults_env_override(monkeypatch):
    monkeypatch.setenv("COLEARN_TURN_CACHE_MAX", "64")
    monkeypatch.setenv("COLEARN_RUNTIME_MAX_RETRIEVAL", "2000")
    # Reload to pick up env changes
    import colearn.config.defaults as m
    importlib.reload(m)
    assert m.Defaults.TURN_CACHE_MAX_TURNS == 64
    assert m.Defaults.RUNTIME_MAX_RETRIEVAL_CHARS == 2000
    # Restore
    importlib.reload(m)


def test_defaults_have_sensible_values():
    from colearn.config.defaults import Defaults
    assert Defaults.TURN_TIMEOUT_SECONDS > 0
    assert Defaults.TURN_CACHE_MAX_TURNS > 0
    assert Defaults.RUNTIME_MAX_RETRIEVAL_CHARS > 0
    assert Defaults.PROMPT_SUPPORT_MAX_ITEMS > 0


def test_logging_context_vars():
    from colearn.logging_context import request_id_var, turn_id_var
    assert request_id_var.get() == "-"
    assert turn_id_var.get() == "-"
    token = request_id_var.set("test-req-1")
    assert request_id_var.get() == "test-req-1"
    request_id_var.reset(token)
    assert request_id_var.get() == "-"


def test_logging_context_isolation():
    """Each contextvar token is independent."""
    from colearn.logging_context import turn_id_var
    t1 = turn_id_var.set("turn-a")
    t2 = turn_id_var.set("turn-b")
    assert turn_id_var.get() == "turn-b"
    turn_id_var.reset(t2)
    assert turn_id_var.get() == "turn-a"
    turn_id_var.reset(t1)
    assert turn_id_var.get() == "-"
