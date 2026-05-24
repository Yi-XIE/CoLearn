import json
import os
from pathlib import Path
import uuid

from colearn.server import _hydrate_provider_env_aliases, _load_repo_env, _sync_runtime_from_settings


def test_load_repo_env_keeps_existing_values_and_parses_quotes(monkeypatch):
    tmp_path = Path.cwd() / ".colearn" / "tmp" / f"test-server-env-{uuid.uuid4().hex}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# local defaults",
                "EXISTING=from-file",
                'QUOTED="hello world"',
                "export SINGLE='value # kept'",
                "INLINE=value # ignored",
                "BROKEN='unterminated",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING", "from-process")
    monkeypatch.delenv("QUOTED", raising=False)
    monkeypatch.delenv("SINGLE", raising=False)
    monkeypatch.delenv("INLINE", raising=False)
    monkeypatch.delenv("BROKEN", raising=False)

    _load_repo_env(tmp_path)

    assert os.environ["EXISTING"] == "from-process"
    assert os.environ["QUOTED"] == "hello world"
    assert os.environ["SINGLE"] == "value # kept"
    assert os.environ["INLINE"] == "value"
    assert "BROKEN" not in os.environ


def test_hydrate_provider_env_aliases_promotes_openai_key_for_deepseek(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    _hydrate_provider_env_aliases()

    assert os.environ["DEEPSEEK_API_KEY"] == "sk-test"


def test_sync_runtime_from_settings_prefers_active_profile(monkeypatch):
    tmp_path = Path.cwd() / ".colearn" / "tmp" / f"test-server-settings-{uuid.uuid4().hex}"
    repo_root = tmp_path / "repo"
    state_root = repo_root / ".colearn" / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".env").write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-stale",
                "DEEPSEEK_API_BASE=https://api.deepseek.com",
                "DEEPSEEK_MODEL=deepseek-v4-flash",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    settings_payload = {
        "ui": {"theme": "dark", "language": "zh"},
        "memory": {"enabled": True},
        "catalog": {
            "version": 1,
            "services": {
                "llm": {
                    "active_profile_id": "deepseek-llm-profile",
                    "active_model_id": "deepseek-v4-flash",
                    "profiles": [
                        {
                            "id": "deepseek-llm-profile",
                            "name": "DeepSeek LLM",
                            "binding": "deepseek",
                            "base_url": "https://api.deepseek.com",
                            "api_key": "sk-fresh",
                            "models": [
                                {
                                    "id": "deepseek-v4-flash",
                                    "name": "deepseek-v4-flash",
                                    "model": "deepseek-v4-flash",
                                }
                            ],
                        }
                    ],
                },
                "embedding": {
                    "active_profile_id": "embed-profile",
                    "active_model_id": "embed-model",
                    "profiles": [
                        {
                            "id": "embed-profile",
                            "name": "Embedding",
                            "binding": "siliconflow",
                            "base_url": "https://api.siliconflow.cn/v1/embeddings",
                            "api_key": "sk-embed",
                            "models": [
                                {
                                    "id": "embed-model",
                                    "name": "Qwen/Qwen3-Embedding-8B",
                                    "model": "Qwen/Qwen3-Embedding-8B",
                                    "send_dimensions": False,
                                }
                            ],
                        }
                    ],
                },
            },
        },
        "providers": {
            "llm": [{"value": "deepseek", "label": "DeepSeek", "base_url": "https://api.deepseek.com"}],
            "embedding": [{"value": "siliconflow", "label": "SiliconFlow", "base_url": "https://api.siliconflow.cn/v1/embeddings"}],
            "search": [],
        },
    }
    (state_root / "settings_state.json").write_text(
        json.dumps(settings_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    monkeypatch.chdir(repo_root)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-stale")
    monkeypatch.setattr(
        "colearn.api.state.colearn_slim_config",
        lambda: repo_root / ".colearn" / "nanobot-v0.2-slim.config.json",
    )

    _sync_runtime_from_settings(repo_root)

    assert os.environ["DEEPSEEK_API_KEY"] == "sk-fresh"
    assert os.environ["EMBEDDING_API_KEY"] == "sk-embed"
