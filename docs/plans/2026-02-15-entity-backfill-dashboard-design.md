# Entity Backfill Runner + Dashboard Design

**Date**: 2026-02-15
**Status**: Approved
**Prerequisite**: [Entity Extraction Design](2026-02-15-entity-extraction-design.md)

## Overview

A standalone Docker service that runs the full-corpus entity extraction backfill (~44,353 documents) with checkpoint-based resume and a PWA dashboard for monitoring progress and receiving push notifications.

## Architecture: Unified Service (Approach A)

Single FastAPI container (`entity-backfill-service`) that contains:
- Backfill runner (asyncio background task)
- REST API for control and status
- PWA dashboard (static files)
- Web Push notification sender

### Why This Approach

The backfill is a ~36-hour temporary operation. A single container with SQLite state minimizes moving parts. After completion, the service can be stopped and removed.

## Service Structure

```
entity-backfill-service/
├── app/
│   ├── main.py              # FastAPI app, static file serving, API routes
│   ├── runner.py             # Backfill loop (asyncio background task)
│   ├── checkpoint.py         # SQLite checkpoint read/write
│   ├── notifications.py      # Web Push subscription + send (pywebpush)
│   └── static/               # PWA files
│       ├── index.html        # Dashboard UI
│       ├── app.js            # SSE client, controls, push subscription
│       ├── style.css         # Mobile-first styles
│       ├── manifest.json     # PWA manifest
│       └── sw.js             # Service worker (push + offline)
├── data/                     # Docker volume mount point
│   └── backfill.db           # SQLite checkpoint database (created at runtime)
├── Dockerfile
└── requirements.txt
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check |
| GET | `/api/status` | Runner state, progress counts, rate, ETA, Neo4j entity stats |
| POST | `/api/start` | Load document queue from Supabase and begin processing |
| POST | `/api/pause` | Pause after current document completes |
| POST | `/api/resume` | Resume from checkpoint |
| GET | `/api/events` | SSE stream of real-time progress updates |
| GET | `/api/errors` | List of failed documents with error details |
| POST | `/api/retry-errors` | Re-queue all errored documents to pending |
| POST | `/api/push/subscribe` | Register Web Push subscription |
| GET | `/api/push/vapid-key` | Get VAPID public key for client subscription |
| GET | `/api/push/test` | Send a test notification |
| GET | `/` | Serve the PWA |

## State Management

### SQLite Schema

**`documents` table**:
| Column | Type | Purpose |
|--------|------|---------|
| file_id | TEXT PK | Google Drive file ID |
| status | TEXT | `pending`, `success`, `skipped`, `error` |
| error_message | TEXT | Error details (nullable) |
| processed_at | TIMESTAMP | When this doc was processed (nullable) |
| queue_position | INTEGER | Original position in queue |

**`runner_state` table** (single row):
| Column | Type | Purpose |
|--------|------|---------|
| state | TEXT | `idle`, `running`, `paused`, `completed` |
| started_at | TIMESTAMP | When the backfill was first started |
| paused_at | TIMESTAMP | When last paused (nullable) |
| current_position | INTEGER | Last processed queue position |

**`push_subscriptions` table**:
| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| subscription_json | TEXT | Browser push subscription object |
| created_at | TIMESTAMP | When registered |

**`vapid_keys` table** (single row):
| Column | Type | Purpose |
|--------|------|---------|
| public_key | TEXT | VAPID public key |
| private_key | TEXT | VAPID private key |

## Backfill Runner Logic

### Initialization (POST /api/start)

1. Query Supabase: `SELECT drive_file_id FROM rag.document_state ORDER BY modified_time DESC`
2. Insert all file IDs into SQLite `documents` table with status `pending`
3. Set runner_state to `running`
4. Launch asyncio background task

### Processing Loop

```
for each document where status = 'pending' (ordered by queue_position):
    1. POST http://drive-rag-service:8000/v1/entities/extract/{file_id}
       timeout: 120 seconds
    2. Record result: success/skipped/error + timestamp
    3. Emit SSE event with updated counts
    4. Check pause flag — if set, stop loop
    5. On error: log details, continue to next doc
```

### Error Handling

- **Transient errors** (timeout, 503): Mark `error`, continue. Retryable via `/api/retry-errors`.
- **Permanent errors** (400): Mark `error` with detail. Continue.
- **Service down** (connection refused): Auto-pause runner, send Web Push notification, auto-retry connection every 30 seconds until service returns, then auto-resume.

### Resume After Crash

On container restart, if runner_state is `running`, automatically resume from the last checkpoint (skip all non-`pending` documents).

## Notification Triggers

Web Push sent when:

| Trigger | Title | Body Example |
|---------|-------|-------------|
| Service unreachable | "Backfill Paused" | "drive-rag-service unreachable. 32,478/44,353 complete." |
| High error rate (>10% of last 50) | "High Error Rate" | "23% errors in last 50 docs. 165 total errors." |
| Backfill complete | "Backfill Complete" | "44,353 docs processed. 40,812 ok, 3,376 skip, 165 err." |
| Paused >5 minutes | "Backfill Still Paused" | "Paused for 12 minutes. 32,478/44,353 complete." |

## PWA Dashboard

### Layout (mobile-first)

- **Status banner**: Running/Paused/Completed indicator with color
- **Progress bar**: Percentage with doc counts (ok/skip/err breakdown)
- **Rate panel**: docs/sec, ETA, elapsed time, estimated cost so far
- **Controls**: Start / Pause / Resume / Retry Errors buttons
- **Error list**: Scrollable list of failed documents with file ID, title snippet, error message
- **Entity stats panel**: Counts by type from Neo4j (People, Projects, Orgs, Software, Generic, Relationships) — refreshed every 60 seconds server-side

### Real-time Updates

- Primary: SSE via `/api/events` — progress updates streamed live
- Fallback: Poll `/api/status` every 5 seconds if SSE disconnects
- Entity stats: Included in `/api/status`, cached server-side (60s refresh from Neo4j)

### PWA Features

- `manifest.json` for home screen installability
- Service worker for Web Push reception and basic offline (shows last-known state from localStorage)
- No framework — vanilla HTML/CSS/JS

## Docker Integration

```yaml
entity-backfill-service:
  build: ./entity-backfill-service
  container_name: entity-backfill-service
  ports:
    - "5140:8000"
  volumes:
    - entity_backfill_data:/app/data
  networks:
    - pa-internal
  depends_on:
    drive-rag-service:
      condition: service_healthy
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Port**: 5140 (external) → 8000 (internal)
**Volume**: `entity_backfill_data` for SQLite persistence
**Network**: `pa-internal` for access to drive-rag-service and Neo4j

External access via Cloudflare tunnel for phone monitoring.

## Cost Tracking

Estimated from pilot data: ~$2.62 per 1,000 documents ($116 / 44,353 docs). Dashboard shows running cost estimate based on documents processed. Actual cost should be verified against OpenAI usage dashboard.

## After Backfill

- `docker-compose stop entity-backfill-service` to stop
- Volume preserves run history
- Remove from docker-compose.yml when no longer needed
- Consider entity consolidation if name deduplication issues visible in Neo4j

## Dependencies

- `fastapi` + `uvicorn` — web framework
- `aiosqlite` — async SQLite access
- `httpx` — async HTTP client for calling drive-rag-service
- `pywebpush` — Web Push notifications
- `cryptography` — VAPID key generation
- `sse-starlette` — Server-Sent Events support
