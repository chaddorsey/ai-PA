# Plan: Letta Code Migration Assessment

## Context

The PA ecosystem runs ~20 Letta agents on a self-hosted Docker server with 75+ custom Python tools, 6 MCP servers, and 48+ backing services. Letta is shifting development focus from standard agents to "Letta Code" agents, which use client-side tool execution (bash/skills) instead of server-side Python sandbox tools. This plan assesses what a migration would involve, what would change, and what the realistic path forward looks like.

## The Core Architectural Shift

| Dimension | Standard Letta (Current) | Letta Code |
|-----------|------------------------|------------|
| Tool execution | Server-side Python sandbox (inside Docker) | Client-side bash/skills (on host machine) |
| Tool format | Python functions with typed schemas | Bash scripts + SKILL.md files |
| Memory model | Memory Blocks (server-side) | MemFS (git-backed) — **NOT available on Docker**, falls back to Memory Blocks |
| Skills system | Not available | First-class feature (.skills/ directories) |
| Subagents | Custom multi-agent wiring | Built-in (7 types: explore, plan, memory, etc.) |
| SDK | Python (`letta_client`) | TypeScript only (`@letta-ai/letta-code-sdk`) |
| Invocation | REST API from any language | CLI session or TypeScript SDK |
| Underlying server | Letta server | Same Letta server (same agent IDs, memory, archival) |

**The good news**: Letta Code points at the same Letta server. Agent memory, archival memory, and conversation history carry over unchanged. Migration is non-destructive — `letta --agent <existing-id>` resumes any existing agent.

**The fundamental tension**: The PA ecosystem is a headless, programmatically-invoked system (slackbot, scheduler, n8n send messages to agents). Letta Code is designed for interactive terminal use with a human approving tool execution.

---

## Critical Blocker: Programmatic Invocation

Five services currently invoke Letta agents programmatically:

| Service | How It Calls Letta | Impact |
|---------|-------------------|--------|
| **slackbot** | `POST /v1/agents/{id}/messages` (Python requests) | REST API unchanged — continues working |
| **scheduler-service** | `POST /v1/agents/{id}/messages` (HTTP action) | Same |
| **pa-routing-handler** | `POST /v1/agents/{id}/messages` (Python) | Same |
| **n8n** | HTTP Request nodes to Letta REST API | Same |
| **pa-web-ui** | Via pa-routing-handler | Same |

**The problem**: These services call the Letta REST API directly. When an agent has standard Python tools, the server executes them in its sandbox. When an agent has Letta Code skills, a Letta Code client process must be running and connected to handle skill execution. If no client is connected, skill calls fail.

**Implication**: Any agent that receives messages from slackbot, scheduler, or n8n **cannot rely solely on Letta Code skills** for its tools. It must either keep standard server-side tools or have a persistent Letta Code daemon process running (which is unconfirmed as a supported pattern).

---

## Tool Migration Analysis

### Tier 1: Direct Skill Conversion (Easy — 15 tools)

These are CLI wrappers or simple HTTP calls. They translate directly to bash skills.

| Tool | Current Pattern | Skill Pattern |
|------|----------------|---------------|
| `run_gws` | `subprocess.run(["gws", ...])` | `gws $command --params "$params"` |
| `fetch_gmail_messages` | Multiple gws subprocess calls | Same, looped in bash |
| `run_omnifocus` | `subprocess.run(["omnifocus-cli", ...])` | `omnifocus-cli $command` |
| `check_current_time` | `datetime.now()` | `date` command |
| `post_slack_channel_reply` | `urllib` to Slack API | `curl -H "Authorization: Bearer $TOKEN" ...` |
| `send_slack_dm` | `urllib` to Slack API | Same curl pattern |
| `get_slack_channels/messages/users` | `urllib` to Slack API | curl |
| `search_slack_messages` | `urllib` to Slack API | curl |
| `watch/unwatch_gmail_thread` | HTTP to gmail-watch-service | curl to localhost port |
| `search_documents` | HTTP to drive-rag-service | curl to localhost port |

**Caveat**: Both CLIs are currently Docker-only and must be installed on the host (see Phase 0 step 2). omnifocus-cli's `bridge.py` auto-detects macOS and uses direct osascript — no HTTP bridge needed when running locally. Port mappings for other services change from Docker-internal names to localhost:PORT.

**Skills**: gws ships 89 pre-built SKILL.md files (OpenClaw format) — no custom skills needed. omnifocus-cli and slack-cli need custom SKILL.md files authored to match the same format.

### Tier 2: HTTP Service Calls via curl (Medium — 10 tools)

These call internal Docker services and can be curl skills, but lose Python response formatting/pagination.

| Tool | Target Service | Conversion Notes |
|------|---------------|-----------------|
| `delegate_to_specialist` | pa-routing-handler:5201 | curl + jq for response parsing |
| `coordinate_task` | pa-routing-handler:5201 | Same |
| `trigger_slack_analytics_export` | Playwright automation | Needs wrapper service endpoint |
| `list_recent_slack_files` | Slack API | curl |
| `lookup_staff` | Letta identities API | curl to localhost:8283 |
| `find_user_blocks` | Letta blocks API | curl to localhost:8283 |
| `recall_activity` | Letta archival search API | curl + jq |

### Tier 3: Keep as Server-Side Tools (Hard — 25+ tools)

These have complex Python logic (100-1000+ LOC), Letta API interactions with read-modify-write patterns, or Python library dependencies. Converting to bash would be fragile, lossy, or impractical.

**Complex business logic (should become HTTP microservice endpoints):**
| Tool | LOC | Why Not Bash |
|------|-----|-------------|
| `orchestrate_scheduling` | 1000+ | ASP solver (clingo), DSPy NLP, constraint optimization |
| `get_email_analytics` | 300+ | SHA-256 hashing with daily rotation, quartile analysis, staff roster |
| `collect_daily_workspace_activity` | 400+ | Multi-page API aggregation, top-N computation, trend detection |
| `compose_daily_briefing` | 500+ | Supabase reads, 7/28-day trend windows, formatted output |
| `compose_gmail` | 150+ | RFC-compliant MIME construction, threading headers |
| `draft_reply_to_email` | 200+ | MIME + threading + gws subprocess |
| `search_meetings_smart` | 200+ | Meeting search + ranking logic |
| `find_my_availability` | 200+ | Calendar analysis + slot ranking |

**Letta API manipulation (concurrent-safe block operations):**
| Tool | Why Not Bash |
|------|-------------|
| `add_extracted_tasks` | Deterministic ref IDs, atomic block updates, structured archival passages |
| `update/transition/merge_extracted_task` | Regex parsing of archival passages, concurrent-safe updates |
| `process_email_task_queue` | Multi-step: read block → fetch Gmail → extract tasks → update block |
| `process_drive_task_queue` | Multi-step: read block → fetch Drive docs → extract context → update block |
| `update_tasks_section` | Section-based regex replacement in memory blocks |
| `sync_omnifocus_completions` | Archival search + omnifocus-cli + archival update |
| `prepare_completion_feedback` | Source routing (Docs/Slack/Email), context fetching |
| `prepare_meeting_followup` | HTML template, MIME, label management |

### Tier 4: Memory Block Readers (Trivial but pointless to convert — 8 tools)

These read memory blocks and return JSON instructions. They work identically in both models since memory blocks are server-side.

### Tier 5: MCP Server Tools (No migration needed — 6 servers)

MCP servers run on the Letta server regardless of tool execution model. They continue working unchanged.

| MCP Server | Status | Tools Provided |
|-----------|--------|---------------|
| slack-tools | Active | Slack read/write |
| scheduler-tools | Active | Job CRUD |
| calendly-tools | Active | Availability checking |
| granola-tools | Active | Meeting queries |
| graphiti-tools | Stopped | Knowledge graph |
| rag-tools | Stopped | Vector search |

---

## Multi-Agent Architecture

### Current Model
- 5+ specialist agents (calendar, email, tasks, docs, pulse), each with its own memory, archival, and tool set
- `delegate_to_specialist` routes from main agent to specialists via pa-routing-handler
- Specialists have persistent identity and learned context

### Letta Code Subagents
- 7 built-in types (explore, general-purpose, plan, memory, etc.)
- Ephemeral — no persistent memory or specialized tool sets
- Share parent context, not their own

**Assessment**: The current multi-agent architecture **cannot be replicated** with Letta Code subagents. Each specialist agent's persistent memory, archival history, and specialized tools are core to the system. The multi-agent routing (via REST API) works regardless of agent type, so this model should be preserved.

---

## Recommended Strategy: Hybrid Architecture

### What This Means

Rather than a full migration, run Letta Code alongside the existing standard agent ecosystem:

1. **Existing agents keep their standard Python tools** — slackbot, scheduler, n8n continue to invoke them via REST API with server-side tool execution
2. **A new Letta Code companion agent** provides interactive terminal access with skills for ad-hoc queries, debugging, and tasks that benefit from bash/file access
3. **Complex tools gradually become HTTP microservices** — callable from either standard tools (via urllib) or Letta Code skills (via curl), making the architecture more modular regardless of Letta Code

### Phase 0: Prerequisites & Validation (1-2 weeks)

1. Install Letta Code CLI on the host: `npm install -g @letta-ai/letta-code`
2. **Install CLIs on host** (currently Docker-only):
   - **gws CLI**: Download Go binary or `brew install`. Credentials already on host at `~/.gws/credentials.json` (volume-mounted into Docker). No credential duplication needed — both Docker and host use the same OAuth tokens.
   - **omnifocus-cli**: `pip install ./omnifocus-cli` (the local Python package). `bridge.py` already has a direct `osascript` code path for macOS — when running on the host it calls `/usr/bin/osascript` directly, bypassing the HTTP bridge service entirely. Much simpler than the Docker path (which goes CLI → HTTP bridge → osascript).
   - **slack-cli** (planned): `pip install ./slack-cli` on host. Pure HTTP (Slack API) — works identically in Docker and on host. Needs `SLACK_BOT_TOKEN` env var.
   - **Note**: Existing Docker installations stay untouched. Standard Letta agents continue using their in-container CLIs. No rework to existing tools.
3. Verify connectivity: `LETTA_BASE_URL=http://localhost:8283 letta --new`
4. Verify memory blocks are accessible from Letta Code agent
5. **Critical test**: Determine if Letta Code can run as a persistent daemon for programmatic invocation

### Agent Skills: Pre-Built and Custom

The gws CLI ships with **89 SKILL.md files** in its repo (`skills/` directory), organized into three tiers:

| Tier | Example | Count | Description |
|------|---------|-------|-------------|
| **Service skills** | `gws-gmail`, `gws-calendar`, `gws-drive` | ~25 | One per Google API — commands, flags, discovery pointers |
| **Recipes** | `recipe-find-free-time`, `recipe-meeting-prep` | ~50 | Multi-step workflows combining services |
| **Personas** | `persona-exec-assistant`, `persona-project-manager` | ~10 | Role-based skill bundles |

Skills use [OpenClaw](https://github.com/anthropics/openclaw) format:
```yaml
---
name: gws-gmail-triage
version: 1.0.0
description: "Gmail: Show unread inbox summary (sender, subject, date)."
metadata:
  openclaw:
    category: "productivity"
    requires:
      bins: ["gws"]
    cliHelp: "gws gmail +triage --help"
---
```

A shared skill (`gws-shared`) provides auth, global flags, and security rules — referenced by all other skills via relative path.

**Key implication**: For gws, no custom SKILL.md files needed — copy the official ones into `.skills/`. For omnifocus-cli and slack-cli, author matching skills following the same OpenClaw format.

### Phase 1: Companion Agent (Week 2-3)

Create a fresh Letta Code agent (`letta --new`) with skills:

**Pre-built (from gws repo):**
- `.skills/gws-shared/` — Auth, global flags, security rules
- `.skills/gws-gmail/` — Gmail commands
- `.skills/gws-gmail-triage/` — Inbox summary helper
- `.skills/gws-gmail-send/` — Email composition
- `.skills/gws-calendar/` — Calendar commands
- `.skills/gws-drive/` — Drive commands
- Relevant recipes (e.g., `recipe-find-free-time`, `recipe-meeting-prep`)

**Custom (authored to match OpenClaw format):**
- `.skills/omnifocus-shared/` — Auth, global flags, CLI syntax
- `.skills/omnifocus-tasks/` — Task CRUD, inbox, review
- `.skills/omnifocus-search/` — Search and filtering
- `.skills/slack-shared/` — Auth, API patterns
- `.skills/slack-channels/` — Channel operations
- `.skills/slack-messages/` — Message read/write/search
- `.skills/slack-users/` — User lookups

Test interactively. Learn the patterns. No disruption to existing agents.

**Installing gws skills**: Clone or copy the entire `skills/` directory from the [gws repo](https://github.com/googleworkspace/cli/tree/main/skills) into the Letta Code agent's `.skills/` directory. This includes all 89 service skills, recipes, and personas. No custom authoring needed for gws.

### Recipe Architecture: Two-Tier System for Both Agent Types

Recipes are multi-step workflow templates (2-5 numbered steps of CLI commands). The gws repo ships 33 relevant recipes. Custom recipes will be authored for omnifocus-cli and slack-cli. All recipes should be available to **both** Letta Code agents (via `.skills/` SKILL.md files) and standard Letta agents (via memory).

**Tier 1 — Core memory block (index):** A single `workflow_recipes` block (~2500 chars) listing all recipes with one-line descriptions, organized by domain. Gives the agent enough context to recognize "this situation matches a recipe" and provides an unambiguous lookup key.

**Tier 2 — Archival memory (full recipes):** Each recipe stored as an archival passage with a deterministic ID prefix: `[RECIPE:namespace:name]`. The agent uses text substring search (`?search=RECIPE:gws:email-triage`) to retrieve exactly one passage.

**Core memory block format:**

```
## Workflow Recipes
Search archival memory for the recipe ID to load full steps.
Example: search for "RECIPE:gws:find-free-time"

### Scheduling & Calendar
- RECIPE:gws:find-free-time — Query free/busy across multiple people for a meeting slot
- RECIPE:gws:block-focus-time — Create recurring focus blocks to protect deep work
- RECIPE:gws:plan-weekly-schedule — Review week, identify gaps, add events
- RECIPE:gws:reschedule-meeting — Move event to new time, notify attendees
- RECIPE:gws:batch-invite — Add attendees to existing event
- RECIPE:gws:schedule-recurring — Create repeating event with attendees
- RECIPE:gws:create-events-from-sheet — Create calendar events from spreadsheet rows
- RECIPE:gws:share-event-materials — Share Drive files with all event attendees

### Email & Gmail
- RECIPE:gws:label-and-archive — Apply labels to matching messages, remove from inbox
- RECIPE:gws:draft-email-from-doc — Read Doc content, use as email body
- RECIPE:gws:email-drive-link — Share Drive file and email the link
- RECIPE:gws:save-email-attachments — Save attachments to Drive folder
- RECIPE:gws:save-email-to-doc — Copy email body into a Google Doc
- RECIPE:gws:forward-labeled — Forward messages with a specific label
- RECIPE:gws:create-gmail-filter — Auto-label/star/categorize incoming messages
- RECIPE:gws:vacation-responder — Enable/disable out-of-office auto-reply

### Drive & Files
- RECIPE:gws:find-large-files — Identify files consuming storage quota
- RECIPE:gws:organize-folder — Create folder structure, move files into place
- RECIPE:gws:share-doc-and-notify — Share doc with edit access, email collaborators
- RECIPE:gws:share-folder-with-team — Share folder and contents with collaborators
- RECIPE:gws:bulk-download-folder — Download all files from a folder
- RECIPE:gws:watch-drive-changes — Subscribe to file change notifications
- RECIPE:gws:create-shared-drive — Create Shared Drive, add members with roles

### Docs, Sheets & Slides
- RECIPE:gws:create-doc-from-template — Copy template, fill content, share
- RECIPE:gws:generate-report-from-sheet — Read sheet data, create formatted Doc report
- RECIPE:gws:backup-sheet-as-csv — Export sheet tab as CSV
- RECIPE:gws:collect-form-responses — Retrieve and review Google Form responses
- RECIPE:gws:compare-sheet-tabs — Diff two tabs to find differences
- RECIPE:gws:copy-sheet-for-new-month — Duplicate template tab for new month
- RECIPE:gws:create-expense-tracker — Set up expense tracking spreadsheet
- RECIPE:gws:create-feedback-form — Create Google Form, share via Gmail
- RECIPE:gws:create-presentation — Create slide deck with initial slides
- RECIPE:gws:sync-contacts-to-sheet — Export contacts to spreadsheet
```

**Archival passage format (one per recipe):**

```
[RECIPE:gws:find-free-time]
Find Free Time Across Calendars
CLIs: gws
Prereq skills: gws-calendar

Steps:
1. Query free/busy: gws calendar freebusy query --json '{"timeMin":"...","timeMax":"...","items":[{"id":"user1@example.com"},{"id":"user2@example.com"}]}'
2. Review output to find overlapping free slots
3. Create event in free slot: gws calendar +insert --summary 'Meeting' --attendees user1@example.com,user2@example.com --start '2026-03-08T14:00:00' --duration 30
```

**Agent instructions (add to persona/guidelines block):**

```
When you encounter a task that might match a workflow recipe, check the
workflow_recipes block first. If a recipe matches, search archival memory
for its full steps (e.g., search "RECIPE:gws:find-free-time") before
proceeding. Follow the recipe steps, adapting parameters to the current context.
```

**Why one block, not per-CLI:** The agent reasons about "what am I trying to do" not "which CLI do I need." Cross-service recipes don't belong to any single CLI. One block = one place to look, organized by domain/use-case.

**Suggested recipes for omnifocus-cli and slack-cli:** See [2026-03-08-cli-recipe-suggestions.md](2026-03-08-cli-recipe-suggestions.md) for proposals (not yet implemented).

### Phase 2: Extract Complex Tools to HTTP Services (Week 3-8)

This is valuable regardless of Letta Code — it makes tools callable from anywhere:

**New task-lifecycle-service (FastAPI, port TBD):**
- `POST /v1/tasks/add` — replaces `add_extracted_tasks`
- `PUT /v1/tasks/{ref_id}` — replaces `update_extracted_task`
- `POST /v1/tasks/{ref_id}/transition` — replaces `transition_extracted_task`
- `POST /v1/tasks/merge` — replaces `merge_extracted_tasks`

**New analytics-service (FastAPI, port TBD):**
- `POST /v1/analytics/email` — replaces `get_email_analytics`
- `POST /v1/analytics/briefing` — replaces `compose_daily_briefing`
- `POST /v1/analytics/snapshot` — replaces `collect_analytics_snapshot`

**Extend scheduling-orchestrator-api:**
- `POST /v1/availability` — replaces `find_my_availability`
- `POST /v1/evaluate` — replaces `evaluate_proposed_times`

### Phase 3: Evaluate Full Migration Feasibility (Week 8+)

Based on Phase 0-2 results:
- If daemon mode works → consider migrating primary agents
- If daemon mode doesn't work → permanent hybrid (most likely outcome)
- In either case, the HTTP service extraction makes the system more modular and resilient

---

## Trade-offs and Pitfalls

### What You Gain
- Letta Code's skills system (reusable, versionable SKILL.md files)
- Built-in subagent types for interactive work
- Bash access for ad-hoc tasks
- Access to future Letta Code features (MemFS when it ships to Docker, etc.)
- Position on the "future track" of Letta development

### What You Risk
- **TypeScript-only SDK**: Cannot drive Letta Code agents from Python (slackbot, scheduler)
- **No confirmed daemon mode**: Programmatic invocation may not work with Letta Code agents
- **Looser return schemas**: Skills echo JSON to stdout; agent parses loosely vs typed Python dicts
- **Two-system maintenance**: Both Python tools and bash skills if running hybrid
- **Host dependency management**: gws (Go binary) and omnifocus-cli (`pip install`) must be installed on host alongside Docker copies; two installations to keep in sync
- **Memory pressure**: Additional Node.js process on 24GB system

### Hard Blockers
1. **Programmatic invocation without daemon mode** — if Letta Code can't run persistently, agents called by slackbot/scheduler MUST keep standard tools
2. **MIME email composition in bash** — `compose_gmail` and `draft_reply_to_email` require Python; must remain server-side or become an HTTP endpoint
3. **ASP solver (clingo)** — scheduling orchestrator cannot be a bash skill; already has an HTTP API

### Non-Issues
- MemFS unavailability on Docker — falls back to Memory Blocks (already in use)
- MCP servers — continue working unchanged
- Agent memory/archival — fully preserved across both models
- Multi-agent routing — REST API-based, works with any agent type

---

## Verification Plan

1. `letta --new` connects to existing Docker server and can create/query agents
2. Skills execute correctly from the host (gws, omnifocus-cli, curl to Docker services)
3. Existing agents continue to respond to slackbot messages during and after Letta Code setup
4. Memory blocks created/modified by Letta Code agent are visible to standard agents and vice versa
5. MCP server tools remain functional for both agent types

---

## Summary

The realistic outcome is a **permanent hybrid** where:
- Standard Letta agents handle all programmatic workflows (Slack, scheduling, analytics, task processing)
- A Letta Code companion agent handles interactive/terminal use cases
- Complex tools are gradually extracted into HTTP microservices callable from either model
- The system positions itself to adopt more Letta Code features as they mature for self-hosted Docker

This preserves 100% of current functionality while gaining Letta Code capabilities incrementally, without risking any existing workflows.
