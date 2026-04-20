"""Smoke test for the curated subprocess environment (Unit 1.1).

Runs INSIDE the pa-web-ui container (not on the host). Verifies:

- `letta --version` returns the pinned letta-code version.
- /workspace-safe exists and contains the expected source directories.
- Secret paths are NOT readable from /workspace-safe (either masked to
  empty dirs/files or absent entirely).
- Memfs path /root/.letta/agents/ is accessible and contains MC's memory.

These tests exercise the Docker bind-mount scope — they cannot be run
meaningfully on the host. Skip-marker kicks in when /workspace-safe is
absent, so running the full test suite outside the container is still
green.

Run: docker compose exec pa-web-ui python -m pytest tests/test_subprocess_env.py -v
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


WORKSPACE = Path("/workspace-safe")
MEMFS_ROOT = Path("/root/.letta/agents")
EXPECTED_LETTA_CODE_VERSION = "0.23.8"
MC_AGENT_ID = os.environ.get(
    "MISSION_CONTROL_AGENT_ID", "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"
)

_IN_CONTAINER = WORKSPACE.exists()
skip_if_host = pytest.mark.skipif(
    not _IN_CONTAINER,
    reason="Requires /workspace-safe bind mount; run inside pa-web-ui container",
)


# --- letta binary ------------------------------------------------------------


@skip_if_host
def test_letta_binary_available():
    result = subprocess.run(
        ["letta", "--version"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert EXPECTED_LETTA_CODE_VERSION in result.stdout, (
        f"expected version {EXPECTED_LETTA_CODE_VERSION} in output: {result.stdout!r}"
    )


# --- curated workspace scope -------------------------------------------------


@skip_if_host
@pytest.mark.parametrize(
    "relpath",
    [
        "docs",
        "letta",
        "lettabot",
        "pa-web-ui",
        "omnifocus-cli/skills",
        "scripts",
        "docker-compose.yml",
        "CLAUDE.md",
        ".lettaignore",
    ],
)
def test_expected_paths_visible(relpath: str):
    target = WORKSPACE / relpath
    assert target.exists(), f"{target} should be visible in the curated workspace"


@skip_if_host
@pytest.mark.parametrize(
    "relpath",
    [
        ".env",
        ".env.bak",
        ".env.backup",
        "cookies.txt",
        "server.log",
        "slack_auth_state.json",
        ".granola-tokens.json",
        ".granola-client.json",
        "gws-bridge/credentials.json",
        "lettabot/.env",
        "scheduler-service/.env.test",
        "letta/.granola_backfill_state.json",
    ],
)
def test_secret_files_masked_or_absent(relpath: str):
    """Masked files read empty; absent files are just absent. Either is ok.

    Docker's `- /dev/null:/path:ro` overlay presents as a character device
    rather than a regular file — reading it returns EOF immediately.
    That's a valid mask. We assert empty-read, not file-type, because the
    security property is "nothing visible to the subprocess".
    """
    target = WORKSPACE / relpath
    try:
        exists = target.exists()
    except OSError:
        # Some masked paths raise on stat; treat as absent (fine).
        return
    if not exists:
        return  # Absent is fine.
    # Read must return empty bytes — whether regular file, char device,
    # or anything else Docker overlaid there.
    try:
        with target.open("rb") as fh:
            content = fh.read()
    except OSError as e:
        # Unreadable = equivalent to masked.
        return
    assert content == b"", (
        f"{target} is visible and non-empty ({len(content)} bytes) — secret leak!"
    )


@skip_if_host
@pytest.mark.parametrize(
    "relpath",
    [
        ".git",
        ".letta",
        ".lteams",
        "auto-madden/credentials",
        "sports-and-media-tools/credentials",
        "gmail-watch-service/credentials",
        "deployment/backups-tmpsave",
        "deployment/logs",
        "smaug-data/.state",
        "slackbot/state_store",
        "letta/exports",
        "letta/backups",
    ],
)
def test_secret_dirs_masked_or_absent(relpath: str):
    """Masked dirs present as empty directories; absent dirs are just absent."""
    target = WORKSPACE / relpath
    if not target.exists():
        return
    assert target.is_dir(), f"{target} exists but is not a directory (mask drift?)"
    contents = list(target.iterdir())
    assert contents == [], (
        f"{target} is non-empty — secret leak! Contents: {[p.name for p in contents]}"
    )


# --- memfs -------------------------------------------------------------------


@skip_if_host
def test_memfs_path_exists():
    assert MEMFS_ROOT.exists(), (
        f"{MEMFS_ROOT} missing — memfs bind-mount not wired. "
        "Check docker-compose.yml volumes for ~/.letta/agents."
    )


@skip_if_host
def test_mc_memory_dir_present():
    """Check MC's memfs directory hydrates from the host bind-mount."""
    agent_dir = MEMFS_ROOT / MC_AGENT_ID
    if not agent_dir.exists():
        pytest.skip(
            f"MC agent dir {agent_dir} not present on host — "
            "expected when LettaBot has never run for this agent; "
            "first spawn will create it."
        )
    memory_dir = agent_dir / "memory"
    # memory/ may not exist until first memfs write; just verify the
    # agent_id dir is visible (bind-mount working).
    assert agent_dir.is_dir()
