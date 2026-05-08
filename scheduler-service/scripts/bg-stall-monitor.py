#!/usr/local/bin/python3
"""
bg-stall-monitor.py — detect Letta bg-run silent stalls (issue #99).

Scans recent (background=True, status=completed, stop_reason=end_turn) Letta
runs and flags any whose step records show real LLM work
(completion_tokens-reasoning_tokens > THRESHOLD) but persisted zero
assistant_message / tool_call_message / reasoning_message records.

That pattern matches the pa-web-ui MC silent-stall observed 2026-05-08:
runs complete cleanly, the LLM emits content, but Letta's bg-path
stream→Message-DB pipeline doesn't materialize anything except the
user_message. A clean letta+pa-web-ui restart fixed it.

This monitor doesn't auto-remediate. It emits a pipeline-health signal
to agents-canonical so the steward daily rollup surfaces it, and exits 1
when stalls are found so the scheduler logs the failure.

Idempotent: same date overwrites the signal file.

Usage (cron, every ~10 min during active hours):
    bg-stall-monitor.py --window-min 30
    bg-stall-monitor.py --window-min 30 --threshold-tokens 50

Exit codes:
  0 = scanned cleanly, no stalls
  1 = stalls detected (signal emitted with attention_level=urgent)
  2 = config error (no Letta URL, no Gitea token)
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


LETTA = os.environ.get("LETTA_BASE_URL", "http://letta:8283")
GITEA = os.environ.get("GITEA_BASE_URL", "http://gitea:3000")
REPO = "agents/agents-canonical"
ENV_PATH = "/workspace/.env"


def read_env(name):
    if name in os.environ:
        return os.environ[name]
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


GITEA_TOKEN = read_env("GITEA_MEMFS_TOKEN")
if not GITEA_TOKEN:
    sys.stderr.write("FATAL: no GITEA_MEMFS_TOKEN\n")
    sys.exit(2)


def http_get_json(url, timeout=15):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def gitea_get(path):
    url = f"{GITEA}/api/v1/repos/{REPO}/{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"token {GITEA_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def gitea_put(path_rel, content, msg):
    url = f"{GITEA}/api/v1/repos/{REPO}/contents/{path_rel}"
    existing = gitea_get(f"contents/{path_rel}?ref=main")
    sha = existing.get("sha") if existing else None
    body = {
        "branch": "main",
        "content": base64.b64encode(content.encode()).decode(),
        "message": msg,
    }
    method = "PUT" if sha else "POST"
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"token {GITEA_TOKEN}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fetch_recent_runs(window_min):
    """Return Letta runs created within window_min minutes."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_min)
    try:
        runs = http_get_json(f"{LETTA}/v1/runs/?limit=200")
    except Exception as e:
        sys.stderr.write(f"WARN: cannot fetch runs: {e}\n")
        return []
    if isinstance(runs, dict):
        runs = runs.get("runs") or runs.get("items") or runs.get("data") or []
    out = []
    for r in runs:
        ts = r.get("created_at") or ""
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
        if t >= cutoff:
            out.append(r)
    return out


def fetch_steps(run_id):
    try:
        return http_get_json(f"{LETTA}/v1/runs/{run_id}/steps")
    except Exception:
        return []


def fetch_run_messages(run_id):
    try:
        return http_get_json(f"{LETTA}/v1/runs/{run_id}/messages")
    except Exception:
        return []


def is_stalled(run, threshold):
    """Return (stalled: bool, reason: str, real_tokens: int) for one run."""
    if not run.get("background"):
        return False, "sync run", 0
    if run.get("status") != "completed":
        return False, f"status={run.get('status')}", 0
    if run.get("stop_reason") not in ("end_turn", "finished", None):
        return False, f"stop_reason={run.get('stop_reason')}", 0

    steps = fetch_steps(run.get("id"))
    real_tokens = 0
    for s in steps:
        ct = s.get("completion_tokens") or 0
        rt = s.get("reasoning_tokens") or 0
        real_tokens += max(0, ct - rt)
    if real_tokens < threshold:
        return False, f"real_tokens={real_tokens} below threshold", real_tokens

    msgs = fetch_run_messages(run.get("id"))
    output_msgs = [
        m
        for m in msgs
        if m.get("message_type") in ("assistant_message", "tool_call_message", "reasoning_message")
    ]
    if output_msgs:
        return False, f"persisted {len(output_msgs)} output msgs", real_tokens

    return True, f"{real_tokens} real tokens, 0 persisted output messages", real_tokens


def emit_stall_signal(stalls, today_str, now_iso):
    """Write signal file to agents-canonical/signals/{today}/bg-stall-monitor-pipeline-health.md."""
    lines = [
        "---",
        "description: Letta bg-run silent stalls detected (issue #99 regression)",
        "source: bg-stall-monitor",
        "attention_level: urgent",
        "mentioned_entities: []",
        f"composed_at: {now_iso}",
        f"date: {today_str}",
        f"stalls_detected: {len(stalls)}",
        "---",
        "",
        f"# bg-run silent stalls — {today_str}",
        "",
        f"Detected {len(stalls)} Letta bg run(s) where the LLM emitted",
        "real output but Letta persisted zero assistant/tool/reasoning",
        "messages. This matches the issue #99 pattern. Mitigation:",
        "`docker compose restart letta pa-web-ui`.",
        "",
        "## Stalled runs",
        "",
    ]
    for s in stalls:
        r = s["run"]
        lines.append(
            f"- `{r.get('id','')[:30]}` agent=`{r.get('agent_id','')[:30]}` "
            f"created={r.get('created_at','')[:19]} "
            f"real_tokens={s['real_tokens']} reason='{s['reason']}'"
        )
    lines.append("")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--window-min", type=int, default=30)
    p.add_argument("--threshold-tokens", type=int, default=50)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    runs = fetch_recent_runs(args.window_min)
    bg_runs = [r for r in runs if r.get("background")]
    print(
        f"scanned {len(runs)} runs in last {args.window_min}m "
        f"({len(bg_runs)} bg=True)"
    )

    stalls = []
    for r in bg_runs:
        stalled, reason, tokens = is_stalled(r, args.threshold_tokens)
        if stalled:
            stalls.append({"run": r, "reason": reason, "real_tokens": tokens})
            print(f"  STALL: {r.get('id','')[:30]}  agent={r.get('agent_id','')[:30]}  {reason}")

    if not stalls:
        print("no stalls detected")
        return 0

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    body = emit_stall_signal(stalls, today_str, now_utc.isoformat())
    target = f"signals/{today_str}/bg-stall-monitor-pipeline-health.md"

    if args.dry_run:
        print(f"\n--- would write {target} ---")
        print(body)
        return 1

    gitea_put(target, body, f"signal: {target} ({len(stalls)} bg stall(s))")
    print(f"signal emitted: {target}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
