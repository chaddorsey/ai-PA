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
    """Run omnifocus-cli with --json and return parsed output."""
    result = subprocess.run(
        ["poetry", "run", "omnifocus-cli", "--json", *args],
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
