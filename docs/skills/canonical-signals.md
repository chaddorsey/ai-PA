---
description: Layer-5 canonical signal emit + read. Replaces emit_canonical_signal and read_recent_signals Letta tools for local-mode agents.
applies-to: any local-mode agent that needs to emit signals or query recent signals
replaces: emit_canonical_signal (Letta tool), read_recent_signals (Letta tool)
cli: scripts/signal
---

# Canonical Signals Skill

## When to use

- **Emit:** when you finish a piece of work whose result other agents
  (or future-you) should be able to discover. Daily briefings, plate
  snapshots, vibe checks, task extractions, monitoring digests.
- **Read:** when you start a turn that benefits from knowing what
  recent signals have been emitted. Plate refreshes, briefing
  composition, cross-agent awareness.

This skill replaces the legacy `emit_canonical_signal` and
`read_recent_signals` Letta tools 1:1. Same path convention
(`signals/YYYY-MM-DD/<source>-<slug>.md`), same frontmatter schema,
same Gitea auth (`GITEA_MEMFS_TOKEN`).

## Prerequisites

`GITEA_MEMFS_TOKEN` must be in your environment. For local-mode
agents, this should be inherited from the launchd-managed runner's
EnvironmentVariables or from the host's shell at TUI start. Test:

```bash
echo "$GITEA_MEMFS_TOKEN" | head -c 16  # should print first 16 chars
```

## Emit — write a signal

```bash
signal emit \
  --slug <short-slug> \
  --source <your-agent-id-or-name> \
  --description "<one-line summary>" \
  --attention <routine|elevated|urgent> \
  --entities "<csv of mentioned entities>" \
  --body "<markdown body>"
```

Examples:

```bash
# Inline body
signal emit --slug morning --source mc \
  --description "Morning briefing for $(date +%F)" \
  --attention routine \
  --body "Today's plate is light. Two meetings, three focus blocks."

# Body from file
signal emit --slug plate-snapshot --source mc \
  --description "Plate snapshot after task extraction run" \
  --body-file /tmp/plate.md

# Body from stdin
echo "Three new tasks extracted from email this morning." | \
  signal emit --slug task-extracted --source tasks-agent --body-file -

# Elevated attention with entities
signal emit --slug deadline-warning --source pulse-monitor \
  --description "Proposal deadline in 48h" \
  --attention elevated \
  --entities "CAMEL Proposal, Kate Grigsby, Cynthia" \
  --body "The CAMEL proposal review is due Friday. Outstanding items: ..."
```

Return value (stdout):

```json
{"status":"ok","path":"signals/2026-05-25/mc-morning.md","html_url":"http://gitea:3000/agents/agents-canonical/src/branch/main/signals/2026-05-25/mc-morning.md","was_update":false}
```

## Read — list recent signals

```bash
signal read \
  [--min-attention <routine|elevated|urgent>] \
  [--days-back <n>] \
  [--source <substr>] \
  [--max <n>] \
  [--excerpt-chars <n>] \
  [--json]
```

Examples:

```bash
# Last 3 days, all sources (default)
signal read

# Only elevated+ in last week
signal read --min-attention elevated --days-back 7

# Only pulse-monitor signals, cap at 5
signal read --source pulse-monitor --max 5

# Raw JSON for programmatic consumption
signal read --source pulse-monitor --max 5 --json | jq '.signals[].description'
```

Human-readable output format:

```
─── 2026-05-25  ROUTINE  [mc]
  Morning briefing for 2026-05-25
  signals/2026-05-25/mc-morning.md
  Today's plate is light. Two meetings, three focus blocks.

(3 signals across 3 day(s))
```

## Path convention

`signals/YYYY-MM-DD/<source>-<slug>.md`

- `YYYY-MM-DD` is the signal's date (defaults to today in
  America/New_York)
- `<source>` is the emitting agent's short identifier (mc,
  pulse-monitor, tasks-agent, calendar-agent, etc.)
- `<slug>` is the signal type (morning, vibe-check, plate-snapshot,
  task-extracted, etc.)

Filename uniqueness: one signal file per `(date, source, slug)` tuple.
Emitting again with the same combination UPDATES the existing file
(idempotent).

## Frontmatter schema

The CLI builds frontmatter automatically. The fields:

```yaml
---
description: <one-line summary, used by read_recent_signals to decide relevance>
source: <emitting-agent-short-id>
attention_level: routine | elevated | urgent
mentioned_entities: ["Entity One", "Entity Two"]
composed_at: 2026-05-25T17:00:00.000Z
date: 2026-05-25
---
```

To add custom frontmatter fields (e.g., for source-specific schema):

```bash
signal emit --slug ... --source ... \
  --extra-frontmatter "$(cat <<EOF
slack_channel: C0AB18G54ET
related_tasks: [task-abc, task-xyz]
EOF
)" \
  --body "..."
```

## Migration notes

When migrating an agent from Docker mode to local mode:

1. **Detach** the `emit_canonical_signal` and `read_recent_signals`
   tools from the local-mode agent (they don't exist there anyway).
2. **Confirm** `scripts/signal` is on the agent's `$PATH` (the host's
   PATH should suffice; verify with `which signal` in the agent's
   Bash environment).
3. **Update protocols** — anywhere the agent's system protocols
   reference `emit_canonical_signal(...)`, replace with a `signal
   emit ...` recipe. (The argument names map 1:1.)

## Failure modes

- **`GITEA_MEMFS_TOKEN not set`** → export it in the agent's
  environment (runner or shell).
- **`ERROR (404): ...`** when reading → no signals exist yet for
  the requested date range. Not a bug.
- **`ERROR (409): ...`** when emitting → SHA collision (rare; another
  process wrote the same path concurrently). Retry once; the second
  attempt will find the new SHA.
- **Gitea unreachable** → check `docker ps | grep gitea` and verify
  `GITEA_BASE_URL` env var (default `http://localhost:3030` from host,
  `http://gitea:3000` from inside Docker).
