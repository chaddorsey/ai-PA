# Gmail Watch Service

A background service that monitors Gmail threads marked with "Watching" label and notifies the Email Agent via Letta when replies arrive.

## Features

- **Thread Watching**: Monitor specific Gmail threads for replies
- **Pub/Sub Integration**: Uses Google Cloud Pub/Sub for efficient change detection
- **Agent Notifications**: Sends formatted notifications to Letta Email Agent
- **MCP Tools**: Exposes tools for programmatic watch management
- **Label-Based**: Uses Gmail labels for easy visibility and management

## Quick Start

1. Set up GCP (see `docs/GCP_SETUP.md`)
2. Copy credentials to `credentials/`
3. Initialize database: `poetry run python scripts/init_db.py`
4. Start service: `docker-compose up -d gmail-watch-service`

## Usage

### Via Gmail UI

1. Add "Watching" label to any thread you want to monitor
2. Or BCC `watch@yourdomain.com` when sending to auto-label

### Via MCP Tools

The Email Agent can use these tools:

- `watch_thread` - Start monitoring a thread
- `unwatch_thread` - Stop monitoring
- `list_watched_threads` - See active watches
- `get_watch_status` - Check specific thread status

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `GCP_PROJECT_ID` | Google Cloud project ID | Required |
| `PUBSUB_SUBSCRIPTION` | Pub/Sub subscription name | `gmail-watch-pull` |
| `LETTA_BASE_URL` | Letta server URL | `http://letta:8283` |
| `LETTA_AGENT_ID` | Email Agent ID | Required |
| `PULL_INTERVAL_SECONDS` | Polling interval | `30` |
| `WATCHING_LABEL_NAME` | Gmail label to monitor | `Watching` |

## API Endpoints

- `GET /health` - Health check
- `GET /v1/status` - Current watch status
- `POST /v1/admin/force-pull` - Manually trigger poll
- `POST /v1/admin/renew-watch` - Renew Gmail watch
- `GET /mcp` - List MCP tools
- `POST /mcp` - Call MCP tool

## Architecture

```
Gmail Label Change
       ↓
Gmail Push Notification → Pub/Sub Topic
                              ↓
                    gmail-watch-service (pull)
                              ↓
                    history.list() for changes
                              ↓
                    Match against watched threads
                              ↓
                    Notify Email Agent via Letta API
```

## Development

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Run locally
poetry run uvicorn gmail_watch.main:app --reload
```
