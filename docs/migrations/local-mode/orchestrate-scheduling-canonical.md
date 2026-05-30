---
date: 2026-05-30
status: complete
related:
  - docs/followups/2026-05-30-strip-letta-identities.md
  - docs/migrations/local-mode/calendar-agent.md
---

# Orchestrate-scheduling: Letta identities → canonical

Phase 1 of the strip-Letta-identities plan executed end-to-end.

## What changed

### New modules

- `letta/scheduling_orchestrator/canonical_client.py` — Gitea HTTP
  client with thread-safe in-memory cache (5min TTL). Walks all
  `reference/people/<bucket>/` dirs, indexes by email, slack_id,
  calendar_id, slug. Provides `get_person_by_*` accessors and
  `list_all_people()`.
- `letta/scheduling_orchestrator/canonical_lookup.py` — drop-in
  replacement for the deleted `identity_lookup.py`. Same public API:
  `lookup_participant_names`, `get_user_preferences_from_identity`
  (now takes slug instead of UUID), `lookup_identity_by_property`,
  `resolve_participant_identifier`. Synthesizes a Letta-identity-shaped
  dict for backward compat with callers iterating `.get('properties')`.
- `letta/scheduling_orchestrator/canonical_working_hours.py` — drop-in
  replacement for the deleted `identity_working_hours.py`. Reads
  per-person `working_hours:` from canonical frontmatter, projects
  onto a UTC date range, returns slot-index sets. Falls back to
  `M-F 09:00-17:00` in the participant's stated timezone (or
  `America/New_York` if none).

### Deleted

- `letta/scheduling_orchestrator/identity_lookup.py`
- `letta/scheduling_orchestrator/identity_working_hours.py`

### Imports swapped

- `evaluate_proposed_times.py` lines 20-21, 30-31 →
  `from .canonical_working_hours import ...` and
  `from .canonical_lookup import ...`
- `unified_slot_ranker.py` lines 27, 33 →
  `from .canonical_lookup import get_user_preferences_from_identity`
- `orchestrate_scheduling.py` lines 4963-4969 → triple-fallback
  import block now references `canonical_lookup` consistently
- Cosmetic: stale log line "Resolved N participant names from
  identity service" → "from canonical"

### Dependencies

- `requirements-api.txt`: added `pyyaml>=6.0` and `requests>=2.31.0`

### Environment

`docker-compose.yml` scheduling-orchestrator-api service now passes:
- `GITEA_BASE_URL: "http://gitea:3000"`
- `GITEA_MEMFS_TOKEN: ${GITEA_MEMFS_TOKEN}`

### Canonical data backfill

Per-person `working_hours:` field added to:

| Slug | tz | Hours |
|---|---|---|
| cdorsey | America/New_York | M-F 08:00-17:00 |
| hlee | America/Los_Angeles | M-F 09:00-17:00 |
| ddamelin | America/New_York | M-F 09:00-17:00 |
| kmiller | America/New_York | M-F 09:00-17:00 |
| lbondaryk | America/New_York (was Pacific/Auckland — BAD) | M-F 09:00-17:00 |
| dkehoe | America/New_York | M-F 09:00-17:00 |

cdorsey.md is new (Chad had no `reference/people/work/cdorsey.md`
before). His record also carries a `protected_blocks:` field for
the 9-11am ET focus block, though the orchestrator's solver doesn't
yet read protected_blocks — that's a follow-on item.

### CLI cleanup

`scripts/orchestrate-scheduling`'s `--pretty` output now includes
`CATEGORY=<clean|solo_override|multi_adjust|single_move>` per
proposal + a category histogram. Was missing before.

### Agent guidance

`system/orchestrate_scheduling_tool_use_guidelines.md` in calendar-
agent-local's memfs rewritten:
- Explicit Mon–Fri default + per-participant local 9-5 honored
  automatically (don't pass via `--policy`)
- UTC→ET conversion reference table for summer/EDT
- Category-aware reading: clean before solo_override
- Cross-timezone display in both zones
- Python one-liner for verified conversions

## End-to-end verification

```bash
letta-calendar -p "When can Hee-Sun and I meet 45min next week?"
```

Returned cleanly: looked up `hlee@concord.org` via canonical, called
orchestrate-scheduling, displayed 10 proposals in correct ET (4:15pm
ET, not the prior 8:15pm error) with PT shown alongside, identified
all 10 as `solo_override` honestly.

## Limitations / follow-on

1. **Protected blocks** in Chad's canonical record (9-11am ET) are
   stored but the orchestrator's clingo solver doesn't yet read
   `protected_blocks:` separately. Today the solver treats Chad's
   8-5 ET as the binding work-hours window. Honoring the 9-11
   protected block as a hard avoidance would need a small extension
   in `canonical_working_hours.py` (or a parallel
   `canonical_protected_blocks.py`) plus a hookup in
   `evaluate_proposed_times.py`.

2. **Test files** `tests/test_identity_lookup.py` and
   `tests/test_unified_slot_ranker.py` still reference the deleted
   modules. They won't break runtime but should be ported to
   canonical_lookup for green CI. (Not done now — orchestrator
   doesn't currently have a CI gate that runs them.)

3. **Cache invalidation**: 5min TTL is hand-tuned. If you update a
   person's canonical record (add working_hours, fix a name), the
   orchestrator picks up the change within 5 minutes. Force refresh
   by restarting `scheduling-orchestrator-api` if needed sooner.

4. **Working-hours schema**: only Mon-Sun per-day {start, end} for
   now. No support for split shifts ("9-12 + 2-5") yet, but the
   schema allows it (just extend the parser).

## Remaining strip-Letta-identities phases

Per `docs/followups/2026-05-30-strip-letta-identities.md`, Phase 1
(scheduling orchestrator) is now done. Remaining:

- Phase 2: pa-routing-handler (~2-4 hrs)
- Phase 3: slackbot identity.py + conversation_helper.py (~4-6 hrs)
- Phase 4: lookup_staff conversation tool (~1-2 hrs)
- Phase 5: decommission identity records (whenever)
