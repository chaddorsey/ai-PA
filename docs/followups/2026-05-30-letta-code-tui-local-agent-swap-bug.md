---
date: 2026-05-30
status: open
severity: workaround-available
related:
  - docs/followups/2026-05-30-multi-agent-tui-workflow.md
  - docs/migrations/local-mode/docs-and-transcripts-agent.md
  - docs/migrations/local-mode/calendar-agent.md
---

# letta-code TUI: /agents swap fails for local→local agent switches

## Symptom

Inside a running `letta --backend local --agent <A>` TUI session, typing
`/agents` opens the agent picker. The local target agent (B) is visible
in the picker. On selection, the swap fails with:

```
Failed: Agent <B-id> not found
```

Confirmed reproducer: in `letta-docs` (running
`agent-local-3898b33a-…`), pick `agent-local-cd5ed5cd-…` (calendar) →
fails.

## Setup at time of bug

- letta-code 0.26.6
- Both agents pinned in `~/.letta/settings.json` with
  `"baseUrl": "local:/Users/dorseyhomeserver/.letta/lc-local-backend"`
- Both agent records exist at
  `~/.letta/lc-local-backend/agents/<base64>.json`
- `LETTA_LOCAL_BACKEND_DIR` env set correctly by wrapper

## Source code clue

`handleAgentSelect` in the bundle (around line 490416) DOES pass
`backendMode` and calls `configureBackendMode` before
`getBackend().retrieveAgent(targetAgentId)`. So the wiring exists, but
something fails between picker selection and the retrieve call.

Possible causes (untested):
1. `configureBackendMode` doesn't carry the local backend DIR — it
   reconfigures mode but loses the path, so retrieve hits a default
   that doesn't exist
2. Backend cache doesn't invalidate properly between local agents
   sharing the same backend dir
3. Some pinned-agent metadata mismatch (Docker-server entries in
   settings.json polluting the local-mode resolution)

## Workaround

Use the per-agent wrapper scripts as the switcher mechanism:

```bash
# Sequential
^C                # exit current letta TUI
letta-calendar    # launches fresh process for target agent

# Parallel via tmux
tmux new -s letta
letta-docs          # pane 0
# Ctrl-b "
letta-calendar      # pane 1
# Ctrl-b o to swap panes
```

The tmux pattern is the recommended multi-agent workflow regardless —
keeps caches warm per agent (no cold-start on swap), per-agent activity
is visually separated, and `Ctrl-b o` swap is faster than typing `/agents`.

## Investigation TODO

When time permits:
1. Add LETTA_DEBUG or NODE_INSPECT trace to see what
   `configureBackendMode` actually configures
2. Try removing the Docker-server-pinned entries from settings.json
   and re-test swap (rule out cross-mode pollution)
3. Try a fresh settings.json with ONLY the two local agents pinned
4. File upstream if reproducible against a clean letta-code install

Not urgent: tmux pattern works fine for daily use. Only matters if you
want a single-process multi-agent TUI session, which isn't required.
