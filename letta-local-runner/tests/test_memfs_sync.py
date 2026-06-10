"""memfs Gitea-sync wrapper tests (Option C).

These exercise the real git helpers (_memfs_sync_pull / _memfs_sync_push)
against real temporary git repos — NO subprocess mocking — so the rebase /
push-retry / contention behavior is verified for real. The invoke()-path
tests (test_invoker.py) keep sync disabled via the conftest fixture.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from letta_local_runner.invoker import Invoker

AGENT = "agent-local-SYNC1"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _commit(cwd: Path, filename: str, content: str, msg: str) -> None:
    (cwd / filename).write_text(content)
    _git(cwd, "add", filename)
    _git(cwd, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", msg)


@pytest.fixture
def hub_and_memfs(invoker: Invoker):
    """Create a bare 'hub' repo + a working memfs clone at the path the invoker
    expects (backend/memfs/<agent>/memory), with remote 'gitea' -> hub.
    Returns (hub_path, memfs_path)."""
    backend = invoker.settings.backend_dir
    hub = backend / "hub.git"
    hub.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", "-b", "main", str(hub)],
                   check=True, capture_output=True)

    mem = invoker._memfs_dir(AGENT)
    mem.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", str(mem)],
                   check=True, capture_output=True)
    _commit(mem, "seed.md", "seed\n", "seed commit")
    _git(mem, "remote", "add", "gitea", str(hub))
    _git(mem, "push", "-u", "gitea", "main")
    return hub, mem


def _hub_head(hub: Path) -> str:
    return _git(hub, "rev-parse", "main")


def _second_clone_advances_hub(hub: Path, tmp_path: Path, line: str) -> str:
    """Simulate another instance pushing to the hub. Returns new hub head."""
    clone = tmp_path / "clone2"
    subprocess.run(["git", "clone", str(hub), str(clone)],
                   check=True, capture_output=True)
    _commit(clone, "from_other.md", line, "other instance edit")
    _git(clone, "push", "origin", "main")
    return _hub_head(hub)


# ---- push -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_push_sends_local_commit_to_hub(invoker, hub_and_memfs):
    hub, mem = hub_and_memfs
    _commit(mem, "note.md", "local change\n", "local edit")
    local_head = _git(mem, "rev-parse", "HEAD")

    await invoker._memfs_sync_push(AGENT)

    assert _hub_head(hub) == local_head, "hub should hold the pushed local commit"


@pytest.mark.asyncio
async def test_push_rebases_and_keeps_both_on_contention(invoker, hub_and_memfs, tmp_path):
    """The key Option-C guarantee: when the hub advanced underneath us, the
    push-retry rebases and BOTH edits survive (graceful, no clobber)."""
    hub, mem = hub_and_memfs
    # hub advances from "another instance"
    _second_clone_advances_hub(hub, tmp_path, "other line\n")
    # meanwhile this instance commits its own change to a DIFFERENT file
    _commit(mem, "mine.md", "my line\n", "my edit")

    await invoker._memfs_sync_push(AGENT)

    # hub now has both files; nothing lost
    files = _git(hub, "ls-tree", "-r", "--name-only", "main").split()
    assert "from_other.md" in files, "other instance's edit must survive"
    assert "mine.md" in files, "this instance's edit must be pushed"


# ---- pull -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pull_brings_remote_commits(invoker, hub_and_memfs, tmp_path):
    hub, mem = hub_and_memfs
    _second_clone_advances_hub(hub, tmp_path, "remote only\n")
    assert not (mem / "from_other.md").exists()

    await invoker._memfs_sync_pull(AGENT)

    assert (mem / "from_other.md").exists(), "pull should bring the remote file local"


# ---- safety: skip / never raise --------------------------------------------

@pytest.mark.asyncio
async def test_sync_noop_when_no_gitea_remote(invoker):
    """A memfs git repo with no 'gitea' remote is skipped silently."""
    mem = invoker._memfs_dir("agent-local-NOREMOTE")
    mem.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", str(mem)],
                   check=True, capture_output=True)
    _commit(mem, "x.md", "x\n", "x")
    # must not raise
    await invoker._memfs_sync_pull("agent-local-NOREMOTE")
    await invoker._memfs_sync_push("agent-local-NOREMOTE")


@pytest.mark.asyncio
async def test_sync_noop_when_not_a_git_repo(invoker):
    """No memfs dir / not a git repo -> skipped silently."""
    await invoker._memfs_sync_pull("agent-local-GHOST")
    await invoker._memfs_sync_push("agent-local-GHOST")


@pytest.mark.asyncio
async def test_push_failure_does_not_raise(invoker, hub_and_memfs):
    """If the remote is unreachable, push fails but the call never raises
    (best-effort: the agent run already succeeded)."""
    hub, mem = hub_and_memfs
    # point the remote at a non-existent path
    _git(mem, "remote", "set-url", "gitea", str(invoker.settings.backend_dir / "does-not-exist.git"))
    _commit(mem, "note.md", "change\n", "edit")
    # must not raise
    await invoker._memfs_sync_push(AGENT)
