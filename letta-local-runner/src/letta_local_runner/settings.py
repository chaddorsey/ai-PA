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
    )
