---
description: Scheduling orchestrator CLI. Wraps the scheduling-orchestrator-api service (POST /schedule). Replaces the orchestrate_scheduling Letta tool with a Bash-callable surface that assembles context_json from individual flags so agents don't have to JSON-encode by hand.
applies-to: any local-mode agent that proposes meeting slots. Primary user: Calendar Agent. Also useful for MC (when handling user-direct scheduling utterances), and Slackbot's fast-path direct scheduler.
replaces:
  - orchestrate_scheduling (Letta tool)
cli: scripts/orchestrate-scheduling
---

# Orchestrate-Scheduling CLI Skill

## When to use

- **Find times to meet** with one or more participants over a date
  range: `orchestrate-scheduling schedule "<utterance>" --participants
  <emails> --from <date> --to <date> --minutes <N>`.
- **Find times to reschedule** a specific event: `orchestrate-scheduling
  reschedule <event_id> "<utterance>" [opts]`.
- **Check orchestrator health** before assuming a stuck Calendar call
  is the orchestrator's fault: `orchestrate-scheduling health`.

This skill replaces the `orchestrate_scheduling` Letta tool 1:1. Both
routes hit the same `POST /schedule` endpoint on
`scheduling-orchestrator-api`; the CLI is the local-mode-compatible
shape.

## When NOT to use

- **The user has not given enough constraints** (no date range, no
  participants, no duration). Ask first; calling the orchestrator
  with an empty `context_json` returns 192 slots considered and 20
  generic proposals that aren't useful. Get specifics from the user
  first.
- **Reading a single participant's calendar** to see what they're
  doing: use `gws calendar events list` for that. The orchestrator
  is for *proposing slots given constraints*, not for raw calendar
  inspection.
- **Confirming / creating a chosen event**: this CLI returns
  proposals; it does NOT book them. Booking is `gws calendar events
  insert` after the user picks one.

## Prerequisites

- `scheduling-orchestrator-api` container running:

  ```bash
  docker ps --filter name=scheduling-orchestrator-api --format '{{.Status}}'
  # should show "Up ... (healthy)"
  ```

- `jq` installed.
- Service URL auto-detected: host (http://localhost:8096) or Docker
  network (http://scheduling-orchestrator-api:8095). Set
  `ORCHESTRATOR_BASE_URL` to skip detection.

## Pre-call gates (CRITICAL)

These two rules are baked into the orchestrator's failure mode — get
them wrong and the orchestrator returns 20 nonsense proposals (the
"all-9:15am" bug) without obvious errors:

### 1. The user MUST be in `--participants`

The user (`cdorsey@concord.org` by default) is the requester. If you
drop the user from the participant list, the orchestrator only checks
the *other* participants' calendars, returning slots that conflict
with the user's actual availability. Always include the user unless
the user explicitly asks "find times only on Danielle's calendar."

### 2. EVERY participant_id MUST be a real, resolvable email

Placeholders like `name@example.com` produce silent degradation: the
orchestrator finds 0 events on the fake calendar, scores all slots
identically, and returns 20 proposals all clustered at the earliest
slot-of-day on each weekday. If a participant name can't be resolved
via `[[system/canonical_reference_protocol]]` → canonical → gws
search, **ask the user** before calling the orchestrator.

## Subcommands

### schedule

```bash
# Standard call (build context_json from individual flags)
orchestrate-scheduling schedule "find 45 min with Danielle next week" \
  --participants cdorsey@concord.org,dkehoe@concord.org \
  --from 2026-06-16 --to 2026-06-20 \
  --minutes 45 \
  --pretty
```

Required: utterance (positional), `--from`, `--to`, `--participants`.
Optional: `--user-id` (defaults to cdorsey@concord.org), `--minutes`
(default 30), `--tz` (default America/New_York), `--policy` (merge into
context.policy), `--limit` (cap `--pretty` output).

### reschedule

```bash
orchestrate-scheduling reschedule evt_abc123 "move to Tuesday afternoon" \
  --from 2026-06-02 --to 2026-06-06 \
  --participants cdorsey@concord.org,dkehoe@concord.org \
  --pretty
```

Same flags as schedule, plus `event_id` becomes the first positional
arg. Use when the user names a specific meeting to move.

### Policy overrides

The `--policy` flag merges a JSON object into `context.policy`. The
orchestrator understands `hard` (must-satisfy) and `soft` (preference)
keys:

```bash
# Hard constraint: minimum 15-min buffer between meetings
orchestrate-scheduling schedule "..." \
  --policy '{"hard":{"min_gap_min":15}}'

# Soft preference: avoid mornings
orchestrate-scheduling schedule "..." \
  --policy '{"soft":{"avoid_time_of_day":["morning"]}}'
```

For full policy control, use `--context-json` (escape hatch):

```bash
orchestrate-scheduling schedule "..." \
  --context-json '{"timeframe":{"from":"...","to":"...","tz":"..."},
                   "slot_size_minutes":45,
                   "policy":{...}}'
```

When `--context-json` is set, all `--from/--to/--tz/--minutes/--policy`
flags are ignored.

### health

```bash
orchestrate-scheduling health
# → {"status":"ok","service":"scheduling-orchestrator-api"}
```

## Output shapes

**JSON (default)**: condensed response with `status`, `explanation`,
`proposals_count`, and the `proposals` array (sorted by `rank`).
Each proposal includes:

- `rank` — 1 = best
- `start_utc`, `end_utc` — ISO 8601 UTC
- `participants` — emails included
- `category` — e.g. `free_slot`, `move_one_event`, `override_blocking`
- `preference_score` — 0.0 if no preferences expressed; higher = better
- `objective_scores.focus_block_bonus` — bigger = bigger contiguous
  free block around the slot
- `objective_scores.moved_minutes` — total minutes of other meetings
  moved to make this slot (0 = clean free slot)
- `moved_events` — list of events that would need to move
- `original_event_id`, `original_event_details` — present on
  reschedule proposals

**`--pretty`**: human-readable summary with rank, time, participants,
preference + focus scores. Limited to top N (`--limit`, default 10).

**`--debug`**: includes the full `debug` section (slots_considered,
normalization_time_ms, solve_time_ms, total_time_ms, input_summary)
useful when diagnosing slow or wrong-looking output.

## Pattern: time-of-day variety sanity check

When proposing slots to the user, the agent should sanity-check the
result before presenting:

```bash
# Get raw response
resp=$(orchestrate-scheduling schedule "..." \
   --participants cdorsey@concord.org,dkehoe@concord.org \
   --from 2026-06-16 --to 2026-06-20 --minutes 45)

# Are all proposals at the same time-of-day? That's a signal one of
# the participants has no visible calendar (likely a wrong email).
echo "$resp" | jq -r '.proposals[] | .start_utc' | cut -dT -f2 | cut -d: -f1 | sort -u
# If this returns 1 unique hour, regenerate the participant list.
```

This is exactly the bug that bit the SPARK Glasses scheduling work in
late May 2026 (all proposals at 9:15am — Danielle's email was a
placeholder). The participant resolution discipline (canonical →
gws → ask) prevents it.

## Pattern: presenting proposals

```bash
# Get top 5 with focus scores
orchestrate-scheduling schedule "..." --participants ... \
  --from ... --to ... --minutes 30 \
  | jq '.proposals[:5] | map({
      time: (.start_utc + " → " + .end_utc),
      focus_bonus: .objective_scores.focus_block_bonus,
      preference_score
    })'
```

Use `focus_block_bonus` as the secondary signal when `preference_score`
is 0 across the board (no soft preferences expressed).

## Failure modes + remediation

- **`cannot reach scheduling-orchestrator at ...`**: service down.
  Restart: `docker-compose restart scheduling-orchestrator-api`.
- **20 proposals all at the same time-of-day**: one or more
  participants has no visible calendar. Re-check participant emails
  via canonical. Common cause: placeholder like `name@example.com`,
  or first-name slug guess that wasn't resolved.
- **`HTTP 422 ... context_json must be string`**: --context-json was
  passed as a literal object, not a JSON-encoded string. The CLI's
  --context-json flag accepts the JSON object form and stringifies
  it for the API; pass it via the flag rather than constructing the
  payload manually.
- **`proposals_count: 0` with no clear explanation**: probably a hard
  constraint conflict (e.g., `min_gap_min` too large for the
  timeframe). Re-call with `--debug` and inspect `debug.input_summary`.
- **Slow (>30s)**: increase `ORCHESTRATOR_TIMEOUT`. Normal range
  is 0.4–10s; >30s suggests the orchestrator is processing very long
  timeframes or many participants.

## Migration history

- **Pre-2026-05-30**: agents called the `orchestrate_scheduling` Letta
  tool. The tool (in `letta/scheduling_orchestrator/orchestrate_
  scheduling.py`) wrapped the same HTTP API but ran inside the Letta
  server's tool runtime.
- **2026-05-28**: surfaced the participant_resolution + always-
  include-user bugs during SPARK Glasses scheduling work. Calendar-
  agent's prompt was rewritten with explicit rules; canonical-store
  lookup procedure was added to its memfs.
- **2026-05-30**: this CLI shipped. The participant discipline is
  enforced both by the calendar-agent's prompt AND by the skill
  protocol (above). Once Calendar migrates to local mode, the
  Letta tool can be detached.

## Validation history

- **2026-05-30** — Shipped + smoke-tested all subcommands:
  - `health` returns `{"status":"ok",...}`
  - `schedule` for Danielle June 16-20 with both participants
    returned 29 options across 7 free / 8 move-one / 14 override
    categories; top 5 spanned 3pm/4pm UTC slots (not all-mornings)
  - `--pretty` rendered ranked proposals with scores
  - `--debug` exposed solver timing (375ms normalize, 10ms solve)
  - `--policy '{"hard":{"min_gap_min":15}}'` produced 13 valid
    proposals respecting the constraint
  - `--context-json` escape hatch accepted a raw payload
  - Missing utterance → error + exit 2
  - Unknown subcommand → error + exit 2
