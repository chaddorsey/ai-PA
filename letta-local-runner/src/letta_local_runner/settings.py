"""Config — read from env at startup."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    letta_bin: str
    backend_dir: Path
    log_dir: Path
    default_timeout_seconds: int
    race_recovery_delay_seconds: float
    listen_host: str
    listen_port: int
    # memfs Gitea sync (Option C: runner-side wrapper — pull-rebase before a run,
    # push-with-rebase-retry after). letta-code commits memfs writes locally
    # (LETTA_MEMFS_LOCAL=1); the runner owns hub sync. Per-agent serialized by the
    # existing invoke() lock. Best-effort: a sync failure never fails the agent run.
    memfs_sync_enabled: bool = True
    memfs_remote: str = "gitea"
    memfs_branch: str = "main"
    git_timeout_seconds: int = 30


def load() -> Settings:
    home = Path(os.path.expanduser("~"))
    return Settings(
        letta_bin=os.environ.get("LETTA_BIN", "/opt/homebrew/bin/letta"),
        backend_dir=Path(
            os.environ.get(
                "LETTA_LOCAL_BACKEND_DIR",
                str(home / ".letta" / "lc-local-backend"),
            )
        ),
        log_dir=Path(
            os.environ.get(
                "LETTA_LOCAL_RUNNER_LOG_DIR",
                str(home / "Library" / "Logs" / "letta-local-runner"),
            )
        ),
        default_timeout_seconds=int(os.environ.get("LETTA_LOCAL_RUNNER_DEFAULT_TIMEOUT", "600")),
        race_recovery_delay_seconds=float(
            os.environ.get("LETTA_LOCAL_RUNNER_RACE_DELAY", "0.5")
        ),
        listen_host=os.environ.get("LETTA_LOCAL_RUNNER_HOST", "127.0.0.1"),
        listen_port=int(os.environ.get("LETTA_LOCAL_RUNNER_PORT", "8920")),
        memfs_sync_enabled=os.environ.get("LETTA_LOCAL_RUNNER_MEMFS_SYNC", "1")
        not in ("0", "false", "False", ""),
        memfs_remote=os.environ.get("LETTA_LOCAL_RUNNER_MEMFS_REMOTE", "gitea"),
        memfs_branch=os.environ.get("LETTA_LOCAL_RUNNER_MEMFS_BRANCH", "main"),
        git_timeout_seconds=int(os.environ.get("LETTA_LOCAL_RUNNER_GIT_TIMEOUT", "30")),
    )
