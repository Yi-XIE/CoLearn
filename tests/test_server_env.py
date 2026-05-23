import os
from pathlib import Path
import uuid

from colearn.server import _hydrate_provider_env_aliases, _load_repo_env


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
