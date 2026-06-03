# letta-push-receiver

HTTP → warm-subprocess bridge for local-mode Letta agents.

## What it does

Producers (slackbot, gmail-watch-service, scheduler-service crons,
granola-poller, task-completion-service) POST `/push` with a target
agent + prompt. The receiver writes the prompt to the agent's warm
subprocess stdin via stream-json, and returns 202 immediately
(fire-and-forget).

Each agent has a long-running subprocess kept warm across pushes.
First push spawns; subsequent pushes reuse the conversation and
memfs context (prompt-cache stays warm).

## Why

Local-mode Letta agents have no HTTP server. Producers can't POST
directly. Substitute: a host-side HTTP daemon that dispatches via
stdin to per-agent warm subprocesses.

## Latency

- Warm path: ~3-10 sec end-to-end (LLM call + tool exec)
- Cold path (first push to an agent, spawns + memfs load): ~10-20 sec
- Receiver overhead: <100ms

## Configuration

Hard-coded fleet mapping in `config.py` (six agents: tasks, email,
pulse, docs, calendar, mc). Override host/port via env:
- `LETTA_PUSH_RECEIVER_HOST` (default 127.0.0.1)
- `LETTA_PUSH_RECEIVER_PORT` (default 8099)
- `LETTA_PUSH_RECEIVER_LOG_DIR` (default /Volumes/main-drive/ai-PA/logs/health)

## API

### POST /push

```json
{
  "agent": "email",           // owner agent slug (optional if source given)
  "source": "email",          // optional; used for auto-routing
  "source_ref": "email-abc",  // optional; for producer dedup tracking
  "prompt": "Process pa_web.task_queue ...",
  "priority": "normal"        // "normal" | "urgent"
}
```

Returns 202 `{"status": "accepted", "agent": "email", "pid": 12345, ...}`.

Source-based routing: if `agent` is omitted, the receiver routes by
`source` per the `DEFAULT_SOURCE_ROUTING` table:

| source | owner agent |
|---|---|
| email, email-watch | email |
| slack | pulse |
| drive, meeting, meeting_marker, google-docs-comment, docs-meeting | docs |
| mc-completion | mc |

### GET /health

`{"status": "ok", "service": "letta-push-receiver"}` — for launchd
healthcheck.

### GET /status

Warm pool inventory: which agents are warm, pids, uptimes, push counts.

## Run

```bash
# After install via pipx:
letta-push-receiver
```

Or via launchd: `~/Library/LaunchAgents/com.ai-pa.letta-push-receiver.plist`
