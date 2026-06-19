---
date: 2026-06-19
status: SUB-PLAN — laptop bring-up + secrets transfer for MC offline/travel-mode.
parent: docs/plans/2026-06-19-mc-offline-travel-mode-plan.md
design: docs/plans/2026-06-19-mc-offline-travel-mode-design.md
note: |
  This is the "what actually needs to be on the laptop" checklist that the MVP
  plan (Phase 0–1) assumes. The repo clone is necessary but NOT sufficient —
  several pieces live outside git (home-dir launchers, memfs, conversations,
  secrets). Run on the LAPTOP unless a step says server.
---

# Laptop translation + secrets — bring-up checklist

## Pre-flight facts (verified on the server 2026-06-19)
- Repo origin: `github.com/chaddorsey/ai-PA.git`. Working branch
  `fix/pulse-analytics-briefing-local-2026-06-07` is **ahead 3** (the offline
  commits) and **unpushed**; `main` is **ahead 535** of origin.
- **git history is secret-clean** (1893 commits / 20388 blobs scanned: only
  placeholders/examples/test-fixtures) → safe to clone to the laptop and safe to
  push. Live secrets are in `.env` (gitignored, never tracked) → hand-carry only.
- letta-code runtime: `/opt/homebrew/bin/letta` → npm `@letta-ai/letta-code`.
- Launchers (`~/bin/letta-mc`, `agent-supervise`, `agent-session`,
  `claude-session`, `cmux-agent-sessions`) are **home-dir, NOT in the repo**.
- MC agent id: `agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d`.
- MC memfs remote: `http://<token>@127.0.0.1:3030/agents/<MC>.git` (Gitea,
  server-local host + embedded token).
- Server tailnet: `dorseys-mac-mini.tailf9b999.ts.net` / `100.99.171.119`.

## 0. Code delivery — clone from the SERVER over the tailnet (not GitHub)
Avoids needing to push `main` (+535) first; the server repo has the full truth.
- [ ] On the laptop: `git clone "dorseyhomeserver@dorseys-mac-mini.tailf9b999.ts.net:/Volumes/main-drive/ai-PA" ~/ai-PA` (over SSH/tailnet).
- [ ] `cd ~/ai-PA && git checkout fix/pulse-analytics-briefing-local-2026-06-07`
- [ ] `export PA_AI_REPO_ROOT="$HOME/ai-PA"` (add to `~/.zshrc`). **Never** use `/Volumes/main-drive/...` on the laptop — that's the server's drive.
- [ ] **Verify:** `ls $PA_AI_REPO_ROOT/letta/offline` shows the bus; `git -C ~/ai-PA log --oneline -3` shows the offline commits.
- [ ] (Separate, optional) back up `main` → origin from the server *after* the secret-scan (already clean) — for durability, not for the laptop.

## 1. Runtime
- [ ] Install letta-code: `npm i -g @letta-ai/letta-code` (match the server's major version — check `letta --version` on the server first).
- [ ] **Verify:** `letta --version` on the laptop equals the server's.

## 2. Local model node (from offline-plan Phase 0/1)
- [ ] Install the chosen model server + model (recorded in the MVP plan Phase 0).
- [ ] **Verify:** `curl localhost:<port>/v1/chat/completions …` returns a completion (offline).

## 3. Home-dir launchers (NOT delivered by git clone)
- [ ] Copy from the server `~/bin/agent-supervise` → laptop `~/bin/` (the self-healing wrapper is reused).
- [ ] Create a laptop `~/bin/letta-mc-local`: same as the server's `letta-mc` but
      (a) `--model mc-local`, (b) reads the minimal laptop `.env` (§5), (c) points at
      the laptop memfs clone (§4). Do **not** copy the server's `letta-mc` verbatim
      (its tokens/paths are server-side).
- [ ] **Verify:** `bash -n ~/bin/letta-mc-local` clean; it references only laptop paths.

## 4. MC memory (memfs) — clone + rewrite the remote host
- [ ] Clone MC's memfs into `~/.letta/lc-local-backend/memfs/<MC>/memory` from Gitea.
- [ ] **Rewrite the remote host** `127.0.0.1:3030` → `dorseys-mac-mini.tailf9b999.ts.net:3030` (server-local IP is unreachable from the laptop). Keep the token out of the URL where possible — prefer a git credential helper over an in-URL token.
- [ ] **Verify:** `git -C <memfs> fetch` succeeds over the tailnet; `git -C <memfs> log --oneline -3` matches the server.

## 5. Secrets — minimal, hand-carried, never via git
- [ ] **Bring ONLY:** the Gitea/memfs token (for memfs sync). That's the sole credential the offline laptop MC needs.
- [ ] **Do NOT bring:** Gmail / Slack / Drive / Calendar / Postgres / Anthropic-prod creds — those stay server-side; offline MC queues fleet work via the outbox, it never calls those APIs directly.
- [ ] **Channel:** `scp` over the tailnet or manual entry into a laptop `~/ai-PA/.env` (gitignored). Never commit; never Dropbox in cleartext.
- [ ] **Verify:** laptop `.env` contains only the memfs token (+ any local-model env); `git -C ~/ai-PA check-ignore .env` prints `.env`.
- [ ] **Posture:** FileVault on (`fdesetup status` = On); the git history clone carries no secrets (scan confirmed).

## 6. MC conversation — copy the canonical thread (not synced yet)
Conversations are per-device today (design §2). For the first run, copy the thread you want to continue.
- [ ] `scp -r` the canonical MC conversation dir(s) from server `~/.letta/lc-local-backend/conversations/<b64-id>/` → same path on the laptop.
- [ ] **Verify:** `letta-mc-local` resumes that conversation (`--conversation <id>`); the last messages match the server.
- [ ] (Superseded later by the offline-plan's conversation-sync — this manual copy is bootstrap-only.)

## 7. Connectivity + bus dirs
- [ ] Tailscale up on the laptop (`tailscale status` shows the server reachable).
- [ ] Create `~/.letta/offline-bus/{outbox,inbox}` (the plan's sync-runner/drainer use these).
- [ ] **Verify:** `tailscale ping dorseys-mac-mini` pongs; the laptop can reach Gitea `:3030` and `github.com`.

## 8. litellm route (for the cloud↔local swap)
- [ ] Add an `mc-local` model alias on the laptop routing to `localhost:<model-port>` (OpenAI-compatible).
- [ ] **Verify:** `curl localhost:4000/v1/chat/completions` with `model=mc-local` returns a completion.

## Exit (laptop is "translated")
- [ ] With Wi-Fi OFF, `letta-mc-local` answers a memory-grounded prompt (offline MC works).
- [ ] With Wi-Fi ON, the memfs `git fetch`/`push` round-trips to the server over the tailnet.
- [ ] Only the memfs token is present as a secret; FileVault on; `.env` gitignored.

## Separate follow-ups (surfaced by the secret scan — not laptop blockers)
- [ ] Verify/rotate `ZOTERO_API_KEY` in `docs/configuration-reference.md:472` if it's a real key.
- [ ] Replace the default Supabase JWT secret in `docker-compose.yml` (PGRST/GOTRUE) if prod still uses it (system hardening).
