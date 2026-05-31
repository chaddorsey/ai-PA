---
date_started: 2026-05-30
date_phase_h: 2026-05-30
status: migrated, soaking
agent_old_id: agent-b4928949-8012-4436-a3c7-a9e510785147
agent_old_name_now: XXX-PRE-LOCAL-email-agent
agent_new_id: agent-local-93241bd6-ce9c-4ea6-89ca-318a6d873b0f
agent_new_name: email-agent-local
model: lmstudio/gpt-5.4-nano
backup: /Volumes/main-filestore/ai-PA-backups/local-mode-migrations/email-agent/
launcher: ~/bin/letta-email
launch_cwd: /Volumes/main-drive/letta-launchpad
---

# Email migration log

Fifth per-agent local-mode migration. Lightest of the set (6 memfs
files, 0 crons, 5 tool wrappers needed).

## What migrated

- Agent record (model `gpt-5.4-nano`)
- 6 system/*.md memfs files (clean — no bloat to filter)
- Local-mode patched `canonical_reference_protocol.md`
- New: `system/email_cli_recipes.md` — maps each retired Letta tool
  to a `email-agent <verb>` CLI invocation

## email-cli (built this turn)

5 bespoke email tools extracted from Letta to `letta/email-tools/`
(~470 LOC total). Wrapped in `email-cli/src/email_cli/cli.py`
(Click), installed via pipx as `email-agent` binary (not `email` —
that's a POSIX util on some systems).

Subcommands:
- `email-agent watch <thread_id>` — start watching a Gmail thread
- `email-agent unwatch <thread_id>` — stop watching
- `email-agent watch-status <thread_id>` — single-thread status
- `email-agent watch-list` — all watched threads
- `email-agent process-queue [--max-messages N]` — process TaskQueue
  label
- `email-agent health` — probe gmail-watch-service connectivity

Tools that wrapped HTTP calls to `gmail-watch-service:8000/mcp` were
patched to read URL from `GMAIL_WATCH_SERVICE_URL` env var (default
unchanged). The wrapper script sets it to the host-mapped port.

## docker-compose change

Added host port mapping for `gmail-watch-service`: `127.0.0.1:8094:8000`
so local-mode email-agent can reach the MCP endpoint from host. Picked
8094 (8092 was already used by another service).

## What did NOT migrate

- **767 archival passages** preserved on Docker side (shared archive
  used by tasks-agent too)
- 13 attached Letta tools: NOT detached from Docker (rollback path)
- 0 crons to repoint (email-agent has none)

## Two-headed runtime state

**Docker `XXX-PRE-LOCAL-email-agent`** (renamed):
- 13 tools attached — preserved for rollback
- Receives gmail-watch-service reply-received MCP notifications still
  (via `LETTA_AGENT_ID=${EMAIL_AGENT_ID}` env in docker-compose; the
  env var resolves to the agent_id which is unchanged after rename)
- Archival intact

**Local `email-agent-local`** (new, primary for user interaction):
- 0 attached Letta tools
- Uses Bash + `email-agent` CLI + `gws` + `task` + `signal`
- Reachable via `~/bin/letta-email`
- Doesn't receive direct gmail-watch-service notifications — it polls
  watch state on demand via `email-agent watch-list` etc.

## Watch-notification delivery (RESOLVED 2026-05-30)

When gmail-watch-service detects a reply to a watched thread or hits
a follow-up deadline, it now writes a row to `pa_web.task_queue` with
`source='email-watch'` IN ADDITION TO its legacy Letta API push to the
Docker agent. The local agent claims those rows via
`task queue-claim --source email-watch` — payload.event_type
discriminates reply_received / followup_needed / watch_started.

Code change: `gmail-watch-service/src/gmail_watch/services/agent_notifier.py`
— added `_write_watch_event_to_queue()`; wired into
`notify_reply_received`, `notify_followup_needed`, `notify_watch_started`.

Schema: extended `pa_web.task_queue.source` CHECK constraint to
allow 'email-watch'.

Result: local agent gets the same events the Docker agent gets,
just by polling instead of being pushed. Docker push retained for
rollback safety; can be removed once local mode soaks cleanly.

## Phase E smoke

| Test | Time | Result |
|---|---|---|
| Identity | 2.8s | ✅ "Email Agent, uses `email-agent watch` for thread watching" |
| `email-agent watch-list` via Bash | 5.2s | ✅ Reports count=1 watched thread |
| `email-agent watch-list` direct CLI | <1s | ✅ Returns real thread data through host port 8094 |

## Rollback path

1. Rename Docker agent back:
   ```bash
   curl -X PATCH http://localhost:8283/v1/agents/agent-b4928949-8012-4436-a3c7-a9e510785147 \
     -d '{"name":"email-agent"}'
   ```
2. No crons to revert (none existed).
3. gmail-watch-service notification path is unchanged throughout.

## Soak validation

- [ ] `letta-email` TUI launches cleanly, agent self-identifies
- [ ] `email-agent watch-list` returns watched threads + state
- [ ] User-driven forward → `email-agent process-queue` → row lands in
      pa_web.task_queue with source='email'
- [ ] Tasks agent picks up via `task queue-claim --source email`
      (cross-agent handoff works)
- [ ] Gmail-watch-service notification handling: when a reply arrives,
      both paths fire — Docker agent gets the MCP push AND a row
      lands in `pa_web.task_queue` source='email-watch'. Local agent
      claims via `task queue-claim --source email-watch`. Verify
      payload.event_type is one of reply_received / followup_needed /
      watch_started, and the message field is preformatted for direct
      use by the agent.
