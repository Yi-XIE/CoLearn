import os

from colearn.server import _load_repo_env


def test_load_repo_env_keeps_existing_values_and_parses_quotes(tmp_path, monkeypatch):
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
