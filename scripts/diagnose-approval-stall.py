#!/usr/bin/env python3
"""
diagnose-approval-stall.py — diagnose a wedged pa-web-ui control_request loop.

Reads pa-web-ui's logs (docker logs pa-web-ui), filters to a given
conversation, reconstructs each control_request's chain of 3 log lines:

    control_request_received  -> control_request_classified -> control_response_sent

Reports any request_id missing one or more steps. Pinpoints where the
flow broke down.

Usage:
    # Most common: latest stuck conversation
    python3 scripts/diagnose-approval-stall.py

    # Specific conversation
    python3 scripts/diagnose-approval-stall.py --conv-id conv-abc-...

    # Look further back than the default 5 min
    python3 scripts/diagnose-approval-stall.py --since 30m

    # Show only request_ids that broke the chain
    python3 scripts/diagnose-approval-stall.py --only-broken

    # Get the conv_id of any agent run currently stuck on requires_approval
    python3 scripts/diagnose-approval-stall.py --find-stuck
"""
import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta


CHAIN_KEYS = (
    "control_request_received",
    "control_request_classified",
    "control_response_sent",
)
ERROR_KEYS = (
    "control_request_dispatch_crash",
    "control_response_send_failed",
    "control_request_missing_id",
)
ALL_KEYS = CHAIN_KEYS + ERROR_KEYS


def find_stuck_conversations():
    """Query Letta for runs with stop_reason=requires_approval and an empty
    approvals list — the wedged-loop signature."""
    import urllib.request
    try:
        r = urllib.request.urlopen(
            "http://localhost:8283/v1/runs/?limit=20",
            timeout=10,
        )
        runs = json.loads(r.read())
        runs = runs if isinstance(runs, list) else runs.get("items", [])
    except Exception as e:
        print(f"  (couldn't query Letta runs: {e})")
        return []

    stuck = []
    for run in runs:
        if run.get("stop_reason") != "requires_approval":
            continue
        rid = run.get("id", "")
        try:
            rd = urllib.request.urlopen(
                f"http://localhost:8283/v1/runs/{rid}", timeout=10
            )
            rdata = json.loads(rd.read())
        except Exception:
            continue
        if not (rdata.get("approvals") or rdata.get("pending_approvals")):
            stuck.append({
                "run_id": rid,
                "agent_id": run.get("agent_id"),
                "created_at": run.get("created_at", "")[:19],
                "approvals_empty": True,
            })
    return stuck


def parse_log_line(line: str):
    """pa-web-ui uses structlog; lines look like:
       2026-04-29T01:20:00 [info] control_request_received conv_id=conv-... request_id=... subtype=can_use_tool tool_name=Bash
    Extract the event key and field=value pairs.
    """
    # Find any of our keys in the line
    event_key = None
    for k in ALL_KEYS:
        if k in line:
            event_key = k
            break
    if not event_key:
        return None

    fields = {}
    for m in re.finditer(r'(\w+)=(?:"([^"]*)"|(\S+))', line):
        k = m.group(1)
        v = m.group(2) if m.group(2) is not None else m.group(3)
        fields[k] = v

    ts_m = re.match(r'^(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})', line)
    fields["_ts"] = ts_m.group(1) if ts_m else ""
    fields["_event"] = event_key
    return fields


def get_logs(since: str):
    """docker logs pa-web-ui --since <since>"""
    out = subprocess.run(
        ["docker", "logs", "pa-web-ui", "--since", since],
        capture_output=True, text=True, check=False,
    )
    # docker logs prints stderr stream — filter for control_* lines
    return (out.stdout + out.stderr).split("\n")


def reconstruct_chains(lines, conv_id_filter=None):
    """Group log entries by request_id, return ordered dict of
    {request_id: [list of (event_key, fields_dict)]}."""
    chains = defaultdict(list)
    for line in lines:
        parsed = parse_log_line(line)
        if not parsed:
            continue
        if conv_id_filter and parsed.get("conv_id") != conv_id_filter:
            continue
        rid = parsed.get("request_id", "(no-id)")
        chains[rid].append(parsed)
    return chains


def report_chain(rid: str, events, only_broken: bool):
    seen = set(e["_event"] for e in events)
    missing_chain = [k for k in CHAIN_KEYS if k not in seen]
    has_errors = any(e["_event"] in ERROR_KEYS for e in events)

    if only_broken and not (missing_chain or has_errors):
        return False

    health = "✓ OK" if (not missing_chain and not has_errors) else "✗ BROKEN"
    print(f"\n  {health}  request_id={rid}")
    if missing_chain:
        print(f"      MISSING: {', '.join(missing_chain)}")
    for e in events:
        ts = e.get("_ts", "?")
        ev = e["_event"]
        extra = " ".join(
            f"{k}={v}" for k, v in e.items()
            if k not in ("_ts", "_event", "conv_id", "request_id")
        )
        print(f"      [{ts}] {ev}  {extra}")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--conv-id", help="Filter to one conversation")
    p.add_argument("--since", default="5m",
                   help="Docker logs window (e.g. 5m, 30m, 1h). Default 5m.")
    p.add_argument("--only-broken", action="store_true",
                   help="Show only request_ids that broke the chain")
    p.add_argument("--find-stuck", action="store_true",
                   help="List Letta runs currently wedged with requires_approval+empty approvals")
    args = p.parse_args()

    if args.find_stuck:
        print("Wedged Letta runs (requires_approval + empty approvals list):")
        stuck = find_stuck_conversations()
        if not stuck:
            print("  (none — no obvious stalls)")
        for s in stuck:
            print(f"  agent={s['agent_id']}  run={s['run_id']}  created={s['created_at']}")
        if not stuck:
            return 0
        print("\nNote: --find-stuck does not auto-pivot to a conv_id (Letta's "
              "run record doesn't carry the pa-web-ui conversation id). "
              "If you need the chain trace, find the conv_id from pa-web-ui's "
              "UI and pass --conv-id.")
        return 0

    print(f"Fetching pa-web-ui logs (--since {args.since}) ...")
    lines = get_logs(args.since)
    chains = reconstruct_chains(lines, args.conv_id)

    if not chains:
        scope = f"for conv_id={args.conv_id}" if args.conv_id else "in window"
        print(f"  No control_* log lines {scope} in the last {args.since}.")
        print("  Either no control traffic happened, or the window is too narrow.")
        return 0

    print(f"Found {len(chains)} request_id(s) with control_* events:")
    shown = 0
    for rid, events in sorted(chains.items(), key=lambda kv: kv[1][0].get("_ts","")):
        if report_chain(rid, events, args.only_broken):
            shown += 1
    if args.only_broken:
        print(f"\nShown: {shown} broken chain(s) of {len(chains)} total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
