# letta-local-runner

Host-side bridge between Docker-resident services (scheduler-service,
slackbot, gmail-watch, work-packet-assembler) and host-resident
`letta --backend local` invocations.

## Why

Letta is moving to local mode (per docs.letta.com). Local-mode agents
live in `~/.letta/lc-local-backend/` on the host. The rest of our stack
runs in Docker and can't reach the host's `letta` binary directly.

This service is the bridge. It does three things:

1. Accepts HTTP `POST /invoke` from any Docker service over
   `host.docker.internal:8920`.
2. Forks `letta --backend local --agent <id> -p "<message>"` on the
   host, captures stdout/stderr/exit.
3. Serializes invocations per-agent so concurrent callers from
   scheduler-service + Slackbot + pa-web-ui can't race on Letta's
   local backend (a real bug as of letta-code 0.26.1 — empirically
   verified 2026-05-25).

## Shelf life

This is a stopgap. Expected useful life: 6-18 months. Retire when
Letta either:
- Adds per-conversation locking + retry-on-conflict inside the binary
- Ships a real `letta server --backend local` HTTP mode

Design optimizes for replaceability, not durability. ~150 lines total.

## Usage

```bash
# from any Docker service on the pa-internal network
curl -X POST http://host.docker.internal:8920/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-local-d06e9bf7-1a75-4558-a1fe-1454bb5b2ec7",
    "message": "Generate today's briefing.",
    "conversation_id": "cron-daily-briefing",
    "timeout": 600
  }'
```

Response:
```json
{
  "status": "success",
  "agent_response": "Today's briefing: ...",
  "duration_seconds": 47.2,
  "letta_exit": 0,
  "retried": false,
  "log_path": "/Users/.../Logs/letta-local-runner/2026-05-25.jsonl"
}
```

## Install

```bash
cd letta-local-runner
poetry install
cp launchd/com.ai-pa.letta-local-runner.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ai-pa.letta-local-runner.plist
```

## Architecture

```
Docker services (scheduler-service, slackbot, ...)
  │
  │ HTTP POST host.docker.internal:8920/invoke
  ▼
letta-local-runner (host, launchd, FastAPI/uvicorn)
  │
  │ per-agent asyncio.Lock acquired
  │ subprocess.run([letta, --backend, local, --agent, <id>, ...])
  │ race-loss detection (exit 0 + empty stdout → retry once)
  ▼
letta --backend local (host process)
  │
  ▼
~/.letta/lc-local-backend/memfs/<agent-id>/memory/
```

## Health

```
GET /health   → {"status": "healthy", "active": 2, "version": "0.1.0"}
GET /status   → {"locks": {...}, "recent": [...]}
```

## Caveats

- Single uvicorn worker (asyncio.Lock requires single-process). Don't
  scale workers > 1 without switching to a multi-process lock.
- Locks are in-memory only. Process restart drops in-flight state;
  in-flight requests error and callers retry.
- Race-loss retry is heuristic (exit 0 + empty stdout). Could falsely
  retry legitimately-empty responses, but cost is one extra LLM call.

## Replacement criteria

Retire this service when EITHER of these is true:
- Letta-code's local backend stops dropping output on concurrent
  same-agent invocations. (Test: run two `letta --backend local`
  processes simultaneously against same agent; both should produce
  output.)
- Letta ships `letta server --backend local` exposing HTTP. Then
  scheduler-service POSTs directly to that, no bridge needed.
