"""CLI tests — schema/dry-run/health use no mocking; live commands would need auth."""
from __future__ import annotations

import json

from click.testing import CliRunner

from notebooklm_cli.cli import cli

runner = CliRunner()


def test_schema_list():
    result = runner.invoke(cli, ["schema", "--list"])
    assert result.exit_code == 0
    assert "notebook.create" in result.output
    assert "source.add-url" in result.output
    assert "chat.ask" in result.output


def test_schema_detail():
    result = runner.invoke(cli, ["schema", "notebook.create"])
    assert result.exit_code == 0
    assert "title" in result.output


def test_schema_unknown():
    result = runner.invoke(cli, ["schema", "bogus.thing"])
    assert result.exit_code != 0


def test_dry_run_valid():
    result = runner.invoke(cli, ["--body", '{"title": "Test"}', "--dry-run", "notebook", "create"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data.get("dry_run") is True
    assert data.get("validation") == "passed"


def test_dry_run_invalid():
    result = runner.invoke(cli, ["--body", '{}', "--dry-run", "notebook", "create"])
    assert result.exit_code == 2
    assert "title" in result.output


def test_dry_run_invalid_json():
    result = runner.invoke(cli, ["--body", "not-json{}", "--dry-run", "notebook", "create"])
    assert result.exit_code == 2
    assert "invalid_json" in result.output.lower() or "json" in result.output.lower()


def test_health_no_auth(tmp_path):
    """Health should report error when no storage_state.json exists."""
    result = runner.invoke(cli, ["--storage", str(tmp_path / "nonexistent.json"), "health"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "error"
    assert "not found" in data.get("error_message", "").lower()


def test_dry_run_with_body_and_flags():
    """--body should override convenience flags with a warning."""
    result = runner.invoke(
        cli,
        ["--body", '{"title": "FromBody"}', "--dry-run", "notebook", "create", "--title", "FromFlag"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # Warning goes to stderr; JSON is in stdout. CliRunner may mix them.
    # Find the JSON portion of output.
    lines = result.output.strip().split("\n")
    json_start = next(i for i, l in enumerate(lines) if l.strip().startswith("{"))
    data = json.loads("\n".join(lines[json_start:]))
    assert data["params"]["title"] == "FromBody"


def test_dry_run_convenience_flags_only():
    """Convenience flags without --body should work."""
    result = runner.invoke(
        cli,
        ["--dry-run", "notebook", "create", "--title", "FromFlag"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["params"]["title"] == "FromFlag"


def test_schema_no_args():
    """schema with no args should show usage help."""
    result = runner.invoke(cli, ["schema"])
    assert result.exit_code != 0


def test_notebook_group_exists():
    result = runner.invoke(cli, ["notebook", "--help"])
    assert result.exit_code == 0
    assert "create" in result.output


def test_source_group_exists():
    result = runner.invoke(cli, ["source", "--help"])
    assert result.exit_code == 0
    assert "add-url" in result.output


def test_artifact_group_exists():
    result = runner.invoke(cli, ["artifact", "--help"])
    assert result.exit_code == 0
    assert "generate" in result.output


def test_chat_group_exists():
    result = runner.invoke(cli, ["chat", "--help"])
    assert result.exit_code == 0
    assert "ask" in result.output


def test_research_group_exists():
    result = runner.invoke(cli, ["research", "--help"])
    assert result.exit_code == 0
    assert "start" in result.output


def test_note_group_exists():
    result = runner.invoke(cli, ["note", "--help"])
    assert result.exit_code == 0
    assert "create" in result.output
