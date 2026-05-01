#!/usr/local/bin/python3
"""
daily-schedule-lookahead.py — Stage-1 lookahead briefing pre-write.

Once daily, asks daily-schedule-agent to generate_daily_briefing for
target_date in [today+2 .. today+13] (Eastern Time). Today and tomorrow
are already handled by the existing "Gold-Standard Briefing Update" +
"Off-Hours - Next Day" crons; this script fills the next-12-day window
so MC can answer "what's my Friday" and "do I have 2 free hours next
Tuesday afternoon" without on-demand calendar work.

Each call writes a `signals/{target_date}/schedule.md` file in
agents-canonical (the agent's existing tool path).

Strategy: fire-and-forget POST to /messages/async per offset, in parallel.
The agent serializes its own runs internally; we don't block on them.

Stage 2 (deferred): replace per-day LLM call with a pure-Python schedule
builder that synthesizes calendar events → schedule.md without the LLM.
Then this script becomes a Python loop instead of N agent calls. See
docs/followups/schedule-lookahead-stage2.md.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


LETTA = os.environ.get("LETTA_BASE_URL", "http://letta:8283")
DAILY_SCHEDULE_AGENT = "agent-a3f3940f-2dcb-4b73-a01c-132df63d5ae2"
ET = ZoneInfo("America/New_York")

# Offsets to pre-write. Today + tomorrow are owned by the existing crons.
OFFSETS = list(range(2, 14))  # D+2 .. D+13 (12 days)


PROMPT_TEMPLATE = """Generate a daily briefing for target_date='{target_date}' using the generate_daily_briefing tool.

CRITICAL: You MUST provide the target_date parameter as exactly '{target_date}' (YYYY-MM-DD format). Do NOT compute or override it; use that exact string.

This is a lookahead pre-write. Do not include time-of-day reasoning that depends on the current hour; render the schedule + available-time block for the target date as it stands now in the calendar. The tool writes to signals/{target_date}/schedule.md and to the briefing memory block.

After the tool succeeds, reply with one short line: "Lookahead {target_date}: ok" so the script can record the result.
"""


def post_message(target_date):
    body = {
        "messages": [
            {
                "role": "user",
                "content": PROMPT_TEMPLATE.format(target_date=target_date),
            }
        ]
    }
    req = urllib.request.Request(
        f"{LETTA}/v1/agents/{DAILY_SCHEDULE_AGENT}/messages/async",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
            return d.get("id")
    except Exception as e:
        sys.stderr.write(f"  ! {target_date}: {e}\n")
        return None


def main():
    now_et = datetime.now(timezone.utc).astimezone(ET).date()
    fired = []
    for offset in OFFSETS:
        target = (now_et + timedelta(days=offset)).strftime("%Y-%m-%d")
        run_id = post_message(target)
        if run_id:
            print(f"  fired {target}  run={run_id}")
            fired.append((target, run_id))
        else:
            print(f"  skip  {target}  (post failed)")
    print(f"\nLookahead pre-write fired for {len(fired)}/{len(OFFSETS)} days")
    return 0 if fired else 1


if __name__ == "__main__":
    sys.exit(main())
