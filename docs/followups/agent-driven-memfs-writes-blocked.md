---
date: 2026-04-26
status: RESOLVED 2026-04-26
resolution: agent.message_buffer_autoclear=False (was True default for newer agents)
severity: was P1, no longer blocking
discovered-during: calendar-agent_copy canary migration
related: docs/runbooks/lessons-from-calendar-canary.md (lesson #6)
---

## RESOLVED 2026-04-26

**Root cause:** `message_buffer_autoclear: true` (default for newer
agents) clears pending-approval state on run completion, even when run
finalized with `stop_reason=requires_approval`.

**Fix:** PATCH the agent to set `message_buffer_autoclear: false`
**before migration**. Now baked into the per-agent runbook as Phase 0.
The two agents the runbook was originally tested on (`calendar-agent`
memgpt_v2, `Letta Code` letta_v1) both happened to have the field set
to `false` — that's why the runbook didn't surface the issue.

Calendar-agent_copy verified working end-to-end after the fix:
- `letta-patched -p '<bash prompt>'` → `num_turns=2`, tool runs cleanly
- Agent-driven Edit/Write of memfs files → commit → push → relay → patch
  05 → Postgres update in ~10s, both directions

The original problem statement and investigation plan below are kept
for historical reference and in case a similar-shape error appears in
the future.

---

# Agent-Driven Memfs Writes — Blocked by Approval-State-Machine Bug

## Symptom

Asking a memfs-enabled agent (via either TUI or letta-code headless) to
invoke any tool that modifies its own memfs files reliably produces:

```
"detail": "Cannot process approval response: No tool call is currently
 awaiting approval. Please send a regular message to interact with the
 agent."
```

The error appears at the server-side LLM-streaming layer. Simple prompts
that don't invoke tools (e.g., "Reply OK") return cleanly with the
expected response. Tool-calling prompts uniformly fail with this error,
regardless of:
- `--yolo` flag (tool auto-approval)
- `--new` flag (fresh conversation)
- TUI vs headless invocation
- Specific tool requested (Bash, Edit, Write all fail the same way)

## Reproducer

```bash
export DISABLE_AUTOUPDATER=1
export LETTA_BASE_URL=http://localhost:8283
export LETTA_API_KEY=local-self-hosted

AGENT=agent-892a2d58-b9f6-4baf-84f3-c431fe46487d  # any memfs-enabled letta_v1 agent

# This works (no tool call):
/Volumes/main-drive/ai-PA/bin/letta-patched -p "Reply with just OK" \
  --agent "$AGENT" --output-format json --new --yolo

# This fails with the approval-response error:
/Volumes/main-drive/ai-PA/bin/letta-patched \
  -p 'Run this Bash: cd "$MEMORY_DIR" && ls system/' \
  --agent "$AGENT" --output-format json --new --yolo
```

## What Still Works

- **Substrate round-trip (host-driven):** edit → commit → push → relay →
  patch 05 → Postgres. Verified live during calendar canary; ~600ms
  one-direction.
- **Mirror writer:** continues regenerating the legacy `extracted_tasks`
  block from `pa_web.tasks` on schedule.
- **Letta-API-driven tool calls** on registered domain tools (calendly,
  run_gws, lookup_staff, etc.) — these don't go through letta-code's
  approval flow.
- **Agent's awareness** of memfs in its system prompt (Layer 2) —
  unaffected.
- **Calendar-agent's daily operational use** — calendar queries,
  scheduling, etc., all work normally.

## What's Blocked

- **Agent-driven Edit/Write/Bash on its own memfs files.** Any prompt
  that asks the agent to modify `system/*.md`, append to
  `reflections/inbox.md`, or persist computed output (like a plate
  digest) to a memfs file fails with the approval-response error.

## Cycle-1 Impact

| Plan element | Impact |
|---|---|
| Pattern 5 (Postgres-canonical task substrate) | None — all CRUD goes through pa-web-ui or external services, not the agent |
| Mirror writer | None — server-driven, doesn't involve agent tool calls |
| Reflection inbox capture (R32, Unit 18) | **BLOCKED** — agent can't append to `reflections/inbox.md` |
| MC plate-digest auto-refresh (R38-R42) | **PARTIALLY BLOCKED** — `refresh_plate` returns the digest text via API, but the agent can't Write it to `reference/current-plate.md` |
| Per-agent memfs migrations themselves (Phase E) | None — migrations are host-driven; substrate state changes happen on the server during `/memfs enable`, not via agent tool calls |
| Agent self-housekeeping (cycle-2 reflection subagents) | **BLOCKED** — they would need to Edit memfs files |

**Calendar-agent_copy migration itself is COMPLETE** — substrate is
correct, tools restored, propagation works. This issue is orthogonal
to migration mechanics.

## Hypotheses (untested)

1. **letta-code version regression.** A specific letta-code release
   started sending `is_approval_response: true` headers on every
   tool-call message regardless of approval state. Possible fix:
   pin to an earlier letta-code version OR upgrade past the affected
   range.
2. **Path C patch interaction.** Our Path C handle-resolution patch
   modifies tool-call paths. Could be sending malformed headers in a
   way the server now rejects.
3. **Server-side change.** A recent Letta server release tightened
   approval-flow validation in a way the existing letta-code clients
   don't satisfy.

## Investigation Plan (post-MC-migration; do NOT block cycle 1)

1. **Reproduce on a fresh letta_v1 agent without memfs** (rule out
   memfs-specific issue).
2. **Reproduce on a fresh memfs-enabled agent without Path C patches**
   (rule out patch interaction).
3. **Check letta-code GitHub for known issues + recent releases**
   touching approval-flow.
4. **Capture the actual HTTP request letta-code sends to Letta** (curl
   capture or browser devtools if web UI exists) to see whether
   `is_approval_response` is being sent with `true` for every tool
   call.

## Workarounds for Cycle-1-Blocked Functionality

### Reflection capture (R32) — Option α (sidecar)

Build a service that watches each migrated agent's archival/conversation
log for messages containing `[self]`, `[canonical]`, or `[system]` tags
and appends them to `reflections/inbox.md` from outside the agent.
Reflection content lives in the agent's natural conversation, so an
external observer can extract it without needing the agent to call
Write.

### MC plate-digest persistence — Option β (substrate-side write)

The `refresh_plate` tool currently RETURNS the digest text and expects
the caller (MC) to Write it. Restructure: have `refresh_plate` write
DIRECTLY to MC's bare repo via the same git-push path that
host-side propagation uses (sandbox can run git commands). The plate
file then propagates back to MC's working tree + Postgres via patch 05.

### Reflection capture — Option γ (defer)

Cycle 1 captures reflection content; cycle 2 designs the
helper-reflection agent + steward. Defer the capture mechanism entirely
until cycle 2; rely on the user reviewing conversation logs for
substantive reflection content during MC's soak. Loses some signal but
unblocks cycle 1.

## Recommendation

- **Do not block MC migration on this.** Migrate MC; calendar already
  proved the substrate works.
- **Before registering the MC plate-digest cron**, decide between
  Option β (substrate-side write) or accept the manual-refresh path
  during soak.
- **Before relying on reflection capture**, decide between Option α
  (sidecar observer), Option γ (defer to cycle 2), or debug the
  underlying bug.
