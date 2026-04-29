---
date: 2026-04-28
status: plan-not-yet-executed
priority: medium-high
---

# User Info → Canonical Migration

Plan for consolidating where user (and people, project, organization) info
lives across the system. Surfaced during the Zoom-link conversation and
the related "Letta identities deprecated" callout.

## Problem statement

User info is scattered across **five buckets** today, none coordinated:

1. **Letta identities table** (server-side) — *deprecated per upstream*
   - 20 records: Chad + family + collaborators (Aditi Wagh, Michael Tirenin, etc.)
   - Schema: id, name, type — minimal
   - Some agent prefs files key off these IDs (e.g., `preferences_identity-4b355b96-...`)
2. **Per-agent memfs `preferences_*` blocks** — inconsistent across agents
   - calendar-agent has 5: `preferences_U02V91KU8` (Slack-keyed for Chad), `preferences_identity-4b355b96` (Letta-id-keyed for Chad — duplicate), `preferences_U0AB18G54ET`, `preferences_identity-42c594bb`, etc.
   - SAME person stored 2× (Slack ID + Letta identity ID)
   - Not shared across agents
3. **MC's `system/important_people`** — different shape
   - 341 chars, just a list of priority-monitoring senders
   - Not actual contact info
4. **Embedded in personas / shared_context / playbooks**
   - tasks-agent persona is 16,451 chars (almost certainly carries user facts mixed with behavior)
   - MC's `shared_context` is 1,140 chars (work prefs, monitoring, guardrails)
   - Behavioral guardrails + identity facts mixed
5. **Implied / nowhere yet**
   - Conferencing info (Zoom PMI) — until just now, nowhere
   - Phone numbers, addresses, alt emails, working hours — scattered or missing
   - Project metadata — nowhere centralized

**Notably empty:** `agents-canonical/` had only `signals/` until this session — no canonical user-info store.

## Letta identities deprecation

Upstream is deprecating Letta identities (the user-keyed records in the
server DB). Anything that consumed identity IDs needs to migrate before
the table goes away. Concrete consumers found in this repo:

- calendar-agent's `preferences_identity-<uuid>.md` blocks (3 of them)
- Possibly tools / orchestrator consumers (need audit)

**Source-of-truth for "who are these people" needs to move to canonical** —
specifically `reference/people/<email-slug>.md`.

## Target organization (proposed)

```
agents-canonical/
  signals/<date>/...                # Layer 5 (exists)
  reference/                        # Layer 1 (just started)
    user/                           # the system's primary user (Chad)
      profile.md                    # name, primary email, phone, timezone, role
      conferencing.md               # Zoom PMI, alt links, dial-ins (✓ scaffolded today)
      working_hours.md              # 9-11 AM protected, etc.
      monitoring_priorities.md      # priority senders/channels (was MC's important_people)
    people/<email-slug>.md          # other people: collaborators, family, contacts
    projects/<slug>.md              # project metadata
    organizations/<slug>.md         # external org context (Cisco, Hewlett, NSF, etc.)
```

### Standard frontmatter

```yaml
---
description: <one-line>
updated_by: <agent-name | 'user'>
updated_at: <ISO-8601 UTC>
# optional cross-refs:
slack_user_id: <U…>          # for people files
letta_identity_id: <id>      # legacy, optional, will go away
emails: [<list>]
roles: [<list>]
---
```

### Naming

- `email-slug` = local-part of email lowercased with `-` separators (e.g. `apallant@concord.org` → `apallant-concord-org.md` or just `apallant.md` if domain context is implied)
- `<slug>` = kebab-case stem (e.g., `cisco-stemk12`, `hewlett-foundation`)

## Migration plan (sequenced)

### Phase 1 — Seed canonical (cheap, additive)
- ✓ `reference/user/conferencing.md` (template, awaiting Chad's values)
- `reference/user/profile.md` (name, role, timezone, emails — Chad fills in)
- `reference/user/working_hours.md` (extract from playbook + shared_context)
- `reference/user/monitoring_priorities.md` (extract from MC's `important_people` + Slack/email priorities baked into playbook)

### Phase 2 — People migration (one shot per person)
For each Letta identity record:
1. Resolve to email if not already known (check Slack profile via user_id, check calendar attendees, ask user if unsure)
2. Create `reference/people/<email-slug>.md` with frontmatter that includes the legacy Letta identity ID for cross-ref during transition
3. Copy any per-agent `preferences_identity-<that-uuid>` content into the canonical file
4. Remove the per-agent `preferences_identity-*` blocks (or leave them as thin pointers to canonical for back-compat during transition)

20 identity records to migrate. Some are family (Liz, Liam, Sophia Dorsey) — minimal info; some are collaborators (Aditi Wagh, Michael Tirenin, etc.) — fuller info expected.

### Phase 3 — Persona slimming
For each migrated agent: extract user-facts content from `persona.md` and `shared_context.md` and replace with thin reference cross-refs:

> "User profile lives in `agents-canonical/reference/user/profile.md`.
> Monitoring priorities in `reference/user/monitoring_priorities.md`.
> Read these via Bash + curl when relevant."

This shrinks persona blocks (good for prompt-cache discipline per Ezra's #1775 concern) and centralizes truth.

### Phase 4 — Letta identities sunset
- Audit any remaining consumers of the identities table
- Remove the per-agent `preferences_identity-*` blocks (or set them empty if any code path still loads them by name)
- Rely on canonical `reference/people/` exclusively going forward

### Phase 5 — Steward upkeep
- Daily steward task: scan agents' personas for user-facts content that
  drifted away from canonical; flag drift via `signals/<date>/steward-userinfo-drift.md`
- Periodic prune of `reference/people/<x>.md` files that haven't been touched in 6+ months and represent stale relationships

## Access primitives

**No new Letta tools.** Read/write via Bash + curl (see
`system/canonical_reference_protocol.md` in MC's memfs).

Required env vars:
- `GITEA_MEMFS_TOKEN` (now propagated to pa-web-ui ✓; was already in letta sandbox; calendar-agent has it via Letta tool sandbox)
- `GITEA_BASE_URL` (defaulted to `http://gitea:3000` inside docker network)

### One open question — host-side agents (lettabot)

The lettabot daemon spawns letta-code with `--no-memfs`. It also doesn't
have GITEA_MEMFS_TOKEN in its env (it's a host-side process). For
Telegram users to read canonical references, lettabot needs the token
too. Out of scope for this migration but worth tracking.

## Why no new tools

Per `feedback_capability_pattern_choice.md`: read/write a known canonical
file is a deterministic procedural op with clear I/O. Bash + curl is
exactly the middle-ground pattern that should be reached for first.
Tools cost ~50–200 tokens/turn always-loaded; we already have signal
tools (`emit_canonical_signal`, `read_recent_signals`) for the dated
write-and-query path. A second pair for `reference/` would be
redundant + costly.

If, later, we find agents are repeatedly reaching for the same handful
of `reference/people/<x>.md` lookups, we could consider a thin
`get_person(email)` helper. But not before there's a real frequency
signal that justifies it.

## Cross-refs

- `docs/runbooks/agent-memfs-conventions.md` — layer model + memfs vs. canonical vs. blocks
- `docs/followups/2026-04-28-block-layer-and-rescheduling-input.md` — block-layer audit
- `docs/followups/2026-04-28-signals-roadmap.md` — Layer 5 signal extension plan
- `system/canonical_reference_protocol.md` (MC memfs) — Bash+curl read/write recipe

## Cost estimate

- Phase 1: ~30 min, mostly user filling in profile values
- Phase 2: ~2 hr (20 identity migrations, including email resolution + content transcription)
- Phase 3: ~1 hr per agent persona slim (3-5 agents)
- Phase 4: ~30 min cleanup + audit
- Phase 5: small skill + cron job; ~1 hr

Suggested order: Phase 1 first (especially `profile.md` so the system has Chad's basics), then Phase 2 in batches when convenient. Phase 3+4 can wait until Letta upstream actually retires identities.
