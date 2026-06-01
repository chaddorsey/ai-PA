---
date: 2026-05-31
status: decisions-locked 2026-06-01 (ready to execute)
agent_under_migration: Mission Control (MC)
agent_id: agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef
predecessor_migrations: docs, calendar, tasks, pulse, email (all 2026-04 → 2026-05)
---

## Decisions locked (2026-06-01)

1. **Telegram** → decommissioned entirely (via LettaBot removal)
2. **LettaBot** → fully removed: all channels, all config, all env vars,
   plist unloaded, archived under `docs/migrations/local-mode/lettabot-retired-2026-XX-XX.md`
3. **Tasks-substrate tools on MC** → removed (refresh_plate,
   write_packet_info, backtrace_task, fetch_source_content,
   search_agent_archival, trigger_task_extraction). MC delegates to
   Tasks agent via harness Task/Agent (per detached-2026-04-28 pattern)
4. **Pipeline-health cron** → Bash watchdog at
   `scripts/check-mc-pipeline-health.sh`, launchd at 06:30 ET. Removes
   agentic self-check from scheduler-service. Emits same Layer-5 signal
   path (`signals/{date}/mc-pipeline-health.md`) for steward consumers.
   Optional: keep weekly Sunday agentic introspection as a richer narrative.
5. **Granola** → keep MCP supergateway loaded AND use existing
   `/opt/homebrew/bin/granola` CLI in MC recipes. Both paths
   available; recipe prefers CLI for routine ops.

These decisions reduce Block D effort by ~2 hours (no granola wrapper
build, no tasks-substrate CLI extractions) and remove all complexity
from Block C (full retire, no per-channel triage).


# Mission Control local-mode migration — plan

## TL;DR

MC is the last fleet agent to migrate to local mode. Effort estimate
revised after audit: **~12-18 hours focused work** depending on
choices, broken into 4 work-blocks that can be sequenced (no hard
prerequisites between them once Block A starts).

The original premise that "MC is gated by the slackbot identity strip"
was incorrect — the slackbot (Kinara) does not target MC at all. MC's
real upstream is **LettaBot**, a host-side Node.js multi-channel
gateway that serves Telegram, Slack, Discord, Signal, Bluesky, and
WhatsApp into MC's single Letta conversation. LettaBot is the actual
migration blocker, and it is **currently in a degraded state** (see
Open Risks below).

## Audit findings — what we know now

### MC's current state (Docker Letta server)

| Property | Value | Note |
|---|---|---|
| Agent ID | `agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef` | |
| Type | `letta_v1_agent` | ✅ The non-deprecated type |
| Model | `gpt-5.4` | (heavier than email's nano variant) |
| message_buffer_autoclear | `False` | ✅ Pre-set, the memfs requirement is satisfied |
| memfs_enabled | `None` | ⚠️ Memfs is NOT flipped on yet — MC has 12 memory blocks but they were never migrated to memfs. The 12 block contents exist as files in `~/.letta/agents/agent-90b2e860.../memory/system/` but the agent is reading them as blocks, not from memfs. |
| Attached tools | 26 | Mix of built-in, CLI-wrappers, MC-specific, and Rover-legacy |
| Active crons | 1 | "Pipeline-health: mc daily self-check" 06:30 ET |

### MC's tool inventory — what wraps to what

Grouped by migration treatment:

**Built-in (keep as-is):**
- `conversation_search`, `archival_memory_search`, `archival_memory_insert`,
  `web_search`, `fetch_webpage`

**Already-canonical CLI replacements (just write recipes):**
- `run_slack` → `slack` CLI on PATH
- `run_omnifocus` → `omnifocus` CLI on PATH
- `run_gws` → `gws` CLI on PATH
- `run_twitter` → `twitter-cli` (verify exists)
- `emit_canonical_signal` → `signal emit` CLI
- `read_recent_signals` → `signal read` (verify) or Bash + Gitea curl

**Tasks-substrate tools (delete; MC uses task CLI like other agents):**
- `refresh_plate` → `task plate`
- `write_packet_info`, `backtrace_task`, `fetch_source_content`,
  `search_agent_archival` → likely already covered by Tasks agent's
  recipe; MC delegates to Tasks agent via harness Task/Agent now
  (per MEMORY: `send_message_to_agent_*` deprecated 2026-04-28)

**MC-specific tools needing CLI wrappers (Option-1 pattern):**
- `execute_on_laptop` — SSH-over-Tailscale executor (Rover legacy)
- `manage_widget_queue` — OmniFocus timer widget queue control
- `stage_resource` — download resource to staging dir
- `trigger_task_extraction` — Slack message → task extraction pipeline
- Granola tools (4): `get_meeting_transcript`, `list_meetings`,
  `query_granola_meetings`, `get_meeting_details`, `search_meetings_smart`
  — `granola` MCP exists via supergateway; consider if a thinner
  `granola` CLI wrapper is worth building vs leaving as MCP-callable
- `search_github_stars` — GitHub-stars browser

Estimated **8-10 new CLIs** to extract + wrap, ~3-4 hours total.

### Memfs status — needs special handling

MC has 12 system/ blocks (~58 KB total memory state) NOT yet migrated
to memfs. Other fleet agents went through a memfs-enable step. For
MC, this happens during migration (Phase D below) using the standard
memfs-migration-per-agent runbook. Key checklist item already
satisfied: `message_buffer_autoclear: false` is set.

The 12 blocks are all `system/*_protocol.md` style — the canonical-
reference protocol, scheduling protocol, drive access, signals, etc.
These should map cleanly to memfs files. Nothing exotic.

### Direct callers of MC (switchover points)

| Service | Call pattern | Switchover work |
|---|---|---|
| **LettaBot** (host-side, launchd) | HTTP gateway: receives Telegram/Slack/etc msgs → POSTs to `MC_AGENT_ID` via Letta API | **Block C** — retire or rebuild around subprocess |
| **scheduler-service** | 1 cron job "Pipeline-health: mc daily self-check" via `LETTABOT_AGENTS` registry | Re-point to local-mode subprocess invocation (Block B) |
| **task-completion-service** | Direct HTTP `POST /v1/agents/{MC}/messages` for completion notifications | Re-point to subprocess OR pa_web.task_queue (Block B) |
| **pa-web-ui** | Default agent for new conversations; subprocess-pool already handles fleet agents (incl. MC by ID) when Phase 1 dispatcher matches | Already uses subprocess pattern; just remove fallback to LettaBot URL (Block D) |
| **letta/ setup scripts** | One-time tool attachment + memory seeding | Re-run against local agent after migration (standard) |

### LettaBot — the blocker, currently broken

**Current state (verified 2026-05-31):**
- Runs via `~/Library/LaunchAgents/com.ai-pa.lettabot.plist` (npm-based Node.js service)
- Listens on `127.0.0.1:8080`
- Channel adapters present: Telegram, Slack, Discord, Signal, Bluesky, WhatsApp
- Config (`lettabot/lettabot.yaml`): Telegram enabled
- `LETTABOT_AGENTS` env in docker-compose has MC as the SOLE entry
- **Currently failing** — most recent log shows Letta client connection errors
  (`APIConnectionError: Connection error.: fetch failed`) and letta-code
  SDK errors that look related to today's `letta backend local` flip

The crash is recent. May be self-corrective on next restart; may
require LettaBot config tweak. **Should be diagnosed early in Block C**
regardless of decommission decision (if it's broken now, Telegram
isn't working anyway — making the decommission moment-of-truth less
risky).

### Telegram pivot — Letta's connector path is closed for local mode

Confirmed via Letta docs research:
- Letta's "Channels" architecture (the official Telegram/Slack/Discord
  connectors) requires a **running Letta server** with HTTP/WebSocket
  endpoints. Channels are configured server-side and persist in Letta's
  DB.
- Local-mode (lc-local-backend) agents are pure-client / file-backed.
  No HTTP endpoint. No WebSocket. **No Channels support.**
- The Letta Telegram connector (`letta-ai/letta-telegram`) is a Modal-
  deployed serverless app that talks to a Letta server.

**Implication:** The user's preferred path ("decommission custom
Telegram, use Letta's connector") is not available unless MC stays in
Docker-server mode. Three forks:

1. **Decommission Telegram entirely** — accept the loss. Lowest
   complexity. Aligns with "we don't use it much now."
2. **Keep a small Letta Docker server alongside local mode** —
   register a thin "telegram-relay" agent there with the official
   connector. That agent's only tool: an HTTP/subprocess call into
   local MC. Higher complexity (still running a Docker Letta server),
   modest functional gain.
3. **Don't migrate MC; keep it in Docker** — gives full Channels
   support but defeats the purpose of the local-mode push.

Recommended: (1). Revisit if Letta adds local-mode connector support.

### Other LettaBot channels — what to do with them

LettaBot adapters present beyond Telegram: Slack, Discord, Signal,
Bluesky, WhatsApp. Unknown which are actively used. **Verification
needed before decommissioning LettaBot wholesale.** Quick check via
the LettaBot config (`lettabot.yaml`) for `enabled: true` flags and
their last successful inbound message timestamps in the log.

If LettaBot's Slack channel is the same Concord workspace as Kinara,
it's likely a low-traffic announcement bot. If it's a separate
workspace, more thought needed. Quick audit-then-decide.

## Decisions the user needs to make

Before Block A starts:

1. **Telegram disposition** — recommend (1) decommission entirely. Alt:
   (2) keep a tiny Docker Letta server just for connectors.
2. **LettaBot disposition** — recommend retire entirely (replace its
   role with the subprocess pattern for scheduler-service + task-
   completion-service callers; let dormant channels go). Alt: keep
   LettaBot running for non-Telegram channels we discover are active.
3. **Tasks-substrate tools on MC** — recommend remove all of them
   (refresh_plate, write_packet_info, backtrace_task,
   fetch_source_content, search_agent_archival, trigger_task_extraction).
   MC delegates to Tasks agent via harness Task/Agent per the existing
   detached-2026-04-28 pattern. Alt: extract as CLIs for direct MC use.
4. **Pipeline-health cron rewiring** — invoke via subprocess
   (`letta -p`) OR convert to a Bash script that talks to MC's memfs
   directly (no agent run needed for a daily self-check).
5. **Granola tools** — keep as MCP-callable (via supergateway) OR
   build thin `granola` CLI wrapper. Recommend MCP-callable; less code.

## The 4 work-blocks

Order is suggestion only; B can start before A's full completion if
desired.

### Block A — Audit + decisions sealed (1-2 hrs)

1. Verify LettaBot's non-Telegram channels — which are actually
   delivering messages? Walk the log + check inbound timestamps per
   channel. Decide per-channel disposition.
2. Lock the 5 user decisions above into the plan.
3. Pre-flight snapshot: run `scripts/snapshot-local-mode.sh` to
   capture pre-migration state.
4. Backup MC's Letta record: full export via Letta API to a backup
   location.
5. Confirm pa-web-ui's subprocess dispatcher handles MC's agent ID
   (it should per the Phase 1 README; FLEET_AGENT_NAMES includes
   "Mission Control").

### Block B — Switchover targets (2-3 hrs)

Rewire callers BEFORE flipping MC, so the rollback path is "revert
caller config" not "revert agent migration."

1. **scheduler-service** — modify Pipeline-health daily check to
   invoke MC via subprocess (`letta --backend local --agent <MC_ID>
   -p "..."`) instead of via LettaBot URL. Verify cron continues to
   fire and produce health signal.
2. **task-completion-service** — switch from direct HTTP POST to MC
   to writing to `pa_web.task_queue` with `source='mc-completion'`.
   MC then claims via `task queue-claim --source mc-completion` when
   summoned. Lossy if MC isn't running — needs the user to be OK with
   batched completion delivery. (Alternative: subprocess invocation
   per completion, but that's heavy.)
3. **pa-web-ui** — remove `LETTABOT_API_URL` fallback (deferred per
   README); MC traffic should already flow through the subprocess
   pool. Smoke-test by opening a new MC conversation in pa-web-ui.

### Block C — LettaBot disposition (3-5 hrs)

If decision = retire:

1. Diagnose the current crash (may be a 5-minute fix tied to today's
   `letta backend local` switch). Decide whether to bring it back to
   stable before retiring or just stop it.
2. Quiesce: `launchctl unload ~/Library/LaunchAgents/com.ai-pa.lettabot.plist`
3. Tear down docker-compose env vars: remove `LETTABOT_AGENTS`,
   `LETTABOT_API_URL`, `LETTABOT_API_KEY` from docker-compose.yml +
   .env.
4. Stop relevant launchd unit, archive plist to `docs/migrations/local-mode/lettabot-retired-2026-XX-XX.md`.
5. Document in retirement doc what was decommissioned and rollback path.
6. Leave `lettabot/` code in repo (don't delete) — can be revived if
   Channels lands in local-mode later.

If decision = keep for non-Telegram channels:

1. Modify `lettabot/lettabot.yaml` to disable telegram channel.
2. Restart LettaBot, verify other channels still flow.
3. Migration takes longer but cleaner exit if/when those channels go
   dormant.

### Block D — MC migration (Phases A-I, the standard runbook) (4-6 hrs)

Follow `docs/runbooks/memfs-migration-per-agent.md` exactly — this is
identical in shape to the calendar/tasks/pulse/email migrations. Key
steps:

1. **Phase A — Snapshot** (already done in Block A).
2. **Phase B — Tool extraction** — build CLI wrappers for 4-6 MC-
   specific tools (`execute_on_laptop`, `manage_widget_queue`,
   `stage_resource`, `trigger_task_extraction`, plus
   `search_github_stars` if we keep it). Install via pipx as
   `mc-laptop`, `mc-widget`, etc.
3. **Phase C — Create local agent** — `letta agents create --name
   "Mission Control (local)" --model gpt-5.4` etc. The new agent ID
   becomes `agent-local-<uuid>`.
4. **Phase D — memfs enable** on the Docker MC FIRST (it's not yet
   memfs-enabled). PATCH `message_buffer_autoclear: false` (already
   set, sanity-check), then `/memfs enable`. This populates the
   Gitea memfs repo with MC's 12 blocks as system/* files.
5. **Phase E — Import memfs to local agent** — clone the memfs repo
   into the new local agent's working tree. Run the canonical-
   reference-protocol local-mode patch (same one applied to other
   agents).
6. **Phase F — Tool re-attachment** — attach the new CLI wrappers to
   local MC via `letta tools attach`. Leave Letta-side tools attached
   to Docker MC for rollback.
7. **Phase G — Wrapper** — write `~/bin/letta-mc` with the env block
   pattern (matching other agents: SLACK_MCP_XOXP_TOKEN,
   GITEA_MEMFS_TOKEN, POSTGRES_PASSWORD, GWS creds, etc.).
8. **Phase H — Recompile system prompt** — delete
   `~/.letta/lc-local-backend/conversations/<base64>/system-prompt.json`,
   re-launch.
9. **Phase I — Smoke test** — identity check, run each main protocol
   (signals, drive access, scheduling), verify CLI wrappers fire, run
   the daily self-check manually.

### Block E — Switchover + soak (1 hr active, then 1-2 weeks passive)

1. Rename Docker MC: `Mission Control` → `XXX-PRE-LOCAL-Mission-Control`
   (preserve for rollback).
2. Update direct callers' agent IDs:
   - `MISSION_CONTROL_AGENT_ID` in docker-compose.yml + .env → local agent ID
   - pa-web-ui defaults
   - any scheduler-service cron action configs
3. Restart affected services.
4. Soak window: 1-2 weeks (longer than other agents because MC's
   blast radius is bigger — fleet orchestration, scheduler health).
5. During soak: monitor Pipeline-health daily, watch for anomalies in
   pa-web-ui MC convos, watch for missed task-completion deliveries.
6. Post-soak cleanup: tool detachments, delete Docker MC.

## Effort breakdown

| Block | Estimated hours | Can parallelize? |
|---|---|---|
| A — Audit + decisions | 1-2 | No |
| B — Switchover targets | 2-3 | After A |
| C — LettaBot disposition | 3-5 | After A; can run parallel to B if helpful |
| D — MC migration | 4-6 | After A; can run parallel to B/C |
| E — Switchover + soak | 1 active + 1-2 weeks passive | After all |
| **Total active** | **11-17 hours** | |

## Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| LettaBot crash is post-today's-changes — Telegram users are unaware | Med | Diagnose Block A; either restore or document silent failure |
| MC memfs migration introduces the autoclear bug (calendar canary) | Low | autoclear already False; verify before memfs enable |
| Task-completion-service queue pattern adds latency for "I just finished a task" notifications | Low | Already accepted pattern for email-watch; same UX |
| pa-web-ui subprocess pool wasn't designed for MC's tool surface size (26 tools) | Med | Smoke-test in Block A; subprocess pool already handles other fleet agents with similar tool counts |
| Hidden caller of MC's HTTP endpoint discovered post-switchover | Med | Block B grep was thorough; any miss surfaces during soak |
| User's "try Letta connector" intent is not satisfied because connector is server-only | High UX | Documented in plan; user decides |

## Rollback strategy

Three layers:

1. **Per-caller revert** (Block B/E switchovers): every caller change
   is gated by env var or a single config line. Revert by flipping
   back to Docker MC's agent ID + LETTABOT_API_URL.
2. **MC agent rename** (Block E): Docker MC kept as
   `XXX-PRE-LOCAL-Mission-Control` with tools + memfs intact through
   soak. Rename back via `PATCH /v1/agents/{id}` body
   `{"name":"Mission Control"}`.
3. **LettaBot revival** (if decision was retire): plist + config
   remain in repo. `launchctl load` + restore docker-compose env vars
   to bring it back online.

## Open questions to answer in Block A

1. Which non-Telegram LettaBot channels (Slack, Discord, Signal,
   Bluesky, WhatsApp) are actually receiving messages? Is the
   LettaBot Slack channel the same workspace as Kinara?
2. Is the LettaBot crash today self-resolving on restart, or does it
   need config intervention?
3. Does pa-web-ui's subprocess dispatcher correctly handle MC's
   current Docker agent ID, or does the FLEET_AGENT_NAMES match
   require the local agent ID after we create it?
4. Should `granola` get a thin CLI wrapper (like we built for other
   agents) or stay MCP-callable?
5. Are MC's tasks-substrate tools (refresh_plate etc.) actually used
   by MC, or are they vestigial from before delegation moved to
   harness Task/Agent?
