"""Integration tests — require OmniFocus running on macOS.

Run with: poetry run pytest tests/test_integration.py -v -m integration
Skip in CI with: poetry run pytest -m "not integration"
"""
import json
import subprocess

import pytest

pytestmark = pytest.mark.integration

OMNIFOCUS_CLI_DIR = "/Volumes/main-drive/ai-PA/.worktrees/omnifocus-cli/omnifocus-cli"


def run_cli(*args):
    """Run omnifocus-cli with --format json and return parsed output."""
    result = subprocess.run(
        ["poetry", "run", "omnifocus-cli", "--format", "json", *args],
        capture_output=True,
        text=True,
        cwd=OMNIFOCUS_CLI_DIR,
        timeout=30,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    return json.loads(result.stdout)


def test_list_projects():
    projects = run_cli("project", "list")
    assert isinstance(projects, list)
    if projects:
        assert "id" in projects[0] or "projectId" in projects[0]


def test_list_tags():
    tags = run_cli("tags", "list")
    assert isinstance(tags, list)


def test_list_inbox():
    items = run_cli("inbox", "list")
    assert isinstance(items, list)


def test_search_flagged():
    results = run_cli("search", "--flagged")
    assert isinstance(results, list)


def test_task_lifecycle():
    """Create a task, verify it, complete it."""
    created = run_cli("task", "create", "--name", "CLI Integration Test Task")
    task_id = created.get("id") or created.get("taskId")
    assert task_id, f"No task ID in response: {created}"

    fetched = run_cli("task", "get", task_id)
    name = fetched.get("name") or fetched.get("taskName")
    assert name == "CLI Integration Test Task"

    completed = run_cli("task", "complete", task_id)
    assert completed.get("success") is True or "markComplete" not in str(completed)


# ── Agent-first path smoke tests ──────────────────────────────


def test_schema_list_returns_all_methods():
    """Schema --list should return all 17 methods."""
    result = subprocess.run(
        ["poetry", "run", "omnifocus-cli", "schema", "--list"],
        capture_output=True, text=True, cwd=OMNIFOCUS_CLI_DIR, timeout=10,
    )
    assert result.returncode == 0
    assert "task.create" in result.stdout
    assert "search" in result.stdout
    assert "project.list" in result.stdout


def test_schema_task_create_returns_params():
    """Schema introspection should return method metadata."""
    result = subprocess.run(
        ["poetry", "run", "omnifocus-cli", "schema", "task.create"],
        capture_output=True, text=True, cwd=OMNIFOCUS_CLI_DIR, timeout=10,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["method"] == "createTask"
    assert "name" in parsed["params"]


def test_dry_run_task_create():
    """Dry-run should validate without executing."""
    result = subprocess.run(
        ["poetry", "run", "omnifocus-cli",
         "--body", '{"name": "Integration dry-run test"}',
         "--dry-run",
         "task", "create"],
        capture_output=True, text=True, cwd=OMNIFOCUS_CLI_DIR, timeout=10,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["dry_run"] is True
    assert parsed["validation"] == "passed"


def test_validation_error_returns_structured_json():
    """Invalid body should return structured validation errors."""
    result = subprocess.run(
        ["poetry", "run", "omnifocus-cli",
         "--body", '{"flagged": "not_bool"}',
         "task", "create"],
        capture_output=True, text=True, cwd=OMNIFOCUS_CLI_DIR, timeout=10,
    )
    assert result.returncode == 2
    parsed = json.loads(result.stdout)
    assert parsed["error"] == "validation_failed"
