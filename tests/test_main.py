"""Tests for _load_env, which lives in shuper_whisper.app.

main.py is a thin wrapper around shuper_whisper.app:main -- the helpers moved
into the package so the packaged entry point gets them too (issue #11).
"""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shuper_whisper.app as main_module  # noqa: E402


class TestLoadEnv:
    def test_loads_env_from_config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "config_dir", lambda: str(tmp_path))
        (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=test-key-123\n")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        main_module._load_env()

        assert os.environ["ANTHROPIC_API_KEY"] == "test-key-123"
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def test_noop_when_no_env_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main_module, "config_dir", lambda: str(tmp_path))
        monkeypatch.delenv("SOME_UNSET_KEY", raising=False)

        main_module._load_env()  # should not raise

        assert "SOME_UNSET_KEY" not in os.environ

    def test_does_not_check_hardcoded_dev_path(self):
        import inspect

        src = inspect.getsource(main_module._load_env)
        assert "D:/dev" not in src
        assert '"D:"' not in src
