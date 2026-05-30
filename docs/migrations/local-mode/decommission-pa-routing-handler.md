---
date: 2026-05-30
status: complete
removed_from: docker-compose.yml, pa-web-ui/app.py, Letta tools registry
moved_to: archived/pa-routing-handler/
---

# Decommission pa-routing-handler

Removed a deprecated Flask service whose endpoints were no longer hit
in real usage, and whose `/v1/coordinate` design pattern (predefined
multi-agent task workflows) is being replaced by MC skills.

## What it was for (Jan-Feb 2026)

A Python/Flask service exposing 11 endpoints that handled:
- Session-aware message routing (`/v1/route`) — pick which agent
  should handle a message based on keywords/heuristics
- Multi-agent coordination workflows (`/v1/coordinate`) — predefined
  task_types like `meeting_prep` that gathered info from Calendar,
  Docs, Pulse and synthesized a briefing
- Agent registry (`/v1/agents`) — fleet agent list with friendly
  names + keywords for the chat header picker
- Thread/session lifecycle tracking (`/v1/sessions/.../complete`)

Built as a one-shot ~700-line spike in late Jan 2026 with iterative
follow-ons through Feb 27, then no meaningful changes since.

## Why decommissioned

Audit performed 2026-05-30 found:

1. **Zero real traffic in last 24 hours** — container logs show only
   `GET /health` from Docker healthcheck, no actual `/v1/route`,
   `/v1/coordinate`, etc. requests.

2. **All hot paths superseded** by pa-web-ui's Phase-1 subprocess pool:
   the `/stream` handler's `if PA_WEB_UI_PHASE_1_ENABLED and
   is_fleet_target:` branch catches every message for the 6 fleet
   agents and dispatches via subprocess (no routing layer needed).

3. **`/v1/coordinate` was never user-visible.** The only entry points
   were `/api/coordinate` Flask route (zero hits in 24h) and
   `/stream`'s `COORD_SLASH_PATTERN` (`/mprep`-style) commands —
   also zero hits.

4. **Letta tools that called it (`coordinate_task`,
   `analyze_task_executions`) were attached to a side-variant agent
   (`main-assistant-agent-kinara`), not the active MC.**

5. **The remaining live endpoint (`/v1/agents`) returned a static
   list of fleet agents** — duplicating data already in pa-web-ui's
   `FLEET_AGENT_NAMES` constant.

## What changed

### pa-web-ui/app.py

- Removed `ROUTING_HANDLER_URL` constant
- Replaced `/api/agents` Flask handler with one that serves
  `FLEET_AGENT_NAMES` directly (zero remote calls)
- Removed `/api/config`'s `routing_handler_url` field
- Removed `/api/coordinate` Flask route + the `stream_coordination`
  generator + `COORDINATION_COMMANDS` + `COORD_SLASH_PATTERN`
- Replaced the legacy `/stream` `generate()` block (a ~426-line dead
  code path that called `/v1/route`, streamed from Letta server, and
  hit `/v1/sessions/.../complete`) with a tiny 410 shim that fires a
  warning log if anything reaches it
- Updated `FLEET_AGENT_NAMES` comment to note it's now the sole
  source of truth

### docker-compose.yml

- Removed `pa-routing-handler` service entirely
- Removed `pa-web-ui`'s `depends_on: pa-routing-handler` and
  `PA_ROUTING_HANDLER_URL` env var

### Letta server

- Detached `coordinate_task` tool from `main-assistant-agent-kinara`
  (`agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a`); tool count went
  from 32 → 31
- Deleted both tool registrations from Letta:
  - `tool-c407fdfc-...` (`coordinate_task`)
  - `tool-b9f113e3-...` (`analyze_task_executions`)

### Container / image

- `docker stop pa-routing-handler` + `docker rm pa-routing-handler`
- `docker rmi ai-pa-pa-routing-handler` (image removed)
- Rebuilt `pa-web-ui` to pick up code changes; healthy

### Filesystem

- `git mv pa-routing-handler archived/pa-routing-handler` — code
  preserved for reference / git history

## Verification

```
curl http://localhost:5200/api/agents
# → 7 agents (Auto + 6 fleet), served from pa-web-ui's static map

docker ps -a | grep pa-routing-handler
# → (no container)

docker images | grep pa-routing-handler
# → (no image)

curl http://localhost:8283/v1/tools/?limit=500 | grep -iE "coordinate_task|analyze_task_executions"
# → (no remnants)
```

pa-web-ui home page returns 200; logs show no errors after rebuild.

## What's preserved

- **Coordination CONCEPT is sound and worth resurrecting** — see
  followup `docs/followups/2026-05-30-coordination-as-mc-skill.md`
  for the redesigned pattern (load on demand as MC skills, dispatch
  via Agent tool or letta-teams CLI as the messaging substrate).
- **Source code preserved** under `archived/pa-routing-handler/` for
  reference. Not deleted from git history.
- **`/mprep` slash command** was the entry into `coordinate_task`'s
  meeting_prep workflow. The same UX should re-emerge as MC slash
  command that loads the meeting-prep skill — same intent, cleaner
  implementation.

## Identity strip-out impact

This obviates Phase 2 of `docs/followups/2026-05-30-strip-letta-identities.md`
(the pa-routing-handler `_fetch_identities()` cache). With the service
gone, that Letta `/v1/identities/` call site is gone too.

Remaining identity strip phases now reduce to:
- Phase 3: slackbot (~4-6 hrs, gates MC migration)
- Phase 4: lookup_staff conversation tool (~1-2 hrs)
- Phase 5: decommission identity records (<1 hr)
