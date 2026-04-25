---
date: 2026-04-25
status: substrate validation COMPLETE; /doctor + Task→TaskOutput defects flagged
agents tested: calendar-agent (memgpt_v2), Letta Code agent-7f293624 (letta_v1)
parent: docs/plans/2026-04-24-001-feat-letta-memfs-upgrade-plan.md
---

# Memfs migration rehearsal — combined results

## Substrate validation: COMPLETE

End-to-end memfs migration mechanics validated across two test agents. The
substrate is production-ready for MC migration once the shared canonical
store is designed.

### Tests run

| Test | Calendar-agent (`memgpt_v2_agent`) | Letta Code (`letta_v1_agent`) |
|---|---|---|
| `/memfs enable` substrate | ✓ 19 blocks → 17 files (after 2 detached) | ✓ 2 blocks → 2 files |
| Block→file translation | ✓ all blocks mapped to `system/<label>.md` | ✓ same |
| Three-layer consistency at enable | ✓ local / bare repo / Gitea match | ✓ same |
| Identity preservation | ✓ same agent_id, history intact | ✓ same |
| Patch 04 (scoped delete propagation) | ✓ verified empirically before rehearsal | (no shared blocks to test) |
| Read tool against memfs | (not validated, persona-blocked) | ✓ verified by user |
| Edit tool round-trip | (not validated, persona-blocked) | ✓ propagated through all 4 layers |

### Round-trip propagation pattern (CRITICAL for runbook)

letta-code Edit tool propagates **local working tree → Gitea automatically**,
but the **server-side bare repo + Postgres cache do NOT auto-sync**. They
require an explicit `POST /v1/agents/<id>/memory/sync-from-git` (the patched
endpoint pulls Gitea → bare repo → Postgres atomically).

Implication: agents reading via REST API (pa-routing-handler, pa-web-ui task
review sidebar, slackbot, etc.) see **stale content** until sync-from-git is
called. Production migration runbook must include either:
- A scheduled sync-from-git (cron-style)
- Post-edit hook in letta-code (need to check if 0.24.4 has this)
- Manual sync after any memfs edit session

OPEN QUESTION: does letta-code auto-trigger sync-from-git on session end? To
be checked in source before MC migration.

## Defects flagged for Ezra

### 1. `/doctor` failure mode A — persona without Skill awareness

**Repro target**: calendar-agent (`memgpt_v2_agent`, "master scheduler" persona).

`/doctor` correctly client-intercepted by letta-code TUI (line 154823).
`buildDoctorMessage` (line 83960) injected the standard template directing the
agent to invoke `Skill(context_doctor)`. **Agent did not invoke Skill** —
fell back to `web_search` and looped (151 messages, hit max_steps).

Root cause: calendar-agent's persona has no language about Skill tool or
context_doctor. The agent has no idea what to do with the doctor template
beyond "search for what /doctor means."

**Resolution path** for MC pre-migration: add explicit Skill+context_doctor
language to MC's persona (per Ezra's Option A) so it knows to invoke the
skill when the doctor template fires.

### 2. `/doctor` failure mode B — Task→TaskOutput protocol bug

**Repro target**: agent-7f293624 (`letta_v1_agent` + `origin:letta-code`,
gpt-5.2 model, with letta-code-paradigm persona that DID know to invoke
`Skill(context_doctor)`).

Sequence:
- `/memfs enable` ✓
- `/doctor` → `Skill(skill: "context_doctor")` invoked correctly ✓
- Skill instructs the agent to spawn analyzer subagents via Task and read
  their output via TaskOutput
- Agent calls `TaskOutput(non-blocking)` with **hallucinated IDs** (`task_1`,
  `task_2`, `task_1.log`, `subagent-persona-first5`) instead of real
  Task-returned IDs
- Agent appears to be using Claude-Code-style task naming patterns from
  training rather than capturing actual return values from Task

Reproducible across:
- `/doctor` flow
- Direct prompt: "Use Task tool to spawn a general-purpose subagent..."
- Both with --yolo and without

In some calls Task IS invoked and returns real IDs (e.g.
`subagent-1776661684849-1` with unix timestamp). In others the agent skips
Task entirely and hallucinates. Behavior is intermittent.

This is the root cause of /doctor's max_steps in our second test — the
context_doctor skill flow depends on Task→TaskOutput working reliably, and
the agent's behavior makes that unreliable.

**Speculation**: possibly a tool-definition or system-prompt ordering issue
that lets the agent confuse "predict an ID" with "use the returned ID from a
prior call." Possibly model-specific (gpt-5.2). Worth investigating in
letta-code 0.24.4 source.

## What this means for MC migration

- **Substrate-level mechanics: green-light.** MC's `/memfs enable` will work
  cleanly given MC is `letta_v1_agent` + `origin:letta-code`.
- **Don't depend on `/doctor`** as the cleanup step. Run an audit-prompt
  manually instead. The Task→TaskOutput defect makes /doctor unreliable, and
  the persona-awareness needs to be added regardless.
- **Add to MC pre-migration prep**:
  - Persona language for Skill+context_doctor invocation (Option A)
  - Manual cleanup-audit prompt prepared in advance (since /doctor is
    unreliable)
  - Plan for sync-from-git cadence post-migration (so REST consumers see
    fresh data)

## Pre-migration runbook updates

The "two-pass /memfs enable" friction we hit twice (server-side enable
succeeds → local clone fails because Gitea repo doesn't exist yet → manually
push bare→Gitea → re-run /memfs enable) should be automated for MC. Wrapper
script:

1. Tag agent + POST sync-from-git via REST (server-side enable + backfill)
2. Create Gitea repo if missing (idempotent)
3. Push bare repo content from container to Gitea
4. Then user opens TUI and `/memfs enable` is just a clean clone

This reduces MC migration to a single TUI session instead of a two-pass
dance, reduces failure surface area, and makes the runbook scriptable.
