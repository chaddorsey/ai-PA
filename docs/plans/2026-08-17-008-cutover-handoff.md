---
title: "Cutover + web-slice handoff — read this first in the fresh session"
type: handoff
status: ready
date: 2026-08-17
origin: docs/plans/2026-08-15-006-feat-continuity-controller-plan.md (post C1–C8 + C10b rehearsal)
branch: feat/msc-app-server-sole-owner
---

# Handoff: attended cutover, then the minimal web slice

Written at the end of the build session (2026-08-15→17) so a fresh session can execute
without re-deriving anything. **Authority order when documents disagree: the runbook, then
this handoff, then memory.**

## Where things stand (all committed on `feat/msc-app-server-sole-owner`)

- Controller **built and proven on clone**: C1–C8 green, P1–P5 passed live, 125-entry
  mutation harness caught everything, rollback rehearsed at ~1s. Nothing has touched the
  live backend; the live system still runs its incumbents.
- **Both operator decisions are IN** (2026-08-16): ingress secret = **path-token**
  (`/t/<secret>/v1/agents/{agent_id}/messages`); quiesce Tier-3 = **option (a)** (runner
  bootout at cutover, two `route=local` jobs re-pointed same-sitting,
  memfs-sync/extension-tools migration = first post-cutover unit).
- Authoritative docs: `docs/runbooks/continuity-controller-cutover.md` (the steps, tiers,
  decisions, rollback), `docs/plans/2026-08-15-006-controller-spike-findings.md` (platform
  facts incl. the S7 stock-TUI negative), `docs/plans/2026-08-15-006-salvage-map.md`,
  `docs/plans/2026-08-15-006-scheduler-job-inventory.md`,
  `clients/continuity-controller/README.md` (ops: env vars, CLI, ports).

## Session 1 (operator attended): the terminal-first cutover

Run runbook §2 top to bottom. Facts the fresh session would otherwise rediscover:

- **Production registry seeding (step 4)** — local fleet agent ids
  (`continuity-controller registry add --agent <id> --label <label> [--default]`; each
  creates a REAL conversation — `default` alias is banned by design):
  - MC/Kinara `agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d` → label `kinara`,
    **--default**
  - tasks `agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4` → `tasks`
  - docs `agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a` → `docs`
  - email `agent-local-93241bd6-ce9c-4ea6-89ca-318a6d873b0f` → `email`
  - calendar `agent-local-cd5ed5cd-44d5-4e32-b202-3d8dfcb5505c` → `calendar`
  - pulse `agent-local-d48b128a-b3a8-4930-a27f-b4127c96fe3a` → `pulse`
  Then `routes set --alias <label> --agent <id>` per specialist for the direct lane.
  NOTE: history does NOT move into these new threads — old conversations stay readable in
  the backend; recall is qmd/archive as before. (Known, accepted.)
- **Quiesce specifics (step 2, decided)**: kill `restore-app-server.py` + its `:4577` child
  (Tier 1); quit Letta.app (its `--backend local` child holds the empty cron lease); close
  the `agent-supervise` tmux TUIs (kinara/mc, email, tasks, calendar, pulse — they exec
  `letta --backend local`, direct writers); `launchctl bootout gui/501/com.ai-pa.letta-local-runner`.
  Non-writers (leave alone): letta-teams-daemon, letta-cleanup, letta-code-verify,
  letta-push-receiver (enrichment — a `/v1/responses` client; it stays up through the swap,
  503-retrying during the seconds-long gap).
- **Ports/env**: controller surface `:4610`, ingress `:4611`, App Server `:4577`. Production
  state dir `~/Library/Application Support/continuity-controller` (auto-created; token +
  liveness + SQLite live there). Set `CONTINUITY_INGRESS_SECRET` in the worker plist env —
  without it the ingress stays down (fail-closed).
- **Plist hygiene**: production plists are the TRACKED copies
  (`clients/continuity-controller/launchd/com.ai-pa.continuity-{controller,anchor}.plist` and
  `letta-push-receiver/launchd/com.ai-pa.letta-app-server.plist`) hand-copied to
  `~/Library/LaunchAgents`. The `*-clone.plist` files there are the rehearsal copies —
  do NOT load them at cutover; delete them at clone teardown.
- **Same-sitting follow-ups**: PATCH the two `route=local` jobs (`6afa76c3`, `1ccfae03`) to
  `route=letta` (agent ids unchanged — already local ids); archive the fired rehearsal job
  `e054f4b5`; add the controller state dir to `deployment/scripts/backup.sh` host-data.
- **Rollback**: runbook §3 — 3a partial (controller only, 1s, rehearsed) and 3b **full
  switch-back to the incumbent stack** (≈2 min: controller down → sole owner down →
  `restore-app-server.py` → scheduler env revert → runner reload → tmux TUIs → Desktop).
  No data migrates anywhere; order matters (writers return only after the tripwire-armed
  server is down).
- **Verification** = runbook §2 step 9 checklist (P1/P2/C4 vitest live gates against `:4577`
  with a scratch agent via `clients/tools/scratch-agent.mjs`, scripted P3/P4, a 10:55
  one-off job, an `@specialist` exchange). P5 stays clone-only.
- **Phone access works DAY ONE after this session with zero new code**: mosh + tmux (already
  the operator's pattern) + `letta-continuity` — the whole point of the controller is that
  a phone SSH session detaching mid-turn loses nothing.

## Session 2: the minimal web slice (phone browser) — TAILSCALE-FIRST

C9 carries a **pickup gate**: expand it to full unit format in the parent plan before
implementing. For the *minimal* slice (basic chat from the phone browser), the
**recommended transport is the operator's tailnet** (raised by the operator 2026-08-17;
confirm at pickup, then it is decided):

- **Verified on this box**: the Mini, the MacBook, and the iPhone are all on the tailnet,
  and `tailscale serve` is ALREADY serving `https://dorseys-mac-mini.tailf9b999.ts.net`
  (tailnet-only, real cert) proxying `/` → `localhost:5140`. Add a PATH mount (do not
  clobber the existing `/` mount) proxying to `127.0.0.1:4610` — `tailscale serve` proxies
  WebSockets, so `wss://…ts.net/<path>/surface` reaches the controller with **zero
  controller code change** and TLS handled by Tailscale.
- **Auth simplification, and why it is sound**: the surface protocol authenticates with the
  token in the FIRST WS FRAME (never a header, never the URL) — the browsers-can't-set-WS-
  headers problem that motivated tickets does not apply to our own protocol. Tickets were
  about PUBLIC exposure (secrets leaking through proxy logs, long-lived tokens on
  internet-reachable pages). Inside the tailnet, WireGuard device identity is the network
  gate and the existing 0600 surface token (pasted once on the phone, kept in
  localStorage) remains the app-layer gate — defense in depth, no new auth code.
  **`mintTicket` stays a throwing stub**; the ticket design is deferred to genuine public
  (Cloudflare) exposure in full C9.
- **What to build**: a single static page speaking surface protocol v1 (`core` + `notify`;
  protocol = `clients/continuity-controller/src/surface/protocol.ts` + README table).
  Serve it either via a second `tailscale serve` path → static dir, or by teaching the
  controller's `:4610` HTTP handler to answer `GET /` (it deliberately 501s today — a
  small, honest addition). Validate on the desktop browser via loopback first.
- **Laptop terminal over the tailnet** (nice-to-have follow-up): `letta-continuity
  --controller-url` currently hard-pins loopback (`assertLoopbackUrl(…, false)` in
  `cli.ts`); an explicit opt-in for `ts.net`/tailnet URLs would let the MacBook attach
  directly. Until then, mosh+tmux covers the laptop exactly as it covers the phone.
- Rail CRUD / fork / archive stay in full C9. Test assets that carry over:
  `test/helpers/surfaceClient.ts` shows the exact frames; the two-surface + 10:55 tests
  define expected behavior.

## Cleanup (any time)

Clone artifacts, all inert now: `/private/tmp/lc-clone-c1`, `/private/tmp/continuity-clone-state`
(rehearsal journal/SQLite evidence — keep until cutover soaks), the two `*-clone.plist`
files in `~/Library/LaunchAgents`, `~/Library/Logs/continuity-controller/*-clone.log`, and
the two scratch agents (exist only inside the clone backend — deleting the dir deletes
them). To resurrect the clone stack: `LETTA_LOCAL_BACKEND_DIR=/private/tmp/lc-clone-c1
letta server --backend local --listen ws://127.0.0.1:4599` + load the two clone plists.

## Standing follow-ups (post-cutover backlog, in rough order)

1. memfs Gitea sync + pa-tools extension bridge off the runner (unblocks retiring it for good).
2. Full C9 (rail + full capability tier) after the minimal slice.
3. C10a orchestration pattern registry.
4. Upstream ask: an attach flag for the stock TUI (S7: `AppServerClient` already ships in
   the bundle; only `channel-gateway` consumes it) → then a controller protocol_v2 facade
   makes the native TUI a governed surface.
5. Journal retention/compaction at first size threshold; `letta-code-verify`/cleanup jobs
   unchanged.
