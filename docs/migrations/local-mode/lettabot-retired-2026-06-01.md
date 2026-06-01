---
date: 2026-06-01
status: retired
service: lettabot
prior_purpose: Multi-channel gateway (Telegram, Slack, Discord, Signal, Bluesky, WhatsApp) serving Mission Control agent
---

# LettaBot — retired 2026-06-01

## Summary

LettaBot was a host-side Node.js multi-channel gateway that served the
Mission Control (MC) Letta agent. It listened on `127.0.0.1:8080` and
relayed messages from Telegram (and other channels, mostly dormant)
into MC's Letta conversation, and back out.

Retired as part of MC's local-mode migration plan
(`docs/plans/2026-05-31-mc-migration-plan.md`). The decision was
straightforward: Letta's native Channels architecture requires a Letta
server with HTTP/WebSocket endpoints; local-mode agents are file-backed
with no such endpoint. Custom maintenance of LettaBot's channel
adapters wasn't justified given the user's low Telegram usage.

LettaBot was also already in a degraded state on retirement day: its
session pre-warm subprocess (which spawns `letta-code`) had been
failing since the most recent `letta backend local` flip changed the
default backend out from under it. Telegram inbound was silently
broken; retirement was zero-cost from a UX standpoint.

## What was decommissioned

- **launchd unit:** `~/Library/LaunchAgents/com.ai-pa.lettabot.plist`
  archived to `docs/migrations/local-mode/archived-plists/`
- **Process:** PID 978 (npm/tsx/node) — `launchctl unload`ed
- **Port:** 127.0.0.1:8080 — freed
- **docker-compose env vars:**
  - `LETTABOT_AGENTS` (scheduler-service env, line 420 of docker-compose.yml)
  - `LETTABOT_API_URL` (pa-web-ui env, line 1537)
  - `LETTABOT_API_KEY` (pa-web-ui env, line 1538)
- **.env vars:**
  - `TELEGRAM_TOKEN` (line 217)
  - `LETTABOT_API_KEY` (line 219)
- **Code:** `lettabot/` directory remains in repo (not deleted).
  Includes channel adapters for Telegram, Slack, Discord, Signal,
  Bluesky, WhatsApp. Available for revival if Letta adds local-mode
  Channels support.

## Callers that needed rewiring

| Caller | Was | Now |
|---|---|---|
| scheduler-service Pipeline-health daily cron | POST to `LETTABOT_AGENTS[MC].url` | **Paused** 2026-06-01 (cron status=paused). Replaced by host-side Bash watchdog `scripts/check-mc-pipeline-health.sh` + launchd plist `com.ai-pa.mc-pipeline-health.plist` at 06:30 ET (lands in Block B). |
| pa-web-ui MC traffic | Subprocess pool (already, via `PA_WEB_UI_PHASE_1_ENABLED=true`) | Same. The legacy `LETTABOT_API_URL` fallback path at `pa-web-ui/app.py:2393-2416` is dead code now (all 6 fleet agents are in `FLEET_AGENT_NAMES`); slated for removal in a follow-up cleanup. |
| task-completion-service MC completion notifications | Direct `POST /v1/agents/{MC}/messages` (NOT via LettaBot — direct to Letta server) | Rewired in Block B to write to `pa_web.task_queue` with `source='mc-completion'`. |

## Rollback (full, if ever needed)

```bash
# 1. Restore plist + reload
cp docs/migrations/local-mode/archived-plists/com.ai-pa.lettabot.plist \
   ~/Library/LaunchAgents/com.ai-pa.lettabot.plist
launchctl load ~/Library/LaunchAgents/com.ai-pa.lettabot.plist

# 2. Restore .env vars (original values below; rotate before reuse)
echo 'TELEGRAM_TOKEN=8684373817:AAG2ybDgqtl6QNzCfNs1JG7KUP5C-mLAFpI' >> .env
echo 'LETTABOT_API_KEY=7f7ab2d6bccfeb8e0f85f82557c27db581c3176fcd043ccacc62a648279dd4ce' >> .env

# 3. Restore docker-compose.yml env vars (lines 420, 1537-1538);
#    git revert the LettaBot-retirement commit will do this cleanly.

# 4. Restart affected services
docker-compose up -d --force-recreate scheduler-service pa-web-ui

# 5. Resume Pipeline-health cron
curl -X PATCH "http://localhost:8087/v1/jobs/3cbdccfd-045d-4362-abc3-71bd5f2858d2" \
  -H 'Content-Type: application/json' \
  -d '{"status":"scheduled"}'
```

Note: rotating the Telegram bot token (via @BotFather) before re-enable
is recommended since it was visible in repo history.

## Diagnostic state at retirement

Last LettaBot log (`/tmp/lettabot.log`) before unload:

```
[04:19:51] INFO: [Bot] Started channel: Telegram
[04:19:51] INFO: [Gateway] Started: Mission Control
[04:19:51] INFO: [Gateway] 1/1 agents started
[04:19:51] INFO: [API] Server listening on 127.0.0.1:8080
[04:19:52] ERROR: [Letta-api] Failed to get agent tools:
    APIConnectionError: Connection error.: fetch failed: ECONNREFUSED
[04:19:52] WARN: [Session] Session pre-warm failed: Failed to initialize session
```

The crash was caused by:
1. `letta backend local` set as default earlier on retirement day
2. LettaBot's `Session` pre-warm spawns a `letta-code` subprocess
   without `--backend` override
3. The spawned `letta-code` defaulted to local backend, couldn't
   find Letta server at expected location, exited 1
4. `[Letta-api] Failed to get agent tools` came from a separate
   internal HTTP call to `localhost:8283` (the Docker Letta server),
   which the LettaBot's `Letta` client attempts independently. That
   call appears to have failed due to a transient network issue at
   that exact moment; subsequent diagnosis confirmed `localhost:8283`
   was reachable. Likely a startup-timing window with no retry.

Either issue alone would have made LettaBot unable to function. Both
together made retirement a no-op from a user-facing perspective.
