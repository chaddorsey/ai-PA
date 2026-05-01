#!/usr/local/bin/python3
"""verify-memfs-soak.py — Cycle-1 Phase F daily verification.

API-only health check for migrated memfs agents. Designed to run inside
the scheduler-service container (no docker-exec available, so this is
narrower than the host-side verify-agent-memfs.sh — substitutes API
calls for the bare-repo inspections).

Checks per agent:
  1. Agent has `git-memory-enabled` tag
  2. Agent has blocks (count > 0) with `system/` labels
  3. Each block has non-empty value (catches blocks getting nuked)
  4. Mirror writer is reachable + not halted + no excessive drift

Plus one global check:
  5. Mirror writer drift_alert_count not climbing (> baseline + 2 in 24h
     would suggest rogue writes; baseline tracked in
     /tmp/mirror-drift-baseline.json)

Exits 0 on all PASS, non-zero on any FAIL. Scheduler-service logs
output and marks the run failed/succeeded accordingly.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://letta:8283").rstrip("/")
MIRROR_HEALTH = os.environ.get(
    "MIRROR_HEALTH_URL", "http://mirror-writer:8090/health"
)
DRIFT_BASELINE_FILE = Path("/tmp/mirror-drift-baseline.json")

# Migrated in cycle-1
MIGRATED_AGENTS = [
    ("agent-892a2d58-b9f6-4baf-84f3-c431fe46487d", "calendar-agent_copy"),
    ("agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef", "MC"),
]


def _get_json(url: str, timeout: float = 15.0):
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def check_agent(agent_id: str, name: str) -> tuple[int, int, list[str]]:
    """Return (passes, fails, issues)."""
    passes = 0
    fails = 0
    issues = []

    try:
        agent = _get_json(f"{LETTA_BASE}/v1/agents/{agent_id}")
    except Exception as e:
        return (0, 1, [f"{name}: GET /v1/agents/{agent_id} failed: {e}"])

    tags = agent.get("tags") or []
    if "git-memory-enabled" in tags:
        passes += 1
    else:
        fails += 1
        issues.append(f"{name}: missing git-memory-enabled tag (have: {tags})")

    blocks = agent.get("memory", {}).get("blocks") or []
    if not blocks:
        fails += 1
        issues.append(f"{name}: 0 blocks attached (substrate broken)")
    else:
        passes += 1

    # Each block should have system/ label + non-empty value
    sys_blocks = [b for b in blocks if (b.get("label") or "").startswith("system/")]
    if sys_blocks:
        passes += 1
    else:
        fails += 1
        issues.append(
            f"{name}: 0 blocks with system/ prefix (post-memfs labels expected)"
        )

    empty_blocks = [b for b in sys_blocks if not (b.get("value") or "").strip()]
    if not empty_blocks:
        passes += 1
    else:
        fails += 1
        issues.append(
            f"{name}: {len(empty_blocks)} system blocks have empty content: "
            f"{[b['label'] for b in empty_blocks]}"
        )

    return (passes, fails, issues)


def check_mirror_writer() -> tuple[int, int, list[str]]:
    passes = 0
    fails = 0
    issues = []

    try:
        h = _get_json(MIRROR_HEALTH)
    except Exception as e:
        return (0, 1, [f"mirror-writer health unreachable: {e}"])

    if h.get("halted"):
        fails += 1
        issues.append(f"mirror-writer HALTED: {h.get('halt_reason')}")
    else:
        passes += 1

    rogue = h.get("rogue_ref_ids") or []
    if rogue:
        fails += 1
        issues.append(f"mirror-writer drift: {len(rogue)} rogue ref_ids: {rogue[:5]}")
    else:
        passes += 1

    # Drift baseline tracking
    current_drift = h.get("drift_alert_count", 0)
    baseline = 0
    if DRIFT_BASELINE_FILE.exists():
        try:
            baseline_data = json.loads(DRIFT_BASELINE_FILE.read_text())
            baseline = baseline_data.get("drift_alert_count", 0)
        except Exception:
            pass

    growth = current_drift - baseline
    if growth > 2:
        fails += 1
        issues.append(
            f"mirror-writer drift alerts climbing: {baseline} -> {current_drift} "
            f"(growth +{growth} since last check)"
        )
    else:
        passes += 1

    # Update baseline
    DRIFT_BASELINE_FILE.write_text(json.dumps({
        "drift_alert_count": current_drift,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }))

    # Lag check
    lag = h.get("last_lag_seconds", 0) or 0
    if lag > 300:
        fails += 1
        issues.append(f"mirror-writer lag: {lag}s (> 300s threshold)")
    else:
        passes += 1

    return (passes, fails, issues)


def main() -> int:
    print(f"[verify-memfs-soak] {datetime.now(timezone.utc).isoformat()}")
    total_pass = 0
    total_fail = 0
    all_issues = []

    for agent_id, name in MIGRATED_AGENTS:
        p, f, issues = check_agent(agent_id, name)
        total_pass += p
        total_fail += f
        all_issues.extend(issues)
        print(f"  {name}: pass={p} fail={f}")

    p, f, issues = check_mirror_writer()
    total_pass += p
    total_fail += f
    all_issues.extend(issues)
    print(f"  mirror-writer: pass={p} fail={f}")

    print(f"[verify-memfs-soak] TOTAL pass={total_pass} fail={total_fail}")
    if all_issues:
        print("ISSUES:")
        for i in all_issues:
            print(f"  - {i}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
