# Two-Node Home Server — Sketch (to revisit)

**Date:** 2026-06-19 · **Status:** sketch / parked (build the trend logger first, then return)

## Setup being designed
Three machines, distinct roles:
- **Daily laptop (separate, not the server):** travel/offline node + heavy local LLM. Roomy/capable.
- **Home server = two boxes:** Mac mini (24 GB M4) + M1 Max MBP (32 GB, clamshell, MacBookPro18,4 / 14").

**Primary goal:** the home server never runs out of memory. (Recurring OOM/Jetsam reboots on the 24 GB mini are the problem we're solving.) Local LLM on the *server* is optional — deferred to the daily laptop.

## Split principle
1. **Anchor by what can't move** — external drives + USB + cameras → mini (desktop, wired).
2. **Put the *growing* workload on the roomy box** — agents + pa-web (the uncapped host-side memory-climbers) → M1 Max (32 GB).
3. **Keep hot pairs together** — co-locate chatty deps; let cross-host calls fall on cold paths (agents↔DB over Tailscale OK; agents↔litellm not → litellm moves with agents).

## Node 1 — Mac mini (24 GB): Data, Storage & Peripherals ("foundation")
- External storage: main-drive (repo), main-filestore (archives, backups)
- Mac-only: OmniFocus bridge (:8888), Flipper (USB)
- Cameras/AV: frigate + fox-cam, Roku/sports-media
- Data-bearing Docker: supabase-db (Postgres), gitea (memfs/bus), supabase-rest/auth/studio
- Storage-bound Docker: drive-rag (filestore snapshots), scheduler-service + backups
- Legacy/Slack cluster (until Slack→local): Docker Letta server + bg-fix-sidecar, slackbot, gmail-watch, granola-ingest
- cloudflare-tunnel (proxies to both nodes)

## Node 2 — M1 Max MBP (32 GB, clamshell): Agents & Compute ("brain")
- 6 Mac-native local agents (MC + email/docs/calendar/pulse/tasks) + local-mode substrate (guardian, runner, memfs sync → Gitea on mini over Tailscale)
- pa-web-ui + per-conversation letta-code subprocesses
- litellm proxy (co-located with agents → model calls don't cross network)
- Portable heavy containers: neo4j/graphiti, n8n
- Optional small (7–14B) local model — keep minimal; daily laptop is the real LLM box

## Glue
Tailscale tailnet; cross-host refs use tailnet hostnames instead of Docker DNS. Node 2 agents reach Postgres/Gitea/OmniFocus on Node 1 over the tailnet — same tunnel pattern the offline laptop uses.

## Expected memory outcome
- Mini: ~8–12 GB of 24 (data/storage Docker + peripherals) — well off the cliff.
- M1 Max: ~10–16 GB of 32 (agents + pa-web + litellm + neo4j/n8n) — headroom for the growth.

## Open questions / caveats to resolve when we return
- **Confirm the climber first** (trend logger). If it's OrbStack creep rather than agents/pa-web, move *containers* to the M1 Max instead — same two-node shape, different contents.
- System spans both nodes → a node reboot still disrupts; mitigated because each box runs far below its ceiling.
- Migration effort = replicating the local-mode substrate on the M1 Max (same playbook as the travel laptop).
- Clamshell M1 Max: battery charge limit + airflow.
- Don't move the crown-jewel Postgres volume casually; keep it on the mini.

## Next step when revisited
Turn this into the executable plan: service-by-service assignment for all 27 containers, the Tailscale cross-host wiring, and M1 Max bring-up steps.
