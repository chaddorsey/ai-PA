# Docker Letta Server — Decommission Audit

**Date:** 2026-06-19
**Question:** Now that the fleet runs in local mode, which Docker Letta agents are superfluous, and can the Docker `letta` server be retired?

## Bottom line

- The **Docker `letta` server cannot be turned off yet.** Three running services still
  route to PRE-LOCAL Docker agents, plus several use it as a generic API endpoint.
- **~28 of the 44 Docker agents are pure cruft** (archive/ignore/rogue/ephemeral) and
  are safe to delete after a glance.
- **This is hygiene, not a memory fix.** The Docker `letta` container is **410 MiB**
  regardless of agent count (agents are DB rows, loaded on access). The 2026-06-19
  reboots were host-side OOM (the *local* node fleet + apps), unrelated to this.

## The 6 PRE-LOCAL agents → local replacements (1:1)

The fleet migration renamed each Docker original `XXX-PRE-LOCAL-*`. Local replacements
run as host-side `letta-code` node processes (cmux sessions via the guardian).

| Role | Docker (PRE-LOCAL) | Local replacement | Still wired? |
|------|--------------------|-------------------|--------------|
| MC | `agent-90b2e860` | `agent-local-8474bbbd` (kinara) | only archived jobs + scripts |
| email | `agent-b4928949` | `agent-local-93241bd6` | **YES — gmail-watch-service (`EMAIL_AGENT_ID`)** |
| docs | `agent-398b4f6c` | `agent-local-3898b33a` | **YES — granola-ingest (`GRANOLA_AGENT_ID`), known-broken** |
| calendar | `agent-892a2d58` | `agent-local-cd5ed5cd` | **YES — slackbot (`LETTA_AGENT_ID`), ACTIVE** |
| pulse | `agent-2ed14ef4` | `agent-local-d48b128a` | only archived analytics jobs + scripts |
| tasks | `agent-dd15479e` | `agent-local-30c45759` | only archived jobs + scripts |

## Live dependencies on the Docker letta server (the decommission blockers)

All "running" as of this audit (post-reboot).

| Consumer | Running | Targets | Notes |
|----------|---------|---------|-------|
| **slackbot** | ✅ healthy | `892a2d58` (PRE-LOCAL calendar) via `LETTA_AGENT_ID` | **Slack is NOT on local mode.** `slackbot/ai/letta_conversation.py:33` reads `LETTA_AGENT_ID` with `892a2d58` hardcoded as fallback. Oddly points at the *calendar* agent — historical artifact. Biggest blocker. |
| **gmail-watch-service** | ✅ healthy | `b4928949` (PRE-LOCAL email) via `EMAIL_AGENT_ID` | Verify whether it notifies the agent or only enqueues to `task_queue`. |
| **granola-ingest** | ✅ healthy | `398b4f6c` (PRE-LOCAL docs) via `GRANOLA_AGENT_ID` | Already broken — no meeting drafts (points at retired docs agent). |
| scheduling-orchestrator-api | ✅ healthy | `letta:8283` base (no specific agent) | API-level use; needs code check. |
| mirror-writer | ✅ healthy | `letta:8283` base | API-level use; needs code check. |
| pa-web-ui | ✅ healthy | `letta:8283` base | Spawns LOCAL subprocesses; base URL likely metadata/fallback. |
| memfs-sync-relay | ✅ running | `letta:8283` base | API-level use. |
| letta-bg-fix-sidecar | ✅ healthy | `letta:8283` upstream | The #99 silent-stall proxy. |
| auto-madden-insight-engine | ❌ not running | `letta:8283` base | — |
| open-webui | ❌ not running | `letta:8283` upstream | — |

**Scheduler:** every job is `status=archived` — NOT a live consumer (the agent IDs in
`scheduler.jobs`/`scheduler.actions` are historical).

## Disposition of all 44 Docker agents

**Safe to delete now (~28, high confidence):**
- `XXX-ARCHIVE-*` (7): scratch-agent, companion-agent ×2 + 2 sleeptimes, voice-companion + sleeptime
- `XXX Ignore / XXX-Ignore` (4): LettaBot ×2, Letta Code ×2
- `MC-rogue-*` (3): `e119f0ed`, `a5f374b2`, `44eda6f7`
- `Letta Code` ephemeral session agents (~11)
- Old predecessors per memory: `pulse-monitor-agent` (`6eb765bf`), `pulse-monitor-agent-sleeptime` (`66c4a151`), `calendar-agent` (`e28c6c16`)

**Investigate before deleting:**
- `steward` (`6349140d`, letta_v1, updated 2026-06-07) — purpose unknown
- `work-packet-assembler` (`06a5b4a8`) — task-pipeline legacy (work-packet now local?)
- `sports_and_media_maven` (+ sleeptime) — sports-service may still call it
- `auto_madden_agent` (+ sleeptime) — engine currently not running
- `main-assistant-agent-kinara` (`b1574f99`) — appears in archived scheduler jobs
- sleeptime agents generally (`tasks-agent-sleeptime`, `email-agent-sleeptime`, `companion-sleeptime_copy`) — sleeptime type is deprecated

**Blocked until their consumer migrates (the 3 wired PRE-LOCAL):** `892a2d58` (Slack),
`b4928949` (gmail-watch), `398b4f6c` (granola).

## Decommission path (when ready — not yet)

1. **Migrate Slack to local** — repoint slackbot off `892a2d58` to the local fleet
   (this is the real "Slack → local mode" task; biggest piece).
2. **Repoint gmail-watch + granola** to the local email/docs agents (or confirm they
   only need `task_queue`).
3. **Audit the API-level consumers** (scheduling-orchestrator-api, mirror-writer,
   memfs-sync-relay, pa-web, sidecar) — determine whether they need a Letta *server*
   at all in a local-only world.
4. **Delete the ~28 cruft agents** anytime (independent of the above; frees ~0 memory,
   declutters the roster).
5. Only after 1–3: stop/remove the Docker `letta` container + sidecar.

## Reminder

Retiring the Docker server is a clarity/maintenance win, **not** the fix for the
recurring reboots. That remains host-side memory pressure (see the OOM/Jetsam finding).
