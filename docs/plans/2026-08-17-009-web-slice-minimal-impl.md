# Minimal web slice (phone browser chat) — Tailscale-first implementation

Origin: `docs/plans/2026-08-17-008-cutover-handoff.md` (Session 2). Transport decision
CONFIRMED at pickup (operator, 2026-08-17): **tailnet**. `mintTicket` stays a throwing
stub; tickets are deferred to genuine public exposure (full C9). Rail CRUD / fork /
archive stay in full C9.

## What ships

A single static page speaking **surface protocol v1** (`core` + `notify`), served by the
controller's own `:4610` HTTP handler (the deliberate 501 becomes a page — "a small,
honest addition" per the handoff), reached from the phone via a `tailscale serve` PATH
mount on the existing `dorseys-mac-mini.tailf9b999.ts.net` ident (which already proxies
`/` → :5140 — do not clobber).

## Design decisions

1. **Page served by the controller itself** (option b from the handoff), not a second
   static server: one port (4610) carries both `GET /` (page) and `/surface` (WS), so ONE
   tailscale path mount covers both, and loopback desktop validation needs zero extra
   pieces. Page file: `clients/continuity-controller/static/index.html`, read per-request
   (no restart to iterate); non-`/` non-WS paths keep refusing loudly.
2. **Prefix-tolerant WS path**: `tailscale serve` path-mount prefix stripping is
   version-dependent; instead of betting, the WS upgrade accepts `/surface` AND any path
   *ending* in `/surface`. The page derives its WS URL from `location` (same origin, same
   path dir), so it works identically at `http://127.0.0.1:4610/` and
   `https://…ts.net/pa/`.
3. **Auth**: first-frame token per protocol (browsers-can't-set-WS-headers does not apply
   to our own protocol). Token pasted once on the phone, kept in `localStorage`. Network
   gate = WireGuard device identity (tailnet-only serve); app gate = the 0600 surface
   token. No new auth code.
4. **Runtime selection**: settings drawer with agent_id / conversation_id prefilled to
   the kinara default thread; stored in localStorage. Minimal slice = one thread chat; no
   rail.
5. **Rendering** mirrors `letta-terminal/src/controller-core.ts`: replay + live journal
   events; deltas by `payload.delta.message_type` (user/assistant bubbles; reasoning and
   tool traffic collapsed to a status line); `turn_terminal` / `turn_failed_visible`
   surfaced; mine-vs-peer attribution via `send_ok` receipts + `turn_accepted` origins;
   `presence` on visibilitychange; bounded auto-reconnect with cursor resume.

## Tasks

- [x] 1. `server.ts`: serve `GET /` from `static/index.html`; prefix-tolerant WS upgrade;
        offline tests for both (page served; prefixed-path attach works; other paths still
        refuse). — `test/surface.web.test.ts`, suite 81 green.
- [x] 2. `static/index.html`: the page (protocol v1 core+notify, per decisions above).
        Learned the terminal's lesson live: delta chunks carry DIFFERENT `delta.id`s, so
        bubbles key on `run_id|message_type` (render.ts precedent).
- [x] 3. Validated on desktop via loopback (Playwright): first-run settings flow, attach,
        replay renders coherently, live exchange round-trips with send receipts.
- [x] 4. Tailnet mount live: `/pa` → `127.0.0.1:4610` alongside the existing `/` mount
        (whose 502 is its own backend being down — nothing listens on :5140; config
        intact). `attach_ok` verified over `wss://…ts.net/pa/surface`. Surface token
        ROTATED post-validation (the old one transited the build session).
- [ ] 5. Operator phone validation (paste token, exchange, detach/reattach).
