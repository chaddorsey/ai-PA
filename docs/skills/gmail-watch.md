---
description: gmail-watch-service interaction skill. Replaces the 5 legacy gmail-watch Letta tools with a single shell CLI.
applies-to: any agent that needs to manage Gmail thread-watch subscriptions or process the watch task queue
replaces:
  - get_gmail_watch_status (Letta tool)
  - watch_gmail_thread (Letta tool)
  - unwatch_gmail_thread (Letta tool)
  - list_watched_gmail_threads (Letta tool)
  - process_email_task_queue (Letta tool, partially)
cli: scripts/gmail-watch
---

# Gmail Watch Skill

## When to use

- **After sending an important email** that needs follow-up tracking
  (`gmail-watch watch <thread-id>`) — the service notifies you when a
  reply lands.
- **To list current watches** and decide which to renew/cancel.
- **To check service health** (e.g., is the Gmail push subscription
  still valid? when does it expire?).
- **Admin** operations: force-process the task queue, renew the Gmail
  watch subscription.

This skill subsumes the 5 gmail-watch-related tools that email-agent
used. When email-agent retires (per the migration audit), these
operations move to whichever agent inherits the email-watching
function (likely tasks-agent or MC).

## Prerequisites

The `gmail-watch-service` Docker container must be running:

```bash
docker ps --filter name=gmail-watch-service --format '{{.Status}}'
# should show "Up ... (healthy)"
```

The CLI bridges to the container via `docker exec` by default. If you
add a host port mapping to the service (e.g., `8094:8000` in
docker-compose.yml), set:

```bash
export GMAIL_WATCH_BASE_URL=http://localhost:8094
```

and the CLI uses direct HTTP instead of docker exec.

## Subcommands

### Service status

```bash
gmail-watch status
```

Returns service-wide state: `watch_expiration` (when the Gmail push
subscription dies — needs renewal every 7 days), `last_pull_at` (most
recent pubsub poll), `last_notification_at` (most recent inbound
notification — sparse since the March 2026 architectural shift),
`error_count`, `last_error`.

Use to diagnose "is gmail-watch healthy" before investigating
downstream task-extraction gaps.

### List watched threads

```bash
gmail-watch list
```

Returns all currently watched threads with thread_id, subject,
follow-up settings, reply status, source (manual / auto-registered),
and watch criteria.

### One thread's status

```bash
gmail-watch thread-status <thread-id>
```

Returns whether a specific thread is being watched and the watch's
current state.

### Watch a thread

```bash
gmail-watch watch <thread-id> \
  [--subject <text>] \
  [--recipients <csv>] \
  [--followup <interval>] \
  [--context <text>] \
  [--external-only] \
  [--senders <csv-of-emails-or-@domains>]
```

`<interval>` is e.g. `3d` (3 days, default), `12h`, `1w`.

Examples:

```bash
# Basic watch with default 3-day follow-up
gmail-watch watch 19a2bb3f --subject "RFP draft review"

# Watch with context + custom interval + external-only trigger
gmail-watch watch 19a2bb3f \
  --subject "RFP draft review" \
  --context "waiting for Kate's input before submission" \
  --followup 5d \
  --external-only

# Watch only for specific sender(s)
gmail-watch watch 19a2bb3f --senders "kate@grigsby.org,@datapublishing.com"
```

### Unwatch a thread

```bash
gmail-watch unwatch <thread-id>
```

### Admin: force-process the task queue

```bash
gmail-watch process-queue
```

Manually triggers `process_email_task_queue`. Useful when the
auto-pull cron is paused or you want to flush pending notifications
immediately.

### Admin: renew the Gmail watch subscription

```bash
gmail-watch renew
```

Gmail push subscriptions auto-expire every 7 days. There's typically
a renewal cron, but if it's failed and `gmail-watch status` shows
`watch_expiration` is near or past, run this to force-renew. The
output includes the new expiration timestamp.

## Migration notes

When migrating an agent that uses the legacy gmail-watch tools:

1. **Detach** the 5 legacy tools (they don't exist in local mode).
2. **Confirm** `scripts/gmail-watch` is on the agent's `$PATH`
   (symlinked to `/opt/homebrew/bin/gmail-watch` for the runner).
3. **Update protocols**:

| Legacy Letta tool | Skill equivalent |
|---|---|
| `get_gmail_watch_status()` | `gmail-watch status` |
| `watch_gmail_thread(thread_id, ...)` | `gmail-watch watch <thread-id> [opts]` |
| `unwatch_gmail_thread(thread_id)` | `gmail-watch unwatch <thread-id>` |
| `list_watched_gmail_threads()` | `gmail-watch list` |
| `process_email_task_queue(max=N)` | `gmail-watch process-queue` (no max-N arg today; if needed, add to service) |

## Failure modes

- **"docker: command not found"** — the agent is running where docker
  isn't available. Either install docker CLI or use the host-port
  bypass via `GMAIL_WATCH_BASE_URL`.
- **`gmail-watch-service` not running** → `docker compose up -d
  gmail-watch-service` and retry.
- **`error_count` keeps climbing** — gmail-watch's pubsub puller is
  failing repeatedly. Inspect `docker logs gmail-watch-service` for
  Google API errors (Gmail backend transients, OAuth refresh issues).

## Validation history

- **2026-05-25** — Shipped + smoke-tested:
  - `status` returned full health record (watch_expiration 2026-05-27,
    last_pull_at 2026-05-26T03:01, error_count 280, no recent
    notifications matching today's gmail-watch diagnostic).
  - `list` returned 1 watched thread ("Concord Consortium reconnect",
    March 25, manual source, 3d followup interval).
  - watch/unwatch paths constructed but not exercised against
    production threads for safety.
