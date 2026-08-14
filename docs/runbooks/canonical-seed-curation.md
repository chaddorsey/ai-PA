# Canonical Seed Curation — Unit 11a Checklist

The seed-canonical-from-blocks.py script lifts content from existing
production memory blocks into a structurally-canonical staging
directory. **Before** that content becomes the initial commit on
`agents-canonical.git`, it must be human-reviewed.

## Why curation is required

Production blocks have accumulated content over months:
- Outdated entries (people who've left, roles that changed)
- Agent-specific scratchpad notes (not real canonical knowledge)
- Contradictory entries from different agent perspectives
- Dead-channel references (Slack channels retired, doc URLs moved)
- Stale instructions in playbooks (e.g., "escalate to channel X" when X
  no longer exists)

If we lift the raw block content as-is, every migrated agent reads it as
authoritative truth. Curation is the gate.

## Workflow

1. Run the seed staging script:

       python3 scripts/memfs-helpers/seed-canonical-from-blocks.py

2. Review each file in `/tmp/agents-canonical-seed/`:
   - `people/*.md` — one person per file. Check each for accuracy.
   - `priorities/*.md` — quarterly/period priorities. Check current
     period is right; consider archiving old periods rather than
     committing them.
   - `playbooks/*.md` — playbooks (currently `task-extraction.md`).
     Hardest one to curate; this is procedural knowledge with the most
     drift risk.
3. Use the checklist below for each file.
4. When satisfied, save your edits (mtime updates automatically).
   Optionally `touch /tmp/agents-canonical-seed/.curated` to mark the
   tree as ready even without per-file edits.
5. Run the commit script:

       scripts/memfs-helpers/commit-canonical-seed.sh

   It refuses to push if no curation evidence is found.

## Per-file checklist

For every file in the staging directory, ask:

- [ ] **Frontmatter `description`** is one accurate sentence — this
  surfaces into the agent's prompt on read; sloppy descriptions become
  noise.
- [ ] **Names / roles / titles** are current as of today.
- [ ] **No agent-specific scratchpad** — content reads as canonical
  truth, not "tasks-agent thinks X."
- [ ] **No contradictions** — if the source had two different versions
  of a fact, decide which is right.
- [ ] **No dead references** — Slack channels, URLs, agent_ids, etc.
  all point at things that still exist.
- [ ] **Playbooks**: instructions match current tool inventory.
  Reference to `add_extracted_tasks` as a v1 tool is now wrong (it's
  detached per cycle-1 Unit 10). Rewrite to the new flow:
  `add_extracted_tasks_postgres` post-migration; pa-web-ui sidebar for
  user-driven CRUD pre-migration.
- [ ] **One logical unit per file** — if a file holds multiple distinct
  concerns, split into separate files.
- [ ] **Filename** is lowercase-hyphenated (LET-8217 transition
  discipline; commit script enforces).

## Special considerations for each section

### `people/`

- The seed splits the original block on `## Heading` lines or blank
  lines. Some people may end up merged or split incorrectly — fix.
- For each person, capture:
  - Role / org (current)
  - Relationship to user
  - Recent context (cycle-1 acceptable; can prune later)
- Drop anyone the user no longer regularly works with — this is
  canonical, not historical.

### `priorities/`

- Cycle-1 expectation: ONE current period file (e.g., `2026-q2.md`).
  Older periods should NOT be committed — they belong in archive, not
  canonical truth.
- If the seed produced multiple files, decide which is current; delete
  the rest.

### `playbooks/task-extraction.md`

- This is procedural knowledge that's now partially stale because of
  the cycle-1 cutover (legacy tools detached).
- Rewrite the "how to write a task" section to point at the new
  Postgres-backed tools (post-migration) or the sidebar (pre-migration).
- Remove references to v1 block PATCH semantics.
- Keep the high-level extraction heuristics (when to capture, what
  metadata to include, etc) — those are still valid.

## After commit

The repo is live at `http://127.0.0.1:3030/agents/agents-canonical`.

Migrated agents pull it via the canonical-store skill (Unit 18 / cycle-2
work). Future updates flow through the reflection inbox →
steward-review path (cycle 2).
