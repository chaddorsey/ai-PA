# Scheduler Service

Dedicated scheduling and reminder service for the AI personal assistant ecosystem. Built with FastAPI, APScheduler, and PostgreSQL (pgvector) to support durable, searchable reminders and automation jobs.

## Features (planned)
- REST API for job CRUD, triggers, and archive search
- MCP integration for Letta agents
- Embedding-based semantic search over reminders/action logs
- External action execution (HTTP/webhook/script) with result ingestion
- Structured logging, health checks, and metrics

## Development Quickstart
```bash
poetry install
poetry run uvicorn scheduler_service.main:app --reload
```

## Testing
```bash
poetry run pytest
```


