---
date_started: 2026-05-30
date_phase_h: 2026-05-30
status: migrated, soaking
agent_old_id: agent-892a2d58-b9f6-4baf-84f3-c431fe46487d
agent_old_name_now: XXX-PRE-LOCAL-calendar-agent_copy
agent_new_id: agent-local-cd5ed5cd-44d5-4e32-b202-3d8dfcb5505c
agent_new_name: calendar-agent_copy-local
model: lmstudio/gpt-5.4-nano
backup: /Volumes/main-filestore/ai-PA-backups/local-mode-migrations/calendar-agent_copy/
launcher: ~/bin/letta-calendar
launch_cwd: /Volumes/main-drive/letta-launchpad
---

# Calendar migration log

Second per-agent local-mode migration. Smallest fleet target (4 tools, 1
cron). Executed 2026-05-30 in same session as Docs migration.

## What migrated

- Agent record + system prompt
- 14 system/*.md memfs files (after Phase D cleanup; see below)
- 1 cron job repointed: `Pipeline-health: calendar-agent daily self-check`
  (06:30 ET, route=local + new agent_id)

## Phase D cleanup applied

The Docker calendar memfs had 5 issues the local-mode pre-commit hook
would have rejected:

1. **`system/agent_info.md`** had `read_only: true` — stripped before commit.
2. **`preferences_U02V91KU8.md`** — missing YAML frontmatter, added a minimal block.
3. **`preferences_U0AB18G54ET.md`** — missing frontmatter, added minimal.
4. **`preferences_identity-42c594bb-92bd-45ff-ad1a-2e609976eb1c.md`** — missing frontmatter, added minimal.
5. **`preferences_identity-4b355b96-5a33-48c7-bac1-f2b88b517e12.md`** — missing frontmatter, added minimal.

The added frontmatter blocks are placeholders for description; the agent
can refine during the soak window.

## Item A: preferences canonical dedup

The 5 preferences files imported verbatim ARE the alignment doc's Item A
worst case:

- `preferences_U02V91KU8.md` (Slack user ID format — likely identity-stale)
- `preferences_U0AB18G54ET.md` (Slack user ID format)
- `preferences_identity-42c594bb-92bd-45ff-ad1a-2e609976eb1c.md`
- `preferences_identity-4b355b96-5a33-48c7-bac1-f2b88b517e12.md`
- `user_preferences.md` (generic)

Recommended post-Phase-H pattern: have calendar-agent-local do its own
consolidation. It has all the context to compare the 5 files, identify
what's canonical vs duplicate vs stale, and merge into a single
`user_preferences.md` (or `users/<canonical-id>/preferences.md` per the
canonical-seed-curation runbook). Don't preempt — let the agent see them
in context first, then ask it.

## What did NOT migrate

- **3 archival passages** preserved on Docker side (small, low-stakes).
- Custom Letta tools (only 2 non-built-in: `emit_canonical_signal` → `signal` CLI; `orchestrate_scheduling` → `orchestrate-scheduling` CLI). Both on host PATH.

## Two-headed runtime state

Slackbot multi-user scheduling still routes to the renamed Docker agent
via `LETTA_SCHEDULER_AGENT_ID` env (docker-compose.yml:974). Agent_id
unchanged, so the renamed Docker agent continues serving slackbot
transparently. Local agent serves direct TUI invocations + cron-driven
pipeline-health.

**Defer slackbot repoint** until item G (slackbot routing pattern
decision) lands. Same architectural posture as Docs.

Other refs (letta/*.py scripts, docs/*) are historic / one-shot, no
runtime impact.

## Phase E smoke results

All sub-5s — gpt-5.4-nano + small memfs is a snappy combo.

| Test | Time | Result |
|---|---|---|
| E1 identity | 2.8s | ✅ Correct self-identification |
| E2 memfs round-trip | 4.4s | ✅ Chained `cd && git add && commit` worked first try, frontmatter preserved |
| E3 orchestrate-scheduling --help | 3.2s | ✅ Accurate CLI summary |

E2 succeeded on first attempt because the chained-Bash pattern was
already in the imported `system/tool_use_guidelines_meetings_docs.md`
from the Docs migration recipe — except wait, this is Calendar, not
Docs. Calendar didn't have the lessons-learned applied to its memfs
yet. So either: (a) gpt-5.4-nano happens to know the pattern naturally,
or (b) the system prompt was explicit enough in the user request. Worth
adding the same recipe to Calendar's `orchestrate_scheduling_tool_use_guidelines.md`
during soak for resilience.

## Rollback path (within 7-day soak)

1. Revert cron job:
   ```bash
   curl -sS -X PATCH http://localhost:8087/v1/jobs/1ccfae03-41bb-4944-8b4c-7fea40605373 \
     -H "Content-Type: application/json" \
     -d "@/Volumes/main-filestore/ai-PA-backups/local-mode-migrations/calendar-agent_copy/cron-1ccfae03-*-original.json"
   ```
   (Or PATCH back agent_id + drop route field.)

2. Rename Docker agent back:
   ```bash
   curl -X PATCH http://localhost:8283/v1/agents/agent-892a2d58-b9f6-4baf-84f3-c431fe46487d \
     -d '{"name":"calendar-agent_copy"}'
   ```

3. Stop using `~/bin/letta-calendar`. Slackbot continues working
   throughout (it never stopped, since we left LETTA_SCHEDULER_AGENT_ID
   pointing at the Docker agent's preserved agent_id).

## Soak items to validate

- [ ] Tomorrow's 06:30 ET pipeline-health cron fires successfully against local agent
- [ ] Direct TUI use via `letta-calendar` produces correct slot proposals
- [ ] `orchestrate-scheduling` CLI behaves identically when invoked by agent vs by hand
- [ ] Item A consolidation: ask agent to dedup the 5 preferences files
- [ ] Verify `signal` CLI emit lands at canonical store (replaces emit_canonical_signal)
