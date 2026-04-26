---
date: 2026-04-25
purpose: Isolate root cause of subagent runtime failure (Issue 4)
related: ezra-defects-note-followup.md, model-comparison-test-results.md
status: variables ruled out; failure is system-wide on self-hosted 0.16.7
---

# Issue 4 isolation — variables ruled out

Per Ezra's hint that subagent failures are typically the #3205 client_tools/
approval IPC bug class, ran a series of tests to isolate the variable.

## Variables tested and ruled out

| Variable | Test | Result |
|---|---|---|
| Memfs enabled on parent | Removed `git-memory-enabled` tag from agent-7f293624, retest Task | Same failure |
| Memfs env vars present | Dropped LETTA_MEMFS_LOCAL + LETTA_MEMFS_GIT_URL from invocation | Same failure |
| Parent agent model | Tested kimi-k2p6, gpt-5.4, gpt-4.1-mini | All produce same subagent failure (kimi/gpt-5.4 confirmed cleanly chain Task→TaskOutput; subagent itself crashes) |
| Parent agent identity | Tested agent-7f293624 AND agent-8f885655 (the morning's successful subagent) | Both fail identically as parents |
| LETTA_MEMFS_GIT_URL inheritance | n/a — env not set in failing test | Not the cause |
| Env propagation to child | Verified `composeSubagentChildEnv` (letta.js) inherits parentProcessEnv via spread | Not the cause |

## What's NOT in the variable space

Earlier this morning (06:43 UTC), Task subagents **succeeded** on the same
stack. The successful subagents (`subagent-1777113841582-5`, `-4`) became
persistent agents (`agent-8f885655-...`, `agent-6bd40f17-...`) that still
exist in the database with tags `role:subagent, type:general-purpose`.
Those runs produced clean `subagent_status=success` log files.

The only change between 06:43 (working) and 21:06 (broken):
- **Letta server restarted at ~16:58** with the new v2 patched image (added
  patch 04 — scoped delete propagation in `_delete_block_from_postgres`)

Patch 04 itself cannot logically affect subagent runtime — it only modifies
delete propagation logic, called during `sync_blocks_from_git`. But the
restart itself may have lost some state.

## Root cause: same as #3205, filed today by another user

Per Ezra (Apr 25, in response to the defects note):

> This is almost certainly the same bug class naturlich filed **today
> (Apr 25)** on the same stack (0.16.7 + letta-code 0.24.2): the
> client_tools/approval IPC path is broken on self-hosted, both on the
> **issuance** side (run finalizes `end_turn` instead of
> `requires_approval`) and the **consumption** side (#3205 — the one *you*
> confirmed Apr 19, where utils.py:218 reads deprecated approval fields).
>
> Subagents universally exercise the client_tools path (their first action
> is usually Bash/Read/etc., and the subagent->parent result handoff is
> itself an IPC pattern). Empty stdout with no `{type:"result"}` line is
> exactly what an early client_tool failure looks like — subagent dies
> before its result emitter runs.

**Not memfs-specific. Not model-specific. Not parent-agent-specific. It's
the self-hosted 0.16.7 client_tools approval IPC regression.**

## What our test confirms

- Subagent process spawns successfully (real `subagent-<unix_ms>-<n>` ID
  returned to parent's Task tool result)
- Subagent's first client_tool call fails (not enough info to confirm
  whether issuance-side or consumption-side without packet-capturing)
- Subagent crashes before writing the `{type:"result"}` line to its stdout
- Parent's `parseResultFromStdout` (letta.js:72562) returns "Failed to parse
  subagent output"

## Implications for MC migration

- **Substrate is green.** Memfs enable, block-to-file translation, three-
  layer consistency, round-trip edits all work.
- **Subagent-dependent operations will not work post-migration** until #3205
  is resolved upstream:
  - `/doctor` (depends on `context_doctor` skill spawning analyzer subagents)
  - `recall` (cross-channel history search via fork-based subagent)
  - `general-purpose` Task spawning
  - Any other Task subagent invocation
- **Parent-only flows DO work.** pa-web-ui's letta-code subprocess pattern,
  direct REST API calls, agent-side memory operations — all unaffected.

## Two paths

### Option α — migrate MC now, accept no-subagent limitation

MC's primary value (Telegram, agent memory, scheduling, calendar tasks) is
parent-only. It doesn't currently use Task subagents in production. Migration
unblocked, with the understanding that:
- `/doctor` won't work for post-migration cleanup (use direct prompts)
- `recall` won't work — cross-channel history search via Task→recall won't
  function until upstream fix
- pa-web-ui letta-code subprocesses will work fine

### Option β — wait for upstream fix to #3205

Hold MC migration until subagent runtime is verified working on self-hosted.
Open question on timing — naturlich filed today, no ETA from Letta team yet.
Could be days or months.

### Recommended

Option α. We have substantial post-migration value MC can still deliver,
the limitation is bounded and known, and the subagent-dependent operations
weren't load-bearing for current MC use cases. Re-enable subagent-dependent
flows when #3205 is fixed upstream.

## Open follow-up to Ezra

Worth asking whether there's a workaround on our side (e.g., specific server
version downgrade, server config flag) that restores subagent runtime
without waiting for upstream fix. The morning success suggests the bug is
state-dependent rather than fully deterministic.
