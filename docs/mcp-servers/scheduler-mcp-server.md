# Scheduler MCP Server

## Overview

The Scheduler MCP server exposes the scheduling service using the official Model Context Protocol Python SDK. It provides streamable HTTP tools for Letta agents and includes a health endpoint via FastMCP custom routes.

- **Service Name**: `scheduler-mcp`
- **Language**: Python 3.12+
- **Framework**: FastMCP (streamable HTTP transport)
- **Transport**: ASGI server exposing `/mcp`
- **Default Port**: `8088`
- **Health Endpoint**: `GET /health`
- **MCP Endpoint**: `POST /mcp`

## Key Tools

Registered tools mirror the REST API:

- `scheduler_list_jobs`
- `scheduler_get_job`
- `scheduler_create_job`
- `scheduler_update_job`
- `scheduler_delete_job`
- `scheduler_list_executions`
- `scheduler_get_execution`

## Running Locally

```bash
cd scheduler-mcp
poetry install
poetry run uvicorn scheduler_mcp.app:create_app --factory --port 8088
```

## Docker Compose Integration

- Ensure the container runs with Python ≥3.10 image (e.g., `python:3.12-slim`).
- Expose port `8088` and attach to the same network as Letta and the scheduler service.
- Let other containers access the service via `http://scheduler-mcp:8088`.
- Environment variables:
  - `SCHEDULER_BASE_URL` (default `http://scheduler-service:8087/v1`)
  - `SCHEDULER_API_KEY` (optional shared secret)
- Service depends on `scheduler-service` for REST backend access.

## Dependencies

- `mcp` (official SDK)
- `fastapi`, `uvicorn`
- Shared scheduler REST client and settings modules


