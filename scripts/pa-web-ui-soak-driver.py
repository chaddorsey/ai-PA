#!/usr/bin/env python3
"""pa-web-ui synthetic traffic driver for soak testing.

Drives realistic chat traffic through pa-web-ui's /stream endpoint to exercise
the patched letta-code subprocess pool, stream-json translation, and tool-call
round-trips. Used for Step 3a soak validation and Phase 4 canary stress.

What it does:
  1. Bootstraps CSRF cookie + token via GET /api/csrf-token
  2. Creates a dedicated soak conversation (so production convs aren't polluted)
  3. Cycles through a message bank with three classes (no-tool, single-tool,
     multi-tool) at a configurable cadence
  4. Captures per-request telemetry: status, latency, response size, error
     events, tool-call counts, stop reason
  5. Writes structured JSONL to a log file for post-soak analysis

Defaults are conservative: 10-minute interval, 24-hour total wall-clock,
~140 messages over the soak window. Cost is bounded by the agent's normal
per-message cost × ~140.

Usage:
  python3 scripts/pa-web-ui-soak-driver.py --duration 24h --interval 10m
  python3 scripts/pa-web-ui-soak-driver.py --duration 1h --interval 2m   # quick smoke
  python3 scripts/pa-web-ui-soak-driver.py --duration 5m --interval 60s  # smoke before real soak

Stop with Ctrl-C; cleanup is graceful.
"""

import argparse
import json
import os
import random
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import urllib.request
import urllib.error
import http.cookiejar

# Default endpoints — override via env or args
PA_WEB_UI_URL = os.environ.get("PA_WEB_UI_URL", "http://localhost:5200")
DEFAULT_AGENT_ID = os.environ.get(
    "MISSION_CONTROL_AGENT_ID",
    "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef",
)
LOG_DIR = Path(os.environ.get("SOAK_LOG_DIR", "/tmp/pa-web-ui-soak"))

# Three message classes by realistic ratio
MESSAGES_NO_TOOL = [
    "What's the date today?",
    "Reply with just the word PING. Nothing else.",
    "Spell the word 'soak'.",
    "Count from 1 to 5.",
    "Reply with the literal string 'OK'.",
    "What is 12 + 7?",
    "Name three primary colors in one line.",
]

MESSAGES_SINGLE_TOOL = [
    "Read /etc/hostname using the Read tool and tell me what's in it.",
    "Use Bash to run `date +%Y-%m-%d` and report the output.",
    "Use Bash to run `uname -s` and report the OS name.",
    "Use Bash to print the current working directory.",
    "Use Bash to run `echo soak-test-$(date +%s)` and report.",
    "Use Bash to run `ls /tmp | head -3` and report.",
    "Use the Glob tool to find files matching `/tmp/*.txt` and list them.",
]

MESSAGES_MULTI_TOOL = [
    "Use Bash to write 'soak-multi-test' to /tmp/pa-soak-multi.txt, then Read it back, then Bash `rm /tmp/pa-soak-multi.txt`. Confirm each step worked.",
    "Use Bash to create /tmp/pa-soak-multi-2.txt with 'hello', use Grep to verify the content matches 'hello' in /tmp/pa-soak-multi-2.txt, then Bash to delete it.",
    "Use Bash three times in one turn: 1) write 'a' to /tmp/pa-soak-a.txt, 2) write 'b' to /tmp/pa-soak-b.txt, 3) `cat /tmp/pa-soak-a.txt /tmp/pa-soak-b.txt && rm /tmp/pa-soak-a.txt /tmp/pa-soak-b.txt`.",
]


def parse_duration(s: str) -> int:
    """Parse '24h', '5m', '60s' into seconds."""
    m = re.match(r"^(\d+)([hms])$", s.strip())
    if not m:
        # bare number = seconds
        try:
            return int(s)
        except ValueError:
            raise ValueError(f"bad duration: {s!r}")
    n, unit = int(m.group(1)), m.group(2)
    return n * {"h": 3600, "m": 60, "s": 1}[unit]


def pick_message(rng: random.Random) -> tuple[str, str]:
    """Pick a message + class label by realistic distribution."""
    r = rng.random()
    if r < 0.30:
        return ("no_tool", rng.choice(MESSAGES_NO_TOOL))
    elif r < 0.80:
        return ("single_tool", rng.choice(MESSAGES_SINGLE_TOOL))
    else:
        return ("multi_tool", rng.choice(MESSAGES_MULTI_TOOL))


def bootstrap_session(base_url: str) -> tuple[http.cookiejar.CookieJar, str]:
    """GET /api/csrf-token → returns (cookie jar, token)."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(
        f"{base_url}/api/csrf-token",
        headers={"Origin": base_url},
    )
    with opener.open(req, timeout=10) as resp:
        body = json.loads(resp.read())
    token = body.get("csrf_token", "")
    if not token:
        raise RuntimeError(f"no csrf_token in response: {body}")
    return jar, token


def cookie_header(jar: http.cookiejar.CookieJar, base_url: str) -> str:
    # Emit every cookie in the jar — Python's CookieJar normalizes bare
    # hostnames to e.g. 'localhost.local', and we don't share the jar
    # across hosts in this driver.
    parts = [f"{c.name}={c.value}" for c in jar]
    return "; ".join(parts)


def create_soak_conversation(jar, token: str, base_url: str, agent_id: str, run_id: str) -> str:
    """Create a dedicated conversation so synthetic traffic doesn't pollute production."""
    label = f"soak-driver-{run_id}"
    body = json.dumps({"label": label, "agent_id": agent_id}).encode()
    req = urllib.request.Request(
        f"{base_url}/api/conversations",
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Origin": base_url,
            "X-CSRF-Token": token,
            "Cookie": cookie_header(jar, base_url),
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        d = json.loads(resp.read())
    conv_id = d.get("id") or d.get("conversation_id")
    if not conv_id:
        raise RuntimeError(f"no conversation id in response: {d}")
    return conv_id


def stream_request(
    jar, token: str, base_url: str, agent_id: str, conv_id: str, device_id: str,
    message: str,
) -> dict:
    """POST /stream and parse the SSE response, returning a summary dict.

    pa-web-ui contract: session_id is a per-device UUID, conversation_id is
    the actual letta conv_id. We pass both.

    Captures: timing, status, total bytes, last text response, error events,
    distinct tool_use names emitted in approval_request_message events,
    final stop_reason.
    """
    # NOTE: omit agent_id from /stream body — including it triggers the
    # slash-command/routing-handler path, which is the wrong dispatch for
    # plain chat messages. The device_id + conversation_id pair routes
    # through _dispatch_mission_control_direct which is what we want.
    body = json.dumps(
        {
            "message": message,
            "session_id": device_id,
            "conversation_id": conv_id,
            "device_id": device_id,
        }
    ).encode()
    req = urllib.request.Request(
        f"{base_url}/stream",
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Origin": base_url,
            "X-CSRF-Token": token,
            "Cookie": cookie_header(jar, base_url),
            "Accept": "text/event-stream",
        },
    )
    started = time.monotonic()
    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": None,
        "latency_s": None,
        "bytes": 0,
        "errors": [],
        "tool_calls": {},
        "stop_reason": None,
        "first_byte_s": None,
        "last_text_chars": 0,
    }
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            summary["status"] = resp.status
            buf = b""
            first = True
            for chunk in iter(lambda: resp.read(4096), b""):
                if first:
                    summary["first_byte_s"] = round(time.monotonic() - started, 3)
                    first = False
                buf += chunk
                summary["bytes"] += len(chunk)
            text = buf.decode("utf-8", errors="replace")
            for line in text.splitlines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if not payload:
                    continue
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                t = obj.get("type")
                if t == "error":
                    summary["errors"].append(obj.get("message", "")[:200])
                elif t == "stop_reason":
                    summary["stop_reason"] = obj.get("stop_reason")
                elif t == "tool_use":
                    name = obj.get("name") or "?"
                    summary["tool_calls"][name] = summary["tool_calls"].get(name, 0) + 1
                elif t == "message":
                    mt = obj.get("message_type")
                    if mt == "approval_request_message":
                        tc = obj.get("tool_call") or {}
                        name = tc.get("name") or "?"
                        summary["tool_calls"][name] = summary["tool_calls"].get(name, 0) + 1
                    elif mt == "assistant_message":
                        msg = obj.get("message") or {}
                        content = msg.get("content")
                        if isinstance(content, str):
                            summary["last_text_chars"] = len(content)
                        elif isinstance(content, list):
                            summary["last_text_chars"] = sum(
                                len(c.get("text", "")) for c in content if isinstance(c, dict)
                            )
                elif t == "result":
                    summary["stop_reason"] = obj.get("stop_reason") or summary["stop_reason"]
    except urllib.error.HTTPError as e:
        summary["status"] = e.code
        summary["errors"].append(f"HTTPError {e.code}: {str(e)[:120]}")
    except Exception as e:
        summary["errors"].append(f"{type(e).__name__}: {str(e)[:200]}")
    summary["latency_s"] = round(time.monotonic() - started, 3)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--duration", default="24h", help="total soak duration (e.g. 24h, 5m, 60s)")
    p.add_argument("--interval", default="10m", help="seconds between requests (e.g. 10m, 60s)")
    p.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
    p.add_argument("--base-url", default=PA_WEB_UI_URL)
    p.add_argument("--seed", type=int, default=None, help="random seed (for reproducibility)")
    p.add_argument("--max-requests", type=int, default=None, help="hard cap on total requests")
    args = p.parse_args()

    duration_s = parse_duration(args.duration)
    interval_s = parse_duration(args.interval)
    rng = random.Random(args.seed)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"soak-{run_id}.jsonl"

    print(f"[soak] run_id={run_id}")
    print(f"[soak] log: {log_path}")
    print(f"[soak] duration={duration_s}s interval={interval_s}s")

    jar, token = bootstrap_session(args.base_url)

    # Extract device_id from cookie jar (set by ingress_guard during csrf-token bootstrap)
    device_id = ""
    for c in jar:
        if c.name == "pa_device_id":
            device_id = c.value
            break
    if not device_id:
        device_id = f"soak-driver-{run_id}"
        print(f"[soak] no pa_device_id cookie; using synthetic {device_id}")

    conv_id = create_soak_conversation(jar, token, args.base_url, args.agent_id, run_id)
    print(f"[soak] conv_id={conv_id}")
    print(f"[soak] device_id={device_id}")

    stop = {"flag": False}

    def handle_signal(signum, frame):
        print(f"[soak] received signal {signum}; stopping at next cycle boundary")
        stop["flag"] = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    started_at = time.monotonic()
    n_total = 0
    n_ok = 0
    n_err = 0

    with log_path.open("a") as f:
        # Header record
        header = {
            "type": "header",
            "run_id": run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "duration_s": duration_s,
            "interval_s": interval_s,
            "agent_id": args.agent_id,
            "base_url": args.base_url,
            "conv_id": conv_id,
            "seed": args.seed,
        }
        f.write(json.dumps(header) + "\n")
        f.flush()

        while not stop["flag"]:
            elapsed = time.monotonic() - started_at
            if elapsed >= duration_s:
                break
            if args.max_requests and n_total >= args.max_requests:
                break

            cls, msg = pick_message(rng)
            n_total += 1
            print(f"[soak] #{n_total} cls={cls} msg={msg[:60]!r}")

            try:
                summary = stream_request(
                    jar, token, args.base_url, args.agent_id, conv_id, device_id, msg
                )
            except Exception as e:
                summary = {"errors": [f"{type(e).__name__}: {e}"], "status": None, "latency_s": None}

            ok = summary.get("status") == 200 and not summary.get("errors")
            n_ok += 1 if ok else 0
            n_err += 0 if ok else 1

            record = {
                "type": "request",
                "n": n_total,
                "class": cls,
                "msg_preview": msg[:80],
                **summary,
            }
            f.write(json.dumps(record) + "\n")
            f.flush()

            print(
                f"[soak]   status={summary.get('status')} "
                f"lat={summary.get('latency_s')}s "
                f"bytes={summary.get('bytes')} "
                f"tools={summary.get('tool_calls')} "
                f"stop={summary.get('stop_reason')} "
                f"err={len(summary.get('errors') or [])}"
            )

            # sleep with periodic stop-flag check
            slept = 0
            while slept < interval_s and not stop["flag"]:
                t = min(5, interval_s - slept)
                time.sleep(t)
                slept += t

        # Footer
        footer = {
            "type": "footer",
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(time.monotonic() - started_at, 1),
            "total_requests": n_total,
            "ok": n_ok,
            "errors": n_err,
            "interrupted": stop["flag"],
        }
        f.write(json.dumps(footer) + "\n")

    print(f"[soak] DONE n_total={n_total} ok={n_ok} err={n_err} log={log_path}")


if __name__ == "__main__":
    main()
