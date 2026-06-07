---
date: 2026-06-07
status: definitive (evidence-based) — supersedes the "202 to migrate" framing
evidence:
  - live agents have 0 server-tool attachments (server API)
  - 257 live conversations call ONLY CLIs (exec_command/Bash/write_stdin),
    built-in harness tools, and the 2 extension tools — ZERO bespoke server tools
  - cron jobs invoke 5 distinct tools (2 migrated, 3 CLI-covered/Docker)
related: docs/plans/2026-06-07-letta-tools-migration-plan.md
---

# Server tools — definitive disposition (what to migrate vs. drop)

## Bottom line

**The tool migration is essentially DONE.** The 6 live local agents call
**zero** of the 202 bespoke server tools — they run on host CLIs (via Bash),
Letta built-ins, and the 2 extension tools we built. The only bespoke server
logic with no CLI/service equivalent (the analytics snapshot + briefing) is
already migrated to extension tools. Everything else is **decommission, not
migrate**.

**Re: "removing the daily briefing from the server"** — we *redirected* it
(crons now call `collect_analytics_snapshot_ext` / `compose_daily_briefing_ext`);
the server tools were left **registered but dormant** for rollback. They get
**deleted at decommission**, not re-migrated.

## Disposition of all 202 custom server tools

| Disposition | Count | Action | Why |
|---|---|---|---|
| **DONE** — extension; server dormant | 2 | delete at decommission | `collect_analytics_snapshot`, `compose_daily_briefing` already on the deterministic `_ext` path |
| **CLI-replaced** — `run_*`, mc, signal, scheduler, granola, pulse-slack | 41 | drop | host CLIs already exist (`slack`/`gws`/`omnifocus`/`twitter`/`mc`/`signal`/`scheduler`/`granola`/`pulse`); agents invoke via Bash |
| **Other subsystem** — sports/media (43), Atlassian (26), calendly (3) | 72 | out of scope here | own systems (sports-and-media-tools, Atlassian MCP, Calendly MCP); not the local-agent fleet |
| **Dead** — multi-agent messaging (deprecated) + dead-Docker/other | 37 | drop | deprecated (Ezra/Cameron Apr 2026) or attached only to decommissioned Docker agents |
| **Analytics helpers** — collectors + query helpers | 17 | drop / already bundled | collectors are bundled into `collect_analytics_snapshot_ext` (helper imports in the pinned venv); query helpers read **deprecated memory blocks** and are uncalled |
| **Tasks pipeline** | 12 | drop (CLI-covered) | `task` CLI + `task queue-claim`; tasks-agent is CLI-based; 0 transcript calls |
| **Drive-RAG** | 11 | drop (service-covered) | `drive-rag-service` API (`drive-rag-curl`); 0 transcript calls |
| **Email** | 9 | drop (CLI-covered) | `gws gmail` CLI + gws-bridge; email-agent is CLI-based; 0 transcript calls |
| **Migrate-later** | 1 | migrate with schedule-agent | `generate_daily_briefing` runs on the **Docker** daily-schedule-agent; migrates only when that agent goes local |

(Exact membership is reproducible from the classification script; buckets +
rules above define every tool's disposition.)

## What this means for "confidently done"

- **Migrate now: nothing.** The only no-CLI/no-service bespoke tools (analytics
  snapshot + briefing) are migrated.
- **Migrate later: 1** — `generate_daily_briefing`, bundled into the future
  daily-schedule-agent local migration (separate; also fixes the stale
  `today.md`).
- **Drop at decommission: ~199** — CLI-replaced, other-subsystem, dead, or
  CLI/service-covered. They are not used by any live agent.

## Confidence checks (done)

- Server API: 6 live agents → 0 server-tool attachments.
- Transcript sweep (257 convos): 0 bespoke server-tool calls; all activity is
  CLI / built-in / `_ext`.
- Cron sweep: 5 tools (2 done; `emit_canonical_signal`/`read_recent_signals` →
  `signal` CLI; slack trio → `pulse` CLI; `generate_daily_briefing` → Docker).

## Decommission sequence (the remaining work — small)

1. **Confirm** (optional, belt-and-suspenders): a brief watch that the flipped
   pulse crons stay green for a few cycles; spot-check email/tasks/drive flows
   still work via their CLIs/services.
2. **Repoint** any cron messages still naming a server tool to the CLI/`_ext`
   equivalent (`emit_canonical_signal` → `signal` CLI; slack trio → `pulse`).
3. **Schedule-agent**: migrate `generate_daily_briefing` when that agent goes
   local (separate effort; fixes stale `today.md`).
4. **Delete** the 202 server tool registrations + retire the Docker Letta
   server + sandbox. Rollback stays trivial until this step (tools dormant).

## Note
The big "migrate 202 tools" framing was wrong because the local agents were
already re-architected onto CLIs + built-ins during the local-mode migration —
the server tools were left attached to the now-dormant Docker agents. The real
deliverable is **decommission**, not migration.
