# Slack Analytics Export Service - Operations

## Overview
Standalone FastAPI service (`slack-analytics-mcp-server`) that triggers Slack analytics CSV exports via Playwright/Chromium automation. It exposes:
- `GET /health` – basic health and prerequisites
- `POST /trigger-export` – starts an export for a given date range

## Configuration
- `SLACK_ANALYTICS_SCRIPT_PATH` (default `/app/slack_analytics_with_dates.py`)
- `SLACK_ANALYTICS_AUTH_FILE` (default `/app/slack_auth_state.json`)
- `SLACK_ANALYTICS_SCREENSHOT_DIR` (default `/app/slack_analytics_screenshots`)
- `SLACK_ANALYTICS_TIMEOUT` (default `120`)
- `SLACK_ANALYTICS_HEADLESS` (default `true`)

Compose service (`docker-compose.yml`):
- Service name: `slack-analytics-mcp-server`
- Internal port: 8087 (host bind default 8097)
- Volumes: mount `slack_auth_state.json`, screenshots dir

## Build and Run
```bash
docker compose build slack-analytics-mcp-server
docker compose up -d slack-analytics-mcp-server
```

Verify:
```bash
curl http://localhost:8097/health
```

Trigger example:
```bash
curl -X POST http://localhost:8097/trigger-export \
  -H "Content-Type: application/json" \
  -d '{"analytics_type":"channels","days_ago":3,"date_range_days":1}'
```

## Letta Tool Integration
Registration script: `letta/register_slack_analytics.py`
- Tool `trigger_slack_analytics_export` targets:
  - `SLACK_ANALYTICS_BASE_URL` env var OR
  - default `http://slack-analytics-mcp-server:8087`
- For local host testing:
  - `export SLACK_ANALYTICS_BASE_URL=http://localhost:8097`

## Monitoring and Logs
- Container logs: `docker logs -f slack-analytics-mcp-server`
- Screenshots: `${SLACK_ANALYTICS_SCREENSHOT_DIR}`
- Timeouts configurable via `SLACK_ANALYTICS_TIMEOUT`

## Troubleshooting
- Health degraded (`script:false`): check script path env and image contents
- Auth missing (`auth_file:false`): mount `slack_auth_state.json`
- Playwright/Chromium errors: ensure dependencies installed (image includes `playwright install-deps chromium`)
- Network/Slack failures: retry; confirm workspace access

## Verification Checklist
- Health returns `{"status":"healthy","script":true,"auth_file":true}`
- Trigger returns `success:true` and date range
- A CSV appears in Slack within ~1–2 minutes (use the provided Letta tools to list/download)

## Change Log
- Port mapping set to `8097:8087` to avoid conflict with `scheduler-service`


