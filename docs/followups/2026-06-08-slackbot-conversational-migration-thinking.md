---
date: 2026-06-08
status: ON HOLD — capturing current thinking; weighing scenarios before planning
topic: Migrate slackbot's conversational core off the Docker Letta server (last major Letta-Docker dependency)
branch: fix/pulse-analytics-briefing-local-2026-06-07
---

# Slackbot conversational migration — current thinking (parked)

## Why this exists
Slackbot ("Kinara") is the **last substantial consumer of the Docker Letta
server**. Everything else in the daily-briefing / fleet wind-down is done or
trivially done (see "Surrounding state"). The user confirmed the Slack assistant
is **actively used** (just not lately) and that the **interactive scheduling flow
is crucial** and must be ported carefully. Parked to weigh strategic scenarios
before writing a plan.

## What slackbot's conversational core depends on today (all Docker Letta)
- **Transport:** `ai/providers/letta_stream.py` — `LettaAPIStreaming`, SSE from
  `/v1/agents/{id}/messages/stream` or `/v1/conversations/{id}/messages`. Yields
  text deltas **and tool-call events and tool returns**.
- **Per-user conversations:** `ai/letta_conversation.py` — one Letta Conversation
  per (Slack user, agent), mapped via Supabase `user_conversations`, keyed by
  **Letta identity** (`ai/identity.py`). Identities + Conversations-as-server-
  objects + core-memory **block attach** (`ai/conversation_helper.py`) are all
  deprecated in the local/memfs model.
- **Agents:** scheduler = Docker `agent-892a2d58` (calendar_copy), email =
  `agent-b4928949`. Default brain = the scheduler agent.
- **Interactive scheduling flow:** `services/agent_bridge.py` sends synthetic
  structured messages and **extracts structured tool-return payloads out of the
  SSE stream** to build `InteractiveProposal` sets → Slack buttons
  (`services/interactive_proposals.py`, `listeners/actions/proposal_actions.py`).
  Approve → confirmation modal (cached proposal) → book.

### The scheduling engine is the crux
The proposal flow runs the **`orchestrate_scheduling`** Letta tool, backed by
`letta/scheduling_orchestrator/` — a **~6,400-line package** (`orchestrate_scheduling.py`
5257, `evaluate_proposed_times.py` 515, `free_block_scorer.py` 653) with a
**clingo ASP solver** (`clingo_wrapper.py`, `asp_encoding.py`, `python_solver.py`
fallback), DSPy extraction, calendar clients, canonical lookups. It **already
ships a FastAPI `server.py` + `Dockerfile.api` + `requirements-api.txt`** — i.e.
it's built to run as its own service. It is far too heavy for the Letta sandbox
or the pinned pa-tools venv. (TODO on resume: confirm whether it's already
deployed as a service in docker-compose — `free_block_scorer` matched
docker-compose.yml.)

## Already-local (no migration needed)
Slackbot's utility layer is already off Docker Letta:
- `chad_mention_signal.py` → canonical signals (Gitea)
- `send_to_tasks.py` → push-receiver (`LETTA_PUSH_RECEIVER_URL`) → warm
  letta-code subprocess (fire-and-forget; poller backstop). **The push-receiver
  returns no reply — unsuitable for conversational replies.**
- `schedule_command.py`, `analytics_csv_capture.py` → Letta-server-free.

## Local bridges available as targets
- **local-runner `:8920` `/invoke`** — request/response, returns `agent_response`.
  No streaming, no per-user conversation isolation, single-agent/serialized.
  (What we use for the briefing + analytics crons.)
- **pa-web-ui pattern** — per-conversation letta-code subprocess + memfs +
  `pa_web.conversation_meta`. The proven way to get per-conversation isolation
  locally.
- **MC-local** (`agent-local-8474bbbd`) — candidate general brain.

## Decomposition (the migration is 3 sub-projects)
1. **Scheduling engine → standalone service.** Run `scheduling_orchestrator` as
   its own HTTP service; expose `orchestrate_scheduling`/`evaluate_proposed_times`
   via HTTP/CLI. Decouples the hard part from BOTH Docker Letta and the local
   venv. Long pole, independently valuable.
2. **Conversational transport.** Replace `LettaAPIStreaming` + Conversations +
   identities + block-attach with a local bridge (per-Slack-DM → local brain,
   request/response, final-text). Drop deprecated primitives.
3. **Proposal round-trip.** Get structured proposal data back to slackbot to
   render buttons (local `/invoke` is text-only). Plus where the "brain" sits.

## Decisions so far
- **Sequencing: engine-as-service FIRST** (user-selected). De-risk the long pole
  independently; then transport; then wire proposals. Each its own
  spec/plan/rollback.

## Open decisions (deferred)
- **The brain:** one unified Slack-assistant local agent (scheduling + task
  routing + general + room to grow) vs MC-local vs multi-agent routing. (User
  leaned toward "much of the work is scheduling + task routing, may want more"
  → suggests a unified brain, but undecided.)
- **Proposal data path:** slackbot → scheduling service **directly** for the
  structured step (deterministic; brain does conversational framing) vs
  **agent-mediated** (brain calls the tool, returns parseable structured data).
- **User scope:** single-user (just Chad) vs multi-user (needs per-user
  conversation isolation).
- **Streaming UX:** drop to final-text replies (note: `ENABLE_SLACK_STREAMING`
  already defaults to false) vs preserve streaming.
- **Parity-first** (replicate scheduling + task routing + general DM, no new
  features during migration) vs include new functionality now.

## Scenarios to weigh BEFORE planning (the reason this is parked)
The user wants to consider a few scenarios first:
1. **Full local migration** (all 3 sub-projects) → Docker Letta fully retired.
2. **Engine-as-service, brain stays on Docker (interim)** → partial; removes the
   heavy tool from the sandbox but keeps the server for slackbot's brain.
3. **Slim Docker Letta kept solely for slackbot** → defer slackbot indefinitely;
   accept one small Letta server as a permanent dependency.
4. **Re-home / re-scope the Slack assistant** → reconsider whether the Slack
   conversational assistant is still the right primary surface given pa-web-ui +
   Claude Code; possibly fold its role into a different interface, changing what
   "migrate" even means.
(Also bundle in: whether the unified brain should be the same agent that handles
task routing / future functionality — i.e., this decision may be bigger than
slackbot and worth settling at the fleet level.)

## Rollback posture (whatever path we pick)
- Routing is env/flag-driven (`LETTA_BASE_URL`, agent IDs,
  `ENABLE_SLACK_STREAMING`, `DISABLE_ASSISTANT_STREAMING`; add a `ROUTE_TO_LOCAL`
  flag). Revert = flip flags, restart slackbot container.
- **Per-identity canary:** route only Chad's user to the local path; everyone
  else stays on Docker — test live with near-zero blast radius.
- Keep the Docker calendar/email agents + the Letta server intact until soaked.
  Slackbot is the last gate before Letta Docker can be turned off.

## Surrounding state (so this resumes cold)
- Daily-briefing fully local (materialized current cell + launchd refresher +
  bash watchdog). Analytics/calendar/tasks pipeline crons local. Steward rollup
  localized (Docker notify removed). Lookahead + daily-schedule self-check crons
  paused → Docker `daily-schedule-agent` dormant.
- **Remaining Letta-Docker ties:** (a) **slackbot conversational core** (this
  doc); (b) **pa-web-ui** has `LETTA_BASE_URL=letta:8283` set but runs local
  subprocesses via the sidecar — **still to verify whether that URL is used or
  vestigial** (the other "substantial piece").
- ~40 dormant Docker agents (`XXX-PRE-LOCAL-*`/`XXX-ARCHIVE-*`) await deletion at
  final decommission.

## To resume
Re-open the brainstorming with the 4 open decisions above (sequencing already =
engine-first). Decide the scenario first, then brain → proposal path → user
scope → parity, then writing-plans per sub-project (engine-as-service first).
