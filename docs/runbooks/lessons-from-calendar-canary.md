---
date: 2026-04-26
applies-to: cycle-1 Phase E migrations starting with MC
source: calendar-agent_copy migration (first canary)
---

# Lessons from the Calendar-Agent_Copy Canary

The calendar-agent_copy migration succeeded but surfaced four issues
worth incorporating into MC's plan and into the per-agent runbook
permanently. Each is documented with the symptom, the root cause, and
the action to take during MC migration.

## 1. Tool over-detach during `/memfs enable`

**Symptom (calendar):** Tool count went from 21 (pre-migration) to 2
(post-`/memfs enable` Phase E). Letta-code's intended behavior is to
detach v1 memory tools (`memory_replace`, `memory_apply_patch`, etc.)
and attach Skill/Edit/Write/Read. In practice it stripped ALL
explicitly-attached tools, leaving only the two built-in default tools
(`fetch_webpage`, `web_search`).

**Root cause:** Letta-code's `/memfs enable` tool-mutation logic is
overly aggressive — it doesn't preserve domain-specific tools that
weren't on a curated keep-list. Has the shape of a wipe-and-replace
rather than a targeted-detach.

**Action for MC:**

1. **Snapshot MC's full tool list BEFORE `/memfs enable` Phase C.** Run:
   ```bash
   AGENT=agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef
   curl -sL "http://localhost:8283/v1/agents/$AGENT" \
     | python3 -c "import json,sys; a=json.load(sys.stdin); print(json.dumps([{'name':t['name'],'id':t['id']} for t in (a.get('tools') or [])], indent=2))" \
     > /tmp/mc-tools-pre-migration.json
   ```
2. After Phase E `/memfs enable` succeeds, compare and restore. Use the
   safe-list helper to reattach any domain tools that should stay
   (per MC's pre-migration audit at
   `docs/runbooks/mc-pre-migration-audit.md`).
3. Per the audit, the v1 memory tools that SHOULD remain detached
   (replaced by built-in Edit/Write/Read post-memfs) are:
   `memory_replace`, `memory_apply_patch`, `memory_insert`,
   `archival_memory_insert`, `archival_memory_search`. Also detach the
   stale `rover_status_log_202603a` block per the audit. Everything
   else from the pre-snapshot reattaches.

## 2. "Memory git sync failed" cosmetic banner on TUI resume

**Symptom (calendar):** After Phase D bridge ran and we re-opened the
TUI for Phase E, an alarming banner appeared:
```
⚠ Memory git sync failed: Command failed: git clone ...
fatal: destination path '.' already exists and is not an empty directory.
```
Plus a follow-up `[memfs background sync]` lock-file error.

**Root cause:** Letta-code's background sync runs a redundant clone on
TUI resume. The first `/memfs enable` failure (Phase C, expected to
fail) had already created some local state. On resume, letta-code's
auto-sync sees the directory and tries to clone-into-it again, which
git refuses. The actual `/memfs enable` flow completed correctly in
the background; the banner is stale-state noise, not an actual failure.

**Action for MC:** Ignore the banner if it appears. Verify substrate
state with `verify-agent-memfs.sh` (now patched with locale-stable
sort) instead of relying on the TUI's perception. If the verify script
returns 8/8 PASS, the substrate IS healthy regardless of what the TUI
banner says.

## 3. Verify-script's sort-locale bug (now patched)

**Symptom (calendar):** Initial run of `verify-agent-memfs.sh` reported
"Postgres blocks DIVERGE from bare repo (bare=12, pg=12)" despite
counts being equal. Investigating showed the labels matched as a SET;
they only differed in sort order due to macOS `sort` using
locale-aware sorting (mixed-case) vs Python's `sorted()` doing
case-sensitive ASCII sort.

**Root cause:** `verify-agent-memfs.sh:97` used bare `sort` for the
bare-repo file list while the Postgres-side comparison used Python
`sorted()`. Different orderings of the same set.

**Fix:** Patched to `LC_ALL=C sort` (commit during this session). Future
verifications use a stable C-locale sort consistent with Python's default.

**Action for MC:** No action needed — fix is in. If you ever clone the
helper to a new env, ensure the patch is preserved.

## 4. Webhook-registration check is per-repo blind to org-level webhooks

**Symptom (calendar):** Post-migration substrate health audit reported
"webhooks configured: 0" for the new agent's per-repo hooks endpoint.
This caused initial concern that round-trip propagation was broken.

**Root cause:** The webhook is registered at the **org level**
(`agents` org), not per-repo. Org webhooks fire for any repo under
the org. The Gitea API's `/repos/<org>/<repo>/hooks` endpoint only
reports per-repo hooks; org hooks are at `/orgs/<org>/hooks`.

**Action for MC:** When checking webhook health post-migration, query
both endpoints. The org-level webhook (id=1, push events,
`http://memfs-sync-relay:8901/webhook`) covers all `agents/*` repos
including newly-created ones. **Live round-trip propagation test
(edit → push → wait 5-10s → query Postgres) is the most reliable
verification — substrate either propagates or doesn't, regardless of
how the webhook is configured.**

## 5. Pre-existing local-clone state from failed first `/memfs enable`

**Symptom (calendar):** When letta-code resumed the TUI mid-flight, it
had already partially set up a local clone in
`~/.letta/agents/<id>/memory/` from a prior implicit attempt. This
satisfied Phase E's clone requirement automatically (the local working
tree existed and matched the bare repo HEAD), but caused the misleading
"already exists" error banner.

**Root cause:** Letta-code's resume logic eagerly tries to materialize
the local clone even before the user explicitly runs `/memfs enable`,
and doesn't gracefully detect a partial pre-existing clone.

**Action for MC:** Two options:

**A.** **Don't do explicit `/memfs enable` re-run after Phase D bridge
if the local clone already materialized.** Check first:
```bash
ls -la ~/.letta/agents/$AGENT_ID/memory/.git/HEAD 2>&1
```
If the local clone already exists with a `.git` directory, run
`verify-agent-memfs.sh` directly. If it returns 8/8 PASS, you're done
with Phase E — skip the second TUI invocation entirely.

**B.** **If you DO re-open TUI for Phase E,** ignore the resume-banner
errors and just run `/memfs enable`. The command is idempotent — it
will detect the already-clean state and complete silently (or show
the cosmetic error again, depending on letta-code's mood).

## 6. `message_buffer_autoclear: True` clears pending-approval state ★ ROOT CAUSE FOUND

**Symptom:** Every tool-calling prompt through letta-code (TUI or
headless) on a memfs-enabled agent failed with:
```
"Cannot process approval response: No tool call is currently awaiting
 approval."
```

**Root cause:** When the agent has `message_buffer_autoclear: true`,
the server clears the agent's message buffer (including pending-approval
state) on run completion — even when the run finalized with
`stop_reason=requires_approval`. letta-code's subsequent
approval-response submission (or a manual one) finds no pending tool
call to match.

**Verification:** The two previously-migrated agents (`calendar-agent`
memgpt_v2 and `Letta Code` letta_v1) both have
`message_buffer_autoclear: false` and worked cleanly during their
migrations. `calendar-agent_copy` was created at a later date with
`message_buffer_autoclear: true` (apparent default for newer agents)
and that's where the bug surfaced.

**One-line fix (apply to every agent before migration):**
```bash
curl -sL -X PATCH "http://localhost:8283/v1/agents/$AGENT_ID" \
  -H "Content-Type: application/json" \
  -d '{"message_buffer_autoclear": false}'
```

**Verified end-to-end after fix:**
- Headless `letta-patched -p '...'` invocations with Bash tool calls
  return `num_turns: 2`, tool executes, output returned.
- Agent-driven Edit/Write of memfs files commits to the agent's working
  tree, pushes to Gitea, propagates through memfs-sync-relay and patch
  05 to Postgres in <10s.

**Action for MC migration and all subsequent migrations:** Add to
Phase A pre-flight checklist:
```bash
curl -sL "http://localhost:8283/v1/agents/$AGENT_ID" \
  | python3 -c "import json,sys; print('autoclear:', json.load(sys.stdin).get('message_buffer_autoclear'))"
# If True, PATCH to false BEFORE Phase B.
```

This is now a hard prerequisite, not a "watch out for" — without it,
every memfs-mediated tool call after migration fails.

## 6b. Agent-driven memfs writes hit approval-state-machine bug (RESOLVED via #6)

**Symptom (calendar):** Asking the agent (via TUI or letta-code headless)
to run a Bash command that modifies its memfs files reliably triggers:
```
"Cannot process approval response: No tool call is currently awaiting
 approval. Please send a regular message to interact with the agent."
```
Simple prompts that don't invoke tools work fine. The error fires on
every tool-call attempt regardless of `--yolo` flag, `--new` conversation
flag, or TUI vs headless.

**Root cause (suspected):** letta-code's client sends an approval-response
message wrapper when the server doesn't have a tool-call awaiting
approval. Could be a Path-C-patched-version interaction, a letta-code
release bug, or a server-side state issue specific to letta_v1 +
memfs-enabled agents. Not yet isolated.

**What still works regardless:**
- Letta-API-driven tool calls on registered domain tools (calendly,
  run_gws, etc.) continue to function normally.
- Substrate round-trip propagation (host-side edit → push → bare repo →
  Postgres) is unaffected.
- The agent's awareness of memfs (Layer 2) — describing layout etc — is
  unaffected.

**What's blocked:**
- Agent-driven writes to its own memfs (e.g., `Edit system/persona.md`,
  appending to `reflections/inbox.md`, persisting computed digests to
  `reference/current-plate.md`).

**Cycle-1 implications:**
- **Reflection inbox capture (R32, Unit 18 file convention)** is
  blocked. The agent cannot append entries via Edit/Write.
- **MC plate-digest auto-write (R38-R42)** is partially blocked. The
  `refresh_plate` Letta-API tool computes the digest correctly; persisting
  it to `reference/current-plate.md` requires agent-driven Write — broken.

**Action for MC migration:** Proceed with the migration itself — Phase
A-F don't require agent-driven memfs writes (they're migration mechanics,
all driven from the host). After MC's substrate is wired, **debug this
bug BEFORE registering the plate-digest cron and BEFORE relying on
reflection capture.** Possible remediations:
1. Investigate letta-code release notes for a known-fixed version.
2. Check whether a different Path C variant resolves it.
3. If unfixable: redesign agent-driven memfs writes to go through an
   external sidecar (similar to mirror writer) that appends to
   inbox/digest files from outside the agent's tool context.

This issue is captured at the substrate-canary level, not as a Calendar-
specific bug. Same behavior is expected on MC and any letta_v1+memfs
agent until the underlying cause is identified.

## Summary checklist for MC migration

Add to `docs/runbooks/mc-pre-migration-audit.md` before kicking off MC:

- [ ] Snapshot MC tools to `/tmp/mc-tools-pre-migration.json` (pattern in #1)
- [ ] Snapshot MC blocks (already in audit)
- [ ] Phase B: detach **only** the stale block (`rover_status_log_202603a`)
      per audit; do NOT detach any block needed for Telegram operation
- [ ] Phase C: expect "Repository not found" error; verify server-side
      state landed (tag, bare repo, backfill commit)
- [ ] Phase D: run bridge script
- [ ] Phase E: check if `~/.letta/agents/<MC_ID>/memory/.git/HEAD` exists
      already (the clone may have auto-materialized). If yes, skip the
      TUI re-run. If no, re-open TUI + `/memfs enable`.
- [ ] Phase F verify: 8/8 PASS expected from `verify-agent-memfs.sh`
- [ ] **Post-Phase-E**: snapshot tool list, compare to pre-migration,
      reattach all that aren't intentionally detached. Use:
      ```python
      python3 scripts/memfs-helpers/agent_list_ops.py attach-tool $MC $TOOL_ID
      ```
- [ ] Live round-trip smoke test: edit a system file, commit, push,
      wait 10s, verify Postgres updated. Revert.
- [ ] Telegram smoke test: send message, verify same-shape response
- [ ] Register MC plate-digest cron in scheduler-service (per the plan,
      `*/20 7-22 * * *` America/New_York, `agent_message`,
      message: "Run skill refresh-plate")
