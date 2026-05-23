from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import uuid

from colearn.api.state import DEFAULT_SETTINGS_STATE, MemoryDocStateService, SettingsStateService
from colearn.storage.json_store import JsonStateStore


def test_apply_catalog_uses_openai_key_as_deepseek_fallback(monkeypatch):
    tmp_path = Path.cwd() / ".colearn" / "tmp" / f"test-settings-state-{uuid.uuid4().hex}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        "colearn.api.state.colearn_slim_config",
        lambda: tmp_path / "nanobot-v0.2-slim.config.json",
    )

    service = SettingsStateService(
        state_store=JsonStateStore(root=tmp_path / "state"),
        env_path=tmp_path / ".env",
    )
    service._state = deepcopy(DEFAULT_SETTINGS_STATE)
    service._state["catalog"]["services"]["llm"]["profiles"][0]["api_key"] = ""

    service.apply_catalog(service.catalog())

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=sk-test" in env_text


def test_memory_settings_default_and_update():
    tmp_path = Path.cwd() / ".colearn" / "tmp" / f"test-memory-settings-{uuid.uuid4().hex}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    service = SettingsStateService(
        state_store=JsonStateStore(root=tmp_path / "state"),
        env_path=tmp_path / ".env",
    )

    assert service.memory_settings()["enabled"] is True

    updated = service.update_memory_settings(enabled=False)
    assert updated["enabled"] is False

    reloaded = SettingsStateService(
        state_store=JsonStateStore(root=tmp_path / "state"),
        env_path=tmp_path / ".env",
    )
    assert reloaded.memory_settings()["enabled"] is False


def test_memory_doc_service_persists_and_dedupes_auto_entries():
    tmp_path = Path.cwd() / ".colearn" / "tmp" / f"test-memory-docs-{uuid.uuid4().hex}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = JsonStateStore(root=tmp_path / "state")
    service = MemoryDocStateService(state_store=store)

    service.update("summary", "手动正文")
    changed = service.append_auto_entry(
        "summary",
        source_key="review:1",
        title="学习回顾",
        body="本轮确认了关键结论。",
    )
    unchanged = service.append_auto_entry(
        "summary",
        source_key="review:1",
        title="学习回顾",
        body="本轮确认了关键结论。",
    )

    reloaded = MemoryDocStateService(state_store=store)
    snapshot = reloaded.snapshot()
    assert changed is True
    assert unchanged is False
    assert "手动正文" in snapshot["summary"]
    assert "## 自动沉淀" in snapshot["summary"]
    assert snapshot["summary"].count("本轮确认了关键结论。") == 1
