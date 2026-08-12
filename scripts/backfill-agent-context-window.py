#!/usr/bin/env python3
"""Backfill model_settings.context_window_limit on local letta-code agents.

WHY: letta-code 0.30.19's effectiveContextWindow() reads
`model_settings.context_window_limit`. Agents created before that field
existed have only a synthesized legacy `llm_config.context_window` (which is
NOT stored in the agent file and is NOT consulted), so the effective window
resolves to `undefined`. With an undefined window, sliding compaction cannot
use a token target, falls back to a message-percentage scan, and (with no
"meaningful-progress" guard) degrades to cutoff-index-1 no-op compactions that
wedge the conversation (see docs/plans/2026-08-12-enrichment-loop-context-lifetime-design.md
and docs/followups/2026-08-10-letta-code-byok-context-window-128k-default.md).

Setting model_settings.context_window_limit makes the window resolve, restoring
healthy token-target compaction.

VALUE (128000, override with CONTEXT_WINDOW_LIMIT env): a deliberately
cost-bounded ceiling for long-lived push-driven residents (compaction triggers
near limit-16384 ~= 111.6k, capping steady-state context cost). This is
intentionally BELOW the real model windows in litellm/model-context-windows.json
(gpt-5.2=400k, deepseek-v4-flash=1M, etc.), which target interactive Mission
Control use where the full window is wanted. It is <= every affected model's
real window, so the provider never rejects before compaction fires. Per-call
context minimisation is the App Server per-task-conversation migration's job,
not this backfill's.

IDEMPOTENT: only touches agents whose model_settings.context_window_limit is
absent; agents that already have any value are left unchanged. Backs up each
file it edits to <file>.bak-cwl before writing.

Live residents load agent config at spawn, so recycle the push-receiver
(launchctl kickstart -k gui/$(id -u)/com.ai-pa.letta-push-receiver) after a
backfill for running residents to pick up the new value.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CONTEXT_WINDOW_LIMIT = int(os.environ.get("CONTEXT_WINDOW_LIMIT", "128000"))
BACKEND_DIR = Path(
    os.environ.get("LETTA_LOCAL_BACKEND_DIR", os.path.expanduser("~/.letta/lc-local-backend"))
)
AGENTS_DIR = BACKEND_DIR / "agents"
DRY_RUN = "--apply" not in sys.argv
# --only-named skips default-named throwaway agents (letta agents create defaults
# the name to "Letta Code"); targets only curated production agents.
ONLY_NAMED = "--only-named" in sys.argv
GENERIC_NAME = "Letta Code"


def main() -> int:
    if not AGENTS_DIR.is_dir():
        print(f"ERROR: agents dir not found: {AGENTS_DIR}", file=sys.stderr)
        return 1

    changed, skipped = [], []
    for f in sorted(AGENTS_DIR.glob("*.json")):
        if f.name.endswith(".bak-cwl"):
            continue
        try:
            d = json.loads(f.read_text())
        except Exception as e:
            print(f"  SKIP (unreadable): {f.name}: {e}")
            continue
        ms = d.get("model_settings")
        if not isinstance(ms, dict):
            # No model_settings block at all — not a normal local agent; skip.
            continue
        name = d.get("name", "?")
        model = d.get("model", "?")
        existing = ms.get("context_window_limit")
        if existing is not None:
            skipped.append((name, model, existing))
            continue
        if ONLY_NAMED and name == GENERIC_NAME:
            continue  # skip default-named throwaway agents
        changed.append((name, model, f))
        if not DRY_RUN:
            f.with_suffix(f.suffix + ".bak-cwl").write_text(json.dumps(d, indent=2))
            ms["context_window_limit"] = CONTEXT_WINDOW_LIMIT
            f.write_text(json.dumps(d, indent=2))

    verb = "WOULD SET" if DRY_RUN else "SET"
    print(f"== backfill context_window_limit={CONTEXT_WINDOW_LIMIT} (dry_run={DRY_RUN}) ==")
    for name, model, _ in changed:
        print(f"  {verb}: {name:34} (model {model})")
    print(f"-- already had a value (unchanged): {len(skipped)} --")
    for name, model, val in skipped:
        print(f"  ok: {name:34} cwl={val} (model {model})")
    if DRY_RUN and changed:
        print("\nRe-run with --apply to write, then recycle the push-receiver.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
