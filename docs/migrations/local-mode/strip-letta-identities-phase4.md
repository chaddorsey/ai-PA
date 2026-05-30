---
date: 2026-05-30
status: complete
phase: 4 (lookup_staff removal)
related:
  - docs/followups/2026-05-30-strip-letta-identities.md
  - docs/migrations/local-mode/orchestrate-scheduling-canonical.md (Phase 1)
  - docs/migrations/local-mode/decommission-pa-routing-handler.md (obviated Phase 2)
---

# Phase 4: lookup_staff removal

`lookup_staff` was a custom Letta tool at
`letta/conversation_tools/lookup_staff.py` that queried `/v1/identities/`
to resolve colloquial names ("Dan") to identity properties. Part of
the Letta-identities strip-out plan.

## State before this turn

- Tool registered in Letta server (`tool-6dd8f7c5-...`)
- **Attached to zero agents** — dead code in production but still
  registered
- Source ~149 lines + 1 test file
- Referenced from 6 other files (registration scripts, init,
  test_conversation_pilot, two system-prompt template scripts)

## What changed

### Letta server

- Deleted tool registration (HTTP 200 from DELETE
  `/v1/tools/tool-6dd8f7c5-...`)
- No agents had it attached, so no detachment needed

### Filesystem

- `letta/conversation_tools/lookup_staff.py` → `archived/letta-conversation-tools/lookup_staff.py`
- `letta/conversation_tools/tests/test_lookup_staff.py` → `archived/letta-conversation-tools/test_lookup_staff.py`

### Source edits

- `letta/conversation_tools/__init__.py`: removed import + `__all__`
  entry; left a removal-notice comment pointing at archived source
- `letta/register_conversation_tools.py`: removed import + registration
  entry + summary print line
- `letta/attach_conversation_tools_to_agent.py`: removed from
  `CONVERSATION_TOOLS` list; updated success summary print
- `scripts/test_conversation_pilot.py`: removed
  `test_lookup_staff_tool_registered` function + its caller +
  references in the two `required = [...]` checklists
- `letta/create_domain_specific_blocks.py`: updated system-prompt
  template's "Colleague Coordination" section to point at canonical
  lookup instead of `lookup_staff`
- `letta/update_agent_system_prompts_v1.py`: same swap in the scheduler
  agent's workflow template

## Verification

```
git grep "lookup_staff" | grep -v docs/ | grep -v __pycache__ | grep -v archived/
# → all remaining matches are removal-notice comments

curl /v1/tools/?limit=500 | grep lookup_staff
# → NONE

ls letta/conversation_tools/
# → __init__.py, create_user_memory_block.py, find_user_blocks.py, tests/
#   (lookup_staff.py gone, dir still has the 2 other tools)
```

## Sibling tools also dead

Audit during this work found that the other two tools in
`letta/conversation_tools/`:

- `find_user_blocks` — registered, attached to ZERO agents
- `create_user_memory_block` — registered, attached to ZERO agents

These were part of the same Jan 2026 multi-user conversation pilot that
didn't take. They don't touch Letta identities (their job is memory-block
discovery / creation), so they're out of scope for the identity strip-out
phase plan. But they're dead code worth cleaning up separately.

**Followup tracked**: `docs/followups/2026-05-30-strip-letta-identities.md`
Phase 4 closed; the broader `conversation_tools/` decom would be a
separate small cleanup session.

## Remaining strip-out phases

- Phase 2: pa-routing-handler — obviated by 2026-05-30 decommission
- Phase 3: slackbot identity.py + conversation_helper.py — ~4-6 hrs,
  gates MC migration. **Largest remaining piece.**
- Phase 5: decommission identity records themselves — <1 hr cosmetic
