---
date: 2026-05-30
status: backlog
priority: post-migration cleanup
related:
  - docs/migrations/local-mode/calendar-agent.md
  - docs/migrations/local-mode/docs-and-transcripts-agent.md
  - docs/followups/2026-05-30-multi-agent-tui-workflow.md
---

# Refactor: per-agent system/ tool-use guides → shared skills

## Context

During Calendar migration shakedown we noticed that several
`system/*tool_use_guidelines*.md` files in agent memfs are really
procedural recipes — "when user asks X, run CLI Y with these flags."
They live in every turn's context (after recompile) but are only
invoked occasionally.

The letta-code skill mechanism is designed exactly for this pattern.
Skills load on demand based on description match. Per-turn token cost
is zero unless the agent reaches for the skill.

## Concrete candidates for skill refactor

Calendar:
- `system/orchestrate_scheduling_tool_use_guidelines.md` (~3K tokens)
  → `~/.letta/skills/orchestrate-scheduling/SKILL.md`

Docs:
- (none currently — the tool-use guidelines there are more identity
  than procedural)

Shared across multiple agents (once migrated):
- `canonical_reference_protocol.md` people-lookup section (~2K
  tokens; redundantly stored per-agent right now)
  → `~/.letta/skills/canonical-people-lookup/SKILL.md`
- Future canonical writes pattern
  → `~/.letta/skills/canonical-write/SKILL.md`

## Trade-offs

| Aspect | System memfs | Skill |
|---|---|---|
| Always in context | Yes | No — loads on demand |
| Per-turn token cost | Cost paid every turn forever | 0 unless invoked |
| Update propagation | Edit per-agent memfs | Edit once at global skills dir |
| Cross-agent sharing | Copy per agent | Single source |
| Discoverability | Agent scans system prompt | Description-matched at runtime |

The big win is **single source of truth + cross-agent sharing**.
Right now Calendar and Docs each have a copy of
canonical_reference_protocol.md and they've already drifted
(Calendar has the people-lookup recipe; Docs has the same recipe but
slightly different examples). Skill form makes that impossible.

## When to do this

After Tasks migration. The skill refactor is mechanical (read existing
memfs file, write SKILL.md with frontmatter+description, replace memfs
file content with a 3-line pointer). Doing it once all the migrations
are complete means we touch each agent's memfs once for the cleanup,
not every migration cycle.

## Recipe (for when we do it)

```bash
# 1. Create skill dir
mkdir -p ~/.letta/skills/<name>

# 2. Move full content to SKILL.md with frontmatter:
cat > ~/.letta/skills/<name>/SKILL.md <<EOF
---
name: <name>
description: <triggers this skill loading — be specific about the task it solves>
---
<full content>
EOF

# 3. Replace per-agent memfs file with pointer:
cat > <agent-memfs>/system/<file>.md <<EOF
---
description: <one-line> — full recipe in skill: $name
---

See \`~/.letta/skills/<name>/SKILL.md\` for the full recipe.
EOF

# 4. Commit the per-agent memfs change + force recompile.
```

## Out of scope until decided

- Whether to put skills under `~/.letta/skills/` (current global location)
  vs a project-specific dir. Global works for single-machine; project
  dir would be better for sharing across hosts. Decide before
  refactoring.
- Whether to git-track `~/.letta/skills/` so changes are versioned and
  can be shared. Currently it's outside any git repo. Worth tracking.
