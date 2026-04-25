---
date: 2026-04-25
target: calendar-agent (agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218, OLD/deprecated)
status: pre-flight ready for TUI rehearsal
parent: docs/plans/2026-04-24-001-feat-letta-memfs-upgrade-plan.md
---

# Calendar-agent — pre-flight for v1 TUI memfs rehearsal

This is the load-bearing rehearsal that informs MC's eventual migration
path. Calendar-agent is decommissioned-in-place (last update 39 days
ago, last message ~12 weeks), uses the same `gpt-4.1-mini` via litellm
that MC and most production agents use, and has a realistic block
ecosystem (19 attached, 17 isolated + 2 shared). Identity preserved
across migration per Ezra's "same agent_id = same identity" path.

## State snapshot (as of 2026-04-25)

| Field | Value |
|---|---|
| agent_id | `agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218` |
| name | calendar-agent (the OLD one; not `calendar-agent_copy`) |
| agent_type | `memgpt_v2_agent` (V1-style) |
| llm model | `gpt-4.1-mini` (verified working: 1.5s round-trip ping) |
| tags | `[]` |
| block count | 19 |
| last update | 2026-03-17 (39d) |
| last message | 2026-02-03 (~12w) |

## Block sharing classification

**Shared (need pre-port detach):**

| Label | Block ID | Attached agents |
|---|---|---|
| `important_people` | `block-ec381d6a-57be-4b33-9333-121d2888cdfb` | 3 |
| `extracted_tasks` | `block-7bff4e45-3406-48e9-bc51-4fadaea61e57` | 14 (legacy block; canonical is `block-90300b77`) |

**Isolated (will translate via `/memfs enable`):** 17

Core memgpt blocks:
- `persona` (7054 chars)
- `human` (435 chars)
- `agent_info` (128 chars)

Calendar-specific operational:
- `scheduling_context` (418 chars)
- `user_calendar_context` (447 chars)
- `user_preferences` (76 chars)
- `orchestrate_scheduling_tool_use_guidelines` (6716 chars)
- `response_formatting_guidelines` (833 chars)

Cruft / test residue (`/doctor` will likely propose removing):
- `preferences_TEST_VERIFY_E2E` (40 chars)
- `preferences_TEST_SLACKBOT_HELPER` (83 chars)
- `preferences_TEST_E2E_FULL` (83 chars)
- `coordination_task_identity-test-manual` (23 chars)
- `coordination_gathered_identity-test-manual` (28 chars)

User-specific preferences (relevance unclear — may be live, may be stale):
- `preferences_U02V91KU8` (273 chars) — Slack user ID
- `preferences_U0AB18G54ET` (315 chars) — Slack user ID
- `preferences_identity-42c594bb-...` (83 chars)
- `preferences_identity-4b355b96-...` (83 chars)

## Rehearsal sequence

The user runs steps 2-4 from a terminal where `letta-code` is installed.
Claude Code (this assistant) watches via REST queries / docker logs / git
log on the bare repo and checkpoints between steps.

**1. Defensive pre-port detach (REST, can be run from anywhere):**

```bash
LETTA="http://localhost:8283"
A="agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"

# Detach important_people (3-agent shared)
curl -X PATCH "$LETTA/v1/agents/$A/core-memory/blocks/detach/block-ec381d6a-57be-4b33-9333-121d2888cdfb"

# Detach extracted_tasks (14-agent shared, legacy block)
curl -X PATCH "$LETTA/v1/agents/$A/core-memory/blocks/detach/block-7bff4e45-3406-48e9-bc51-4fadaea61e57"

# Verify: calendar-agent down to 17 attached blocks
curl "$LETTA/v1/agents/$A" | jq '.memory.blocks | length'
```

**2. Open in TUI (interactive, from a terminal):**

```bash
LETTA_BASE_URL=http://localhost:8283 letta --agent agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218
```

Confirm the agent loads, conversation history is intact, no errors in the
splash. Then proceed to slash commands.

**3. `/memfs enable`:**

In the TUI, type `/memfs enable`.

Expected:
- 17 isolated blocks → `system/<label>.md` files in the bare repo
- Bare repo at `/root/.letta/memfs/repository/<org_id>/<agent_id>/repo.git/`
  gets initialized with a real commit containing the 17 files
- Local working tree materialized at `~/.letta/agents/<agent_id>/memory/`
- Tag `git-memory-enabled` set on the agent
- Postgres blocks remain (cache layer per the patched
  GitEnabledBlockManager design — git is source of truth, postgres
  caches reads)

Watch for: any error about model auth, any patch-related error, any
block-translation failure (e.g. block contents not roundtripping
correctly to markdown).

**4. `/doctor`:**

In the TUI, type `/doctor`.

Expected:
- Agent self-evaluates the filesystem layout
- Proposes cleanup of stale blocks (the 5 cruft items listed above)
- May propose reorganizing how blocks group into directories
  (system/ vs reference/ vs other)

We inspect proposals before accepting. Accept the obviously-correct
ones, defer or refine the rest.

## Verification queries (Claude Code runs between steps)

```bash
# After step 1 (detach):
curl -s "$LETTA/v1/agents/$A" | jq '.memory.blocks | length'  # expect 17

# After step 3 (/memfs enable):
curl -s "$LETTA/v1/agents/$A" | jq '.tags'  # expect ["git-memory-enabled"]
docker exec ai-pa-letta-1 git --git-dir=/root/.letta/memfs/repository/org-00000000-0000-4000-8000-000000000000/agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218/repo.git log --oneline | head -5
docker exec ai-pa-letta-1 git --git-dir=/root/.letta/memfs/repository/org-00000000-0000-4000-8000-000000000000/agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218/repo.git ls-tree -r HEAD | head -20

# After step 4 (/doctor):
# diff between git log entries to see what doctor changed
docker exec ai-pa-letta-1 git --git-dir=... log -p HEAD~1..HEAD
```

## Rollback path if anything goes wrong

```bash
# Drop the tag (immediate "memfs disabled" from server perspective)
curl -X PATCH "$LETTA/v1/agents/$A" -H "Content-Type: application/json" \
  -d '{"tags": []}'

# Optionally remove the bare repo (won't affect Postgres blocks because
# memfs-disabled agent doesn't read from git)
docker exec ai-pa-letta-1 rm -rf \
  /root/.letta/memfs/repository/org-00000000-0000-4000-8000-000000000000/agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218

# Re-attach the 2 shared blocks if desired
curl -X PATCH "$LETTA/v1/agents/$A/core-memory/blocks/attach/block-ec381d6a-57be-4b33-9333-121d2888cdfb"
curl -X PATCH "$LETTA/v1/agents/$A/core-memory/blocks/attach/block-7bff4e45-3406-48e9-bc51-4fadaea61e57"
```

Calendar-agent is decommissioned, so even if rollback is messy, blast
radius is contained to the agent itself.

## What this rehearsal will tell us

- Whether the TUI's `/memfs enable` translation produces sensible
  `system/<label>.md` files for V1-style blocks (informs MC migration)
- Whether `/doctor` produces useful cleanup proposals (a load-bearing
  step Ezra called out)
- Whether the shared canonical store needs to exist before MC migration,
  or whether Pattern-1 blocks can be deferred (we'll see what `/doctor`
  says about `important_people` if/when it's missing post-detach)
- Empirical baseline for "how much manual work is in a v1 → memfs port"
  to inform the MC migration plan
