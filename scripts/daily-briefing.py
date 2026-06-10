#!/usr/bin/env python3
"""
daily-briefing — standalone briefing generator. Replaces the
generate_daily_briefing Letta tool + daily-schedule-agent invocation.

This script imports the existing generate_daily_briefing function from
letta/daily_briefing/generate_daily_briefing.py and runs it directly,
eliminating the "agent receives prompt → calls one tool" theater. Same
output (Gitea canonical signal + MC memfs schedule/today.md), one
fewer LLM call per tick, faster + cheaper.

Designed to be invoked from:
  - Interactive shell (manual briefing for a specific date)
  - scheduler-service `script` action type (replacing the current
    `agent_message` cron actions that target daily-schedule-agent)
  - launchd cron (alternative to scheduler-service for this one job)

Usage:
  daily-briefing.py [--target-date YYYY-MM-DD]
                    [--calendar-id <email>]
                    [--timezone <tz>]
                    [--mc-agent-id <id>]
                    [--json]

Env:
  GITEA_MEMFS_TOKEN     required (for signal + memfs writes)
  GITEA_BASE_URL        host: http://127.0.0.1:3030 (default)
                        docker: http://gitea:3000
  GWS_BIN               defaults to gws (on PATH); override if needed
  MC_AGENT_ID           defaults to agent-90b2e860-...; override per env
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make the letta/daily_briefing module importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Default to host-side Gitea endpoint when running standalone.
# The function reads GITEA_BASE_URL at runtime, so this respects any
# override (e.g., from scheduler-service which uses gitea:3000).
os.environ.setdefault("GITEA_BASE_URL", "http://127.0.0.1:3030")

# The function shells out to `gws`; ensure it's on PATH.
# Homebrew bin contains gws on this host.
existing_path = os.environ.get("PATH", "")
for required in ("/Users/dorseyhomeserver/bin", "/opt/homebrew/bin"):
    if required not in existing_path:
        os.environ["PATH"] = f"{required}:{existing_path}"
        existing_path = os.environ["PATH"]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate the daily briefing (canonical signal + MC memfs)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--target-date",
        help="YYYY-MM-DD (default: today in --timezone)",
    )
    ap.add_argument(
        "--calendar-id",
        default=os.environ.get("BRIEFING_CALENDAR_ID", "cdorsey@concord.org"),
    )
    ap.add_argument(
        "--timezone",
        default=os.environ.get("BRIEFING_TIMEZONE", "America/New_York"),
    )
    ap.add_argument(
        "--mc-agent-id",
        default=os.environ.get(
            "MC_AGENT_ID", "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"
        ),
        help="MC agent ID for memfs schedule/today.md write (default: production MC)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="emit result as JSON (default: human-readable summary)",
    )
    ap.add_argument(
        "--no-write",
        action="store_true",
        help="dry-run: generate but skip Gitea writes (DEV ONLY; not implemented yet)",
    )
    args = ap.parse_args()

    if not os.environ.get("GITEA_MEMFS_TOKEN"):
        print("ERROR: GITEA_MEMFS_TOKEN not set in env", file=sys.stderr)
        return 2

    # Allow override per-invocation
    if args.mc_agent_id:
        os.environ["MC_AGENT_ID_OVERRIDE"] = args.mc_agent_id

    if args.no_write:
        print(
            "WARNING: --no-write flag accepted but not yet honored by the "
            "underlying function; writes will still occur.",
            file=sys.stderr,
        )

    # Import inside main so any import-time errors land cleanly
    try:
        from letta.daily_briefing.generate_daily_briefing import (
            generate_daily_briefing,
        )
    except ImportError as e:
        print(f"ERROR: failed to import generate_daily_briefing: {e}", file=sys.stderr)
        return 3

    result = generate_daily_briefing(
        calendar_id=args.calendar_id,
        timezone=args.timezone,
        target_date=args.target_date,
    )

    if args.json:
        print(json.dumps(result, default=str, indent=2))
    else:
        status = result.get("status", "?")
        print(f"status: {status}")
        if "briefing" in result:
            print(f"\n─── briefing ───\n{result['briefing']}")
        if "mc_memfs_written" in result:
            print(
                f"\nmc_memfs_written={result.get('mc_memfs_written')} "
                f"path={result.get('mc_memfs_path', '?')} "
                f"url={result.get('mc_memfs_html_url', '?')[:80]}"
            )
        if "signal_path" in result:
            print(f"signal_path={result['signal_path']}")
        if status == "error":
            print(f"\nERROR: {result.get('error_message', '?')[:500]}", file=sys.stderr)
            return 4

    return 0


if __name__ == "__main__":
    sys.exit(main())
