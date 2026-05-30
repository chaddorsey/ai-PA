---
date: 2026-05-30
status: backlog (multi-week project)
priority: architectural — defer until Tasks migration done
trigger: User directive 2026-05-30 — "we should not be using Letta identities for anything"
related:
  - docs/followups/2026-04-28-user-info-canonical-migration.md
  - docs/followups/2026-05-28-fleet-alignment-status.md (item I-quater)
---

# Strip Letta identities — full scope

## Why

Canonical Gitea repo (`agents-canonical/reference/people/*`) is the
source of truth for staff, working hours, preferences, slack mappings,
calendar IDs. Letta `/v1/identities/` is a parallel store from an
earlier architecture. Maintaining both is a drift hazard and locks
local-mode agents to a Docker-server dependency they shouldn't need.

## Active runtime code using Letta identities

### Scheduling orchestrator (Docker service `scheduling-orchestrator-api`)

| File | Usage | Replacement source |
|---|---|---|
| `letta/scheduling_orchestrator/identity_lookup.py` | Email → display name lookup (entire module) | Gitea: `reference/people/<bucket>/<slug>.md` `description:` line |
| `letta/scheduling_orchestrator/identity_working_hours.py` | Email → per-day working hours (`{"monday": {"start":"09:00","end":"17:00"}, …}`) | Gitea: `reference/user/prefs/working_hours.md` (Chad) + `reference/people/<bucket>/<slug>.md` `working_hours:` field per person |
| `letta/scheduling_orchestrator/evaluate_proposed_times.py` (lines 20-21, 30-31, 431, 455) | Imports + calls identity-based working hours | Same as above |
| `letta/scheduling_orchestrator/unified_slot_ranker.py` (lines 27-33, 54, 65) | `get_user_preferences_from_identity` | Gitea: `reference/user/prefs/*` (Chad's) + per-person preferences fields |
| `letta/scheduling_orchestrator/orchestrate_scheduling.py` (line 4946+) | Display name lookup for response formatting | Same as identity_lookup replacement |

**Refactor approach**: Replace `identity_lookup` and `identity_working_hours` modules with `canonical_lookup` that reads from Gitea. Keep the same callsite signatures (drop-in replacement). Docker rebuild required.

### pa-routing-handler (Docker service)

| File | Usage |
|---|---|
| `pa-routing-handler/src/pa_routing/routers/routing.py:47-79` | `_fetch_identities()`, `_identities_cache` — caches all Letta identities for routing decisions (email → identity_id) |

**Question**: what does pa-routing-handler actually need an identity_id for? If it's "look up agent_id by Slack user", that's resolved via canonical's slack_id field. If it's something else, design replacement before stripping.

### Slackbot

| File | Usage |
|---|---|
| `slackbot/ai/identity.py` | Maps Slack user_id → Letta identity_id; creates new identities for unknown Slack users |
| `slackbot/ai/conversation_helper.py` | Per-identity conversation isolation for the scheduler agent |

**Replacement**: slackbot should resolve Slack user_id → canonical person via `reference/people/*/*.md` `slack: user_id:` field. New unknown user → create a `reference/people/external/<slug>.md` stub (or queue for user to confirm). Conversation isolation should key on canonical slug, not Letta identity_id.

### Conversation tools

| File | Usage |
|---|---|
| `letta/conversation_tools/lookup_staff.py` | Custom Letta tool that queries `/v1/identities/` for a name and returns properties |

**Replacement**: become a Bash + canonical CLI pattern (or removed entirely if the agent can just curl Gitea directly per its memfs guidance).

### One-shot scripts (NOT runtime — keep as historical)

- `letta/scripts/migrate_staff_properties.py` — historical
- `letta/scripts/migrate_working_hours.py` — historical (already populated canonical)
- `scripts/seed-canonical-userinfo.py` — was the initial seed from identities → canonical; keep for reference

## Proposed phased plan

### Phase 1: Scheduling orchestrator (highest impact for fleet)

- Build `canonical_lookup.py` that mirrors `identity_lookup.py`'s
  interface but reads from Gitea HTTP. Same function signatures.
- Build `canonical_working_hours.py` that mirrors
  `identity_working_hours.py`. Same.
- Swap imports in `evaluate_proposed_times.py`,
  `unified_slot_ranker.py`, `orchestrate_scheduling.py`.
- Test: identical proposals for same input across a representative
  set of scheduling cases.
- Deploy: rebuild `scheduling-orchestrator-api` container.
- Delete old `identity_lookup.py` and `identity_working_hours.py`.

Estimated effort: 6-10 hours.

### Phase 2: pa-routing-handler

- Audit what identity_id is actually used for in routing.
- Replace with canonical-derived slug or remove if redundant.
- Rebuild container.

Estimated effort: 2-4 hours.

### Phase 3: Slackbot

- Replace identity-based Slack user mapping with canonical lookup
  by `slack.user_id` field.
- Replace conversation isolation key (identity_id → canonical slug).
- Handle unknown Slack users: queue for canonical creation rather
  than auto-creating Letta identity.
- Rebuild slackbot container.

Estimated effort: 4-6 hours.

### Phase 4: Conversation tools cleanup

- Decide fate of `lookup_staff.py` — remove or convert to canonical
  Bash recipe.
- Verify no agent still has it attached.

Estimated effort: 1-2 hours.

### Phase 5: Letta identities decommission

After all callers gone, delete identity records (or leave them as
inert historical data — they don't cost anything to retain except
mental load).

## Immediate impact on calendar-agent migration

The Calendar agent's evening-slot bug stems from the orchestrator's
work-hours data coming from Letta identities, which may not have
per-person data populated. The right fix is Phase 1 above.

**Interim workaround**: agent should parse `explanation` from
orchestrator response and surface "no clean slots" honestly rather
than presenting override-suggestions as clean proposals. This is the
agent-side fix queued in the prior turn. The orchestrator-side fix
(canonical-backed work hours) is Phase 1 of this plan.

## Out of scope

This is NOT in scope:

- Deleting docs/plans/* historical references to identities
- Modifying auto-madden insight_engine identity refs (unrelated subsystem)
- Migrating identity-DB-backed agent-conversations storage (different concern)

## When to start

After Tasks migration (next fleet agent). The Phase 1 work specifically
should land before any more agents migrate that depend on the scheduler
(Calendar already migrated and lives with the workaround; future agents
should hit a clean orchestrator).
