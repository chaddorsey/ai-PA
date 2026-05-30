---
title: Fleet alignment — memfs + canonical/shared memory + tool surface
date: 2026-05-28
status: open
context: After the 2026-05-27/28 push that added system/important_people.md
  pointers + canonical-lookup prompt blocks to all 6 fleet agents and shipped
  /clear for slackbot. This captures the remaining alignment work surfaced
  during that session, tagged for local-mode-transition relevance.
local_mode_plan: docs/plans/2026-05-25-letta-code-local-mode-investigation.md
local_mode_runbook: docs/runbooks/letta-local-mode-per-agent-migration.md
related_followups:
  - docs/followups/2026-04-28-user-info-canonical-migration.md
  - docs/followups/2026-04-29-pa-web-stability-todos.md
  - docs/followups/2026-04-28-signals-roadmap.md
  - docs/followups/post-cycle1-task-record-comprehensive.md
  - docs/followups/task-pipeline-improvements.md
---

# Fleet alignment status — what's still open

This is the durable list of fleet-alignment work pulled together
2026-05-28 after the canonical-pointer push. Each item is tagged for
its **local-mode-transition relevance**:

- 🔴 **BLOCKS-LOCAL-MODE** — must be cleaned up before migrating an
  agent to local mode, or the agent will be broken / wasteful in
  local mode
- 🟡 **RECOMMENDED-PRE-LOCAL** — strongly preferable to clean before
  local mode, but agent will function without it
- ⚪ **NICE-TO-HAVE** — alignment work, no local-mode dependency

## Shipped 2026-05-27/28 (for context)

- All 6 fleet agents have `system/important_people.md` pointer file
- All 6 prompts have `<people_resolution>` canonical-lookup block
- Calendar-agent's full prompt rewritten (real tools, no-placeholders, always-include-user)
- Calendar-agent's stale prompt tools (`get_calendar_events`, `find_my_availability`, `lookup_staff`) replaced with documented Bash+gws+jq workflow
- `jq` added to pa-web-ui Dockerfile (was missing — agent Bash commands needed it)
- Slackbot `/clear` slash command shipped per Letta semantics

---

## Open work, by tier

### Tier 1 — memfs / canonical (narrow scope)

#### A. 🔴 User info / preferences canonical migration
**Plan exists, not yet executed.** See
[docs/followups/2026-04-28-user-info-canonical-migration.md](2026-04-28-user-info-canonical-migration.md).

User info scattered across 5 buckets today: Letta identities (deprecated
upstream), per-agent `preferences_*` blocks, MC's `important_people`,
scheduler service settings, hardcoded `cdorsey@concord.org` in code.

**Why it blocks local mode**: per-agent `preferences_*.md` files are
pinned into context. Calendar-agent has **5 of them** for what's
probably 2 distinct people (`preferences_U02V91KU8` Slack-keyed for Chad,
`preferences_identity-4b355b96-...` Letta-identity-keyed for Chad —
duplicate). Same person stored 2× or 3× under different key schemes.
In local mode these get pinned to the LLM context every turn, wasting
tokens and risking inconsistent prefs. Some files reference deprecated
Letta identity IDs that may not exist post-migration.

Required before local mode: consolidate to canonical
`agents-canonical/reference/people/<person>.md` as source of truth;
collapse per-agent `preferences_*` into a single pointer or thin overlay.

**Worst offender**: calendar-agent_copy (5 duplicate prefs files).

---

#### B. ⚪ Other canonical pointer files (orgs, projects, monitoring)
Today only `important_people.md` is set up per-agent. Likely additions:

- `system/organizations.md` → `agents-canonical/reference/organizations/` (17 orgs already curated)
- `system/monitoring_priorities.md` — MC has this implicitly; others would benefit (esp. pulse-agent for slack vibe checks)
- `system/projects.md` — if/when canonical project files exist (not yet — `reference/projects/` does not exist)

Not blocking. Pattern is identical to people-pointer rollout.

---

#### C. 🔴 Per-agent `system/` standardization + cleanup
Significant drift across fleet:

| Agent | `system/` files | Notes |
|---|---|---|
| MC | 10 | Uses "protocol" framing |
| Tasks | 9 | Reasonable |
| Calendar | 13 | **5 stale `preferences_*` duplicates (see A)** |
| Pulse | **33** | **🔴 12+ `daily_vibe_check_*.md` files pinned in-context — should live in `digest/`** |
| Docs | 6 | Sparse |
| Email | 5 | Sparse |

**Why pulse's 33 blocks local mode**: every `system/*` file is pinned
in-context on every turn. Pulse-agent's accumulated daily_vibe_check
files are working notes that don't need to be pinned. In Letta-server
mode they're tolerable; in local mode they bloat every LLM call.

Required before local mode for pulse: move `daily_vibe_check_*` and
`coordination_gathered_*` files to `digest/` (or `working/`) so they're
read-on-demand instead of pinned.

Calendar's stale preferences are covered by item A.

---

#### D. ⚪ Canonical-seed curation completeness
Danielle Kehoe was canonical (`dkehoe.md`). Others may not be. Worth a
one-shot pass scanning recent calendar attendees + email senders to
surface gaps. Runbook exists: `docs/runbooks/canonical-seed-curation.md`.

Not blocking — bad lookups just reproduce bugs we already mitigated.

---

### Tier 2 — shared-memory infrastructure

#### E. ⚪ Signals roadmap Phase 1.3+
[docs/followups/2026-04-28-signals-roadmap.md](2026-04-28-signals-roadmap.md)
lists Phase 1.3 (heartbeat refresh) and beyond. Currently only
schedule-signals fire daily. Other agents could emit canonical signals
but aren't.

Not blocking — signal emission works via `signal` CLI in either mode.

---

#### F. ⚪ Comprehensive task-record process changes
[docs/followups/post-cycle1-task-record-comprehensive.md](post-cycle1-task-record-comprehensive.md) —
schema landed, process-side deferred.

Not blocking.

---

#### G. 🟡 Slackbot routing pattern (MC → calendar dispatch)
Slackbot DM default-routes to calendar-agent directly today. Per the
2026-05-25 agent audit, intended design is **MC orchestrates →
dispatches to calendar-agent for scheduling**. Today slackbot bypasses
MC entirely.

**Why it's pre-local recommended**: in local mode each agent has its own
letta-code subprocess. If slackbot is going to switch between agents on
intent, the dispatch logic should live in MC (one consistent place),
not in slackbot's keyword detector. Otherwise slackbot becomes its own
mini-orchestrator competing with MC.

Not technically blocking — slackbot can keep its current direct route
and we revisit later. But every day this stays, MC's role weakens.

---

### Tier 3 — tooling alignment

#### H. 🔴 Tool inventory audit per agent (stale Letta-server tools)
Tool counts: MC=27, tasks=18, calendar=4, pulse=36, docs=31, email=15.

**Why it blocks local mode**: Letta-server-attached tools execute on
the Letta server. In local mode, the agent runs entirely in
letta-code subprocess. Server-attached tools may need:
- Replacement by a CLI/skill the subprocess can call via Bash, OR
- Re-implementation as a letta-code skill, OR
- Re-attachment to the local-mode agent via the new mechanism

Pulse and docs have 30+ tools — likely many are stale and won't survive
the transition. Each agent needs a "tools-to-CLIs" audit before flipping
to local mode.

**Already partially addressed**: `emit_canonical_signal` → `signal` CLI
(shipped). `scheduler-mcp` tools → `scheduler` CLI (shipped). gmail-watch
tools → `gmail-watch` CLI (shipped). `generate_daily_briefing` →
`daily-briefing.py` (shipped).

**Still need CLI/skill replacements**:
- `orchestrate_scheduling` (calendar) — needs `run_orchestrate` or
  similar; today it's a Python function calling the Python orchestrator
  service over HTTP. Could become a thin CLI.
- `run_atlassian` (pulse, MC) — listed in earlier work; broken today
- `run_calendly` (calendar) — W5 reconstitution; Playwright-based
- `run_granola` (docs) — needed for docs-and-transcripts
- Drive RAG tools (docs) — `run_drive_rag` or `drive-rag-curl`
- Various analytics tools attached to pulse — need audit

See [docs/plans/2026-05-25-letta-code-local-mode-investigation.md](../plans/2026-05-25-letta-code-local-mode-investigation.md) W16 section
for the full Tier 1/2/3 list.

---

#### I-sexies. ✅ letta-code security-preamble false-refusal — RESOLVED 2026-05-29
Surfaced 2026-05-29 when MC (on `gpt-5.4 (oauth)` Codex Responses) began
refusing benign personal-assistant work — Google Doc editing, bibliography
analysis — citing *"the current higher-priority config still restricts
me to defensive security tasks only."*

**Root cause**: letta-code's bundled system prompt includes a default
preamble inherited from Claude Code:

> *"IMPORTANT: Assist with authorized security testing, defensive
> security, CTF challenges, and educational contexts. Refuse requests
> for destructive techniques..."*

Other providers (kimi, gpt-5.4 API, gpt-4.1, claude) treated this as
contextual hint. ChatGPT's Codex Responses endpoint interprets it as
hard scope restriction.

**Fix shipped**: `letta-memfs-patches/patches/apply_letta_code_neutralize_security_preamble.py`
— replaces both bundle occurrences with a benign personal-assistant
context line. Wired into `letta-code-patched/build.sh` and
`pa-web-ui/Dockerfile`. Idempotent via `PATCH-NEUTRALIZE-SECURITY`
marker. Joins the existing three bundle patches (PATCH-3205,
PATCH-EMPTY-APPROVALS, PATCH-MEMFS-GIT).

**Generalization for local mode**: letta-code's bundled system prompt
contains other preambles that may interact poorly with future
provider/model combinations. Worth a once-over of the bundle's
preambles before flipping to local mode — the same problem could
surface differently with a different provider mix.

---

#### I-quinquies. 🟡 pa-web approval UI is missing
Surfaced 2026-05-29 during the SPARK Glasses bibliography build.
letta-code's `UpdatePlan` (and certain Skill/planning tool calls)
reach `requires_approval` stop reason that the subprocess does NOT
internally auto-approve. pa-web has no UI to show / accept these.
Options today are binary:

- **Auto-approve everything** (responder enabled — current state as
  of 2026-05-29) — works but produces occasional false-positive
  "stranded" log events when the responder races letta-code's own
  approval path
- **Approve via Letta API** — works but runs against Letta-server's
  tool list (Bash et al. unavailable), so the approved tool fails
- **Wait forever** — what happens when responder is disabled and
  no API approval is sent

**Proper fix**: real approval-card UI in pa-web. Render
`approval_request_message` events as cards with Approve / Deny
buttons; on click, POST `ApprovalCreate` to Letta. Auto-approver
becomes belt-and-suspenders for un-interactive contexts (cron, etc.)
instead of the only UX path.

Files:
- `pa-web-ui/static/js/chat.js` — needs approval-card render path
- `pa-web-ui/templates/index.html` — approval card markup
- `pa-web-ui/static/css/styles.css` — styling
- `pa-web-ui/subprocess_pool.py` — once UI exists, narrow the
  auto-approver to non-INTERACTIVE non-Plan tools only

Pre-local relevance: same as I-bis (Stop reliability) — local mode
makes every wedged subprocess a real running process. Proper
approval UI matters more not less. Worth fixing before migration.

---

#### I-bis. 🟡 Stop button reliability (pa-web-ui)
Surfaced 2026-05-28 mid-session when a Stop click failed to cancel an
MC run and required manual `os.kill()` from inside the container.

Two compounding bugs:

1. **Cancel mishandles the `default` pseudo-conv-id.** The frontend
   posts `POST /api/conversations/default/cancel`; pa-web-ui forwards
   to Letta as `POST /v1/conversations/default/cancel` which 404s
   (because `default` is pa-web-ui's local pseudo-id for the registry
   slot, not a real Letta conversation). The cancel silently no-ops.
   Fix: translate `default` to the actual subprocess termination —
   SIGTERM the subprocess + evict the registry handle, NOT a Letta
   API call.
2. **Race between Stop and next message.** Even when cancel reaches
   the subprocess, a new POST /stream within ~2s spawns a fresh
   subprocess that holds the turn lock. Subsequent messages get 409.
   Fix: registry should mark the conv_id as "draining" for a short
   window after cancel, rejecting new spawns until the drain settles.

Why 🟡 (recommended pre-local): in local mode every wedged
subprocess is a real running process holding compute. Reliable Stop
becomes more important, not less. Worth fixing before migration but
not strictly blocking.

Files to touch:
- `pa-web-ui/app.py` — cancel handler for `default`
- `pa-web-ui/subprocess_pool.py` — drain window / handle eviction
- `pa-web-ui/static/js/chat.js` — clear `_currentStreamAbort` and
  `inFlightRequests` on Stop so the client can send next msg

---

#### I-quater. 🔴 Migrate operational knowledge out of archival memory
Surfaced 2026-05-29 while bringing MC back up to speed on the SPARK
Glasses notebook-syncing workflow. MC's archival memory holds two
passages from 2026-03-27 that are the *only* authoritative record of
the recordkeeping rules — `SPARK Glasses Sources cross-registry`
structure and `NotebookLM local recordkeeping rules`. Archival is the
wrong layer for that kind of durable operational protocol.

**Why archival is the wrong layer for workflow rules:**

- **Non-deterministic recall.** Search hits depend on embedding
  similarity, not authority. The rules can fall out of MC's working
  context for whole conversations.
- **No source of truth.** Two passages on the same topic with subtly
  different wording can both surface; agent has no way to know which
  is current.
- **No edit / versioning.** Updates require writing a new passage and
  hoping search ranking favors it. Old advice keeps surfacing.
- **No agent visibility.** The agent doesn't *know* what's in
  archival until it searches. Pinned `system/` files are visible
  every turn.

**Migration target:** the canonical/memfs pattern we've been building:
- **Pinned operational rules** → per-agent `system/<workflow>_protocol.md`
- **Cross-agent canonical references** → `agents-canonical/reference/<topic>/`
- **Read-on-demand context** → `reference/` in agent memfs, indexed by
  pointer files
- **Ephemeral session state** → `digest/` (not pinned)

Archival stays in scope for **conversation-history recall** (its
original purpose: "what did we discuss 3 months ago"), not for
operational protocols, workflow rules, or canonical references.

**Workflows known to currently rely on archival for operational knowledge
(needs surfacing during the migration pass):**

| Workflow | What lives in archival | Migration target |
|---|---|---|
| SPARK Glasses notebook sync | recordkeeping rules + `refs/` structure | MC `system/spark_glasses_workflow.md` |
| NotebookLM local registry | `notebooks.json` / `source-map.jsonl` / `query-log.jsonl` conventions | MC `system/nlm_protocol.md` (partial — already exists; needs the recordkeeping rules added) |
| **(unknown others)** | likely several more workflow protocols from the memory-block era | requires an audit pass: `archival_memory --search` for passages tagged `protocol`, `rule`, `convention`, `workflow` |

**Why this blocks local mode:** in local mode each agent runs as a
letta-code subprocess on the host. Archival API access still works,
but the architectural goal is to have **all operational knowledge
locatable in the memfs file tree** (`system/`, `reference/`, `skills/`)
so the agent's behavior is determined by inspectable files, not by
ephemeral vector hits. Agents migrated to local mode without first
moving their operational protocols out of archival will silently
drift in capability between sessions.

**Audit + migration plan** (rough):
1. For each fleet agent, run a tagged search across archival for
   protocol/workflow/rule passages.
2. Classify each: is this an operational protocol (migrate to
   memfs) or a conversation/decision record (leave in archival)?
3. For each migrated protocol, write a memfs file (`system/` if
   pinned-rule, `reference/` if read-on-demand).
4. Note migration completion in the passage itself (so the search
   result, if it still surfaces, says "this content moved to
   `system/foo.md` — consult that file").

**Estimated scope:** medium. Probably 20-40 distinct protocols across
all 6 agents based on how heavily archival was used during the
memory-block era (Q1 2026).

---

#### I-ter. ✅ drive-rag-service `/v1/ingest/{file_id}` returns 500 on re-ingest — RESOLVED 2026-05-28
Surfaced 2026-05-28 when MC tried to follow the snapshot-on-command
pattern for an actively-edited doc. **Fixed same session.**

**Symptom**: `POST /v1/ingest/{file_id}` returns 500 Internal Server
Error for any doc where most chunks haven't changed.

**Root cause**: `src/drive_rag/ingestion.py:438` calls
`database.upsert_chunks(...)`, but the underlying PostgREST POST to
`http://supabase-rest:3000/document_chunks` is not using
`Prefer: resolution=merge-duplicates` (or equivalent `ON CONFLICT`).
When re-ingesting, unchanged chunks have identical hashes, so the
INSERT trips the `unique_chunk` constraint and the whole call fails.

**Service log**:
```
duplicate key value violates unique constraint "unique_chunk"
Key (drive_file_id, chunk_id)=(<id>, <hash>) already exists.
```

**Fix applied**: added `?on_conflict=drive_file_id,chunk_id` query
param to the PostgREST upsert calls. The `Prefer:
resolution=merge-duplicates` header was already present, but PostgREST
defaults the conflict target to the table's PK; for tables where the
uniqueness lives on a separate UNIQUE constraint, the conflict target
must be passed explicitly. Same fix applied to two other upsert sites
that had the same shape:
- `upsert_chunks` → `on_conflict=drive_file_id,chunk_id`
- `upsert_document_revision` → `on_conflict=drive_file_id,revision_id`
- `upsert_snapshot_metadata` → `on_conflict=drive_file_id,revision_id`

Service rebuilt + verified: all three previously-failing file_ids
return 200 OK; staleness poll runs clean with no 409s.

**Also surfaced**: response schema field is `similarity` (not
`score`). MC's protocol now pins this explicitly with sample jq
projections.

Why 🟡 (recommended pre-local): the snapshot-on-command pattern is
the right model for RAG over actively-edited docs. With it broken,
MC falls back to "just read via gws", which is fine for single-doc
reads but blocks any semantic-search-the-latest-version workflow.

Files to touch:
- `drive-rag-service/src/drive_rag/ingestion.py` line 438 area
- Verify any other PostgREST POST that should be an upsert

---

#### I. ⚪ Model alignment per agent
- MC: kimi-k2p6
- Tasks: gpt-5.2
- Calendar: gpt-5.4-nano
- Pulse: gpt-5.4-nano
- Docs: gpt-4.1-mini (legacy — drift?)
- Email: gpt-5.4-nano

Docs on gpt-4.1-mini is drift. Worth deciding whether per-agent models
is intentional. In local mode each agent has independent litellm
routing so heterogeneity is fine, but explicit choice beats accidental
drift.

Not blocking.

---

### Tier 4 — ops + small wins

#### J. ⚪ `/new` as alias of `/clear`
Letta docs reference both. 1-line addition to register the callback
twice. Trivial.

#### K. ⚪ Slack manifest deployment automation
Today: edit `slackbot/manifest.json`, manually paste into Slack admin
UI. ~30 min to script with `slack manifest update`.

#### L. ⚪ Followup queue housekeeping
[docs/followups/2026-04-29-pa-web-stability-todos.md](2026-04-29-pa-web-stability-todos.md)
is a living document. Worth a pass to mark what's done vs. open after
recent work.

---

## TL;DR — blocking-for-local-mode subset

Three items must be addressed before flipping each agent to local mode:

| # | Item | Severity | Agents affected |
|---|---|---|---|
| **A** | preferences_* duplicates → canonical | 🔴 | Calendar (worst, 5 duplicates); others have 0-2 |
| **C** | pulse-agent's bloated system/ folder | 🔴 | Pulse only (12+ digest files in system/) |
| **H** | tool inventory audit + CLI replacements | 🔴 | All 6 (varies by agent; calendar is lightest, pulse + docs heaviest) |
| **I-quater** | Migrate operational knowledge out of archival memory | 🔴 | All 6; MC heaviest (Q1 2026 memory-block-era passages) |

**Per-agent local-mode readiness** (best to worst, depending on the
items above):

| Agent | Ready? | Gating items |
|---|---|---|
| MC | Closest to ready by tool-coverage | H partial (most CLIs shipped) |
| Calendar | Needs A + H + G | 5 prefs files + orchestrate_scheduling CLI + slackbot routing |
| Tasks | Needs H | Many tools likely stale |
| Email | Needs H | 15 tools, audit needed |
| Docs | Needs H | 31 tools + drive-rag + granola CLIs |
| Pulse | Needs C + H | 33 system files + 36 tools |

### Revised migration order (2026-05-29 update)

**Docs → Calendar → Tasks → Email → Pulse → MC**

(Earlier note suggested MC first based on tool-coverage. That
under-weighted user-impact risk; MC is the agent the user interacts
with most, and its dispatch role means a regression breaks the user's
primary access to the fleet.)

Reasoning:

- **Docs first (pilot)**: lowest active traffic (last meaningful
  update 2026-05-13), failure gracefully falls back to MC handling
  doc queries directly, builds the migration recipe on a finite
  known tool surface before touching user-facing agents.
- **Calendar second**: smallest absolute tool count (4), heavily
  exercised during 2026-05-29 hardening so currently in best-ever
  state; needs `orchestrate_scheduling` CLI + slackbot routing
  decision (item G) in same window.
- **Tasks, Email, Pulse** in middle: progressive complexity, each
  uses the prior recipe with one new domain wrinkle.
- **MC last**: by the time MC migrates, the recipe is proven on
  five other agents; MC's tool diversity benefits from
  battle-tested-elsewhere debugging; user-visible regression risk
  minimized.

### Hedge strategies (apply to any agent, especially MC)

1. **Pre-migration checkpoint** — snapshot memfs git head, archival
   passages, tool attachments, conversation list. Tagged in Letta +
   Gitea + memory entry so rollback is scripted.

2. **Parallel-run window** — pa-web spawns either local subprocess
   OR server-side fallback for some days. Compare outputs on the
   same prompts before decommissioning.

3. **Tool-by-tool pre-build** — most tool migration can complete
   BEFORE the agent's migration window: build + test each
   replacement CLI against the existing server-side agent first.
   When the migration window opens, only the agent-level memfs +
   model + tool-binding flip is in scope. This makes each agent's
   migration window short (hours, not days).

4. **Migration-eve freeze** — 24h before each agent's migration, no
   other fleet changes (no protocol edits, no canonical writes, no
   Gitea config changes). Clean baseline.

5. **First-week safety net** — keep the previous (server-side) agent
   version selectable via pa-web picker for 1 week after the
   local-mode flip. If anything regresses, switch back without
   losing state.

### Implications for ordering items A, C, H, I-quater

These are *largely parallelizable with* the per-agent migration
sequence, not strictly upstream:

- **Item H (tool CLIs)**: builds proceed CONTINUOUSLY in parallel
  with the migration sequence. Each agent's migration window only
  needs the CLIs *that agent's* tool list depends on.
- **Item A (preferences canonical)**: per-agent; tackled in the
  same window as that agent's migration.
- **Item C (pulse system/ bloat)**: pulse-specific; tackled in
  pulse's window only.
- **Item I-quater (archival → memfs)**: per-agent audit; same window
  as that agent's migration.

## Recommended-but-not-blocking subset

| Item | Notes |
|---|---|
| **G** Slackbot routing pattern | Better to fix before local mode, but slackbot can keep direct route during transition |

## Nice-to-have subset (defer)

B, D, E, F, I, J, K, L — none gate local mode. Address opportunistically.
