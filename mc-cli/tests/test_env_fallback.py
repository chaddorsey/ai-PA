import os
import sys
from pathlib import Path

# Import from source (mc-cli is editable-installed; tests run without packaging).
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import mc_cli.cli as cli  # noqa: E402


def test_ensure_env_backfills_missing_from_dotenv(tmp_path, monkeypatch):
    """A missing GITHUB_TOKEN is loaded from REPO_ROOT/.env (the runner-env path)."""
    (tmp_path / ".env").write_text('GITHUB_TOKEN="ghp_test123"\nOTHER=ignored\n')
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    cli._ensure_env_from_dotenv("GITHUB_TOKEN")
    assert os.environ["GITHUB_TOKEN"] == "ghp_test123"


def test_ensure_env_does_not_override_existing(tmp_path, monkeypatch):
    """An already-set env var wins over the .env file (shell/plist takes precedence)."""
    (tmp_path / ".env").write_text("GITHUB_TOKEN=fromfile\n")
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "fromenv")
    cli._ensure_env_from_dotenv("GITHUB_TOKEN")
    assert os.environ["GITHUB_TOKEN"] == "fromenv"


def test_ensure_env_no_dotenv_is_safe(tmp_path, monkeypatch):
    """Missing .env file is a no-op, not an error."""
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)  # empty dir, no .env
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    cli._ensure_env_from_dotenv("GITHUB_TOKEN")  # must not raise
    assert os.environ.get("GITHUB_TOKEN") is None
