---
date: 2026-04-25
target: XXX-ARCHIVE-scratch-agent (agent-880a63ad-2dbd-4f4d-a92b-3346b3346b1c)
status: SUBSTRATE PASS — content-flow validation deferred to step 2/3 TUI rehearsals
parent: docs/plans/2026-04-24-001-feat-letta-memfs-upgrade-plan.md
---

# Step 1 — memfs substrate mechanics smoke test on scratch-agent

## Result

**Substrate-level PASS.** The server-side memfs primitives (tag set,
auto-init of bare repo, sync-from-git, patch 04 scoped delete) all work
against the self-hosted patched server. **Content flow was NOT validated**
because scratch had zero attached blocks at the time of memfs enable —
the test exercised an empty-state operation, not the block-to-file
translation that real migrations require.

**Migration-flow validation moves to step 2/3 TUI rehearsals.** The
canonical block-to-file translation lives inside letta-code's TUI
`/memfs enable` slash command; reimplementing it in REST orchestration
isn't justified for a candidate set of ~4 agents.

Scratch was reverted to neutral state (tag dropped, bare repo removed)
post-test.

## What was tested

1. **CLI/server handshake**: `letta memory status --agent <scratch>`
   against `LETTA_BASE_URL=http://localhost:8283` returned a clean JSON
   error response (CLI reached server, server responded normally).

2. **Patch 04 (scoped delete propagation)**: direct invocation of
   `_delete_block_from_postgres` against a 2-agent shared block resulted
   in per-agent detach with the block retained for the other agent.
   Counterfactual under Fimeg patch 02 alone: global hard-delete.

3. **Server-side memfs enablement**:
   - PATCH `/v1/agents/<scratch> {"tags": ["git-memory-enabled"]}` → 200
   - POST `/v1/agents/<scratch>/memory/sync-from-git` (cold) → 200, `[]`
   - Server auto-initialized the bare repo at
     `/root/.letta/memfs/repository/<org_id>/<agent_id>/repo.git/` with
     a real `Initial commit` on `main`. No manual `git init` needed —
     improvement over the C3 canary work where we had to manually init.

## Findings worth carrying forward

### `--memfs` CLI flag is hardcoded Cloud-only

```
$ letta --memfs --agent <id> -p "..."
Memory git sync failed: --memfs is only available on Letta Cloud (api.letta.com).
```

The flag is gated client-side in letta-code by URL check, not server
capability. Useless against self-hosted. To unblock the user-facing
flag path, would need a letta-code patch (similar to our
`apply_letta_code_self_hosted_handle_fix.py`).

### `/memfs enable` slash command is TUI-only

Slash commands aren't parsed in headless `-p` mode (the string just
becomes a user message). To test the user-facing flow, a real TUI
session against a working agent model is required.

### `letta memory status` / `pull` / `diff` are local-state-driven

Source: `letta.js:164728` and adjacent. The `isGitRepo(agentId)` check
inspects a local working tree under `~/.letta/agents/<agent_id>/memory/`.
If that directory doesn't exist locally (i.e. user hasn't opened the
agent in TUI yet), all `letta memory` actions report `"Not a git repo"`
even when the **server** has memfs enabled and the bare repo is
populated.

**Implication for migration tooling**: the CLI's `letta memory` commands
are not authoritative for "is memfs enabled on this agent?" — they
reflect the local CLI's working tree only. The authoritative check is:
agent has the `git-memory-enabled` tag AND the server-side bare repo
exists and has refs.

## Server-side bare repo is now first-class

Pre-patch C3 had to manually init the bare repo and set HEAD ref.
On v2 patched server, POST `sync-from-git` against a tagged agent
auto-initializes the bare repo with an Initial commit and proper
`refs/heads/main` HEAD. Migrations only need to:

1. Set the tag
2. Push starting content from Gitea (or wherever the canonical state
   lives)
3. POST sync-from-git

## Side effect on scratch-agent state

After step 1, scratch is in:
- `tags: ["git-memory-enabled"]`
- 0 attached blocks (started with 2; defensive-detached `block-7bff4e45`
  legacy extracted_tasks, then patch-04 verification removed
  `block-18056d34` important_people)
- Server-side bare repo with one empty commit on main
- Local CLI working dir does not exist (would materialize on first
  TUI open)

Reversibility: remove the tag via PATCH; remove the bare repo dir; the
agent goes back to a non-memfs Pattern-3 state with no blocks. Both
detached blocks (-7bff4e45 and -18056d34) still exist and could be
re-attached if desired (though they're stale in our ecosystem).

## What's NOT yet tested (intentionally deferred)

- Full TUI `letta --agent <scratch>` opening, slash-command
  `/memfs enable`, and `/doctor` reorganization. These belong in step 2
  (letta-code-native rehearsal) and step 3 (calendar-agent v1 rehearsal).
- Sync of actual block content from Gitea → bare repo → Postgres. The
  cold sync test was deliberately empty; content sync will be exercised
  on the calendar-agent rehearsal where there are real blocks to port.

## Step 1 → Step 2 readiness

All step-1 prerequisites for steps 2 and 3 are now satisfied:
- Patched server (v2) running and healthy
- Patch 04 verified to prevent catastrophic shared-block deletion
- Server auto-init of bare repo confirmed working
- Gitea infrastructure in place (orgs `agents` and `letta-memfs` exist;
  `pa-admin` token available)
- Memory note about CLI memory commands being local-state-only recorded
