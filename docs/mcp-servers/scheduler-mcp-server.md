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

- `scheduler_list_jobs` - List jobs with optional filtering (status, category, created_by)
- `scheduler_search_jobs` - Semantic search using vector embeddings
- `scheduler_get_job` - Fetch a single job by ID
- `scheduler_create_job` - Create a new scheduled job
- `scheduler_update_job` - Update an existing job
- `scheduler_delete_job` - Cancel a scheduled job
- `scheduler_list_executions` - List execution history for a job
- `scheduler_get_execution` - Retrieve a specific execution record

### Search and Filtering

The `scheduler_list_jobs` tool supports filtering:
- `status_filter`: Filter by status (scheduled|paused|cancelled|completed)
- `category_filter`: Filter by category
- `created_by_filter`: Filter by creator identifier

The `scheduler_search_jobs` tool provides semantic search:
- `query_text`: Natural language query for semantic similarity search
- `limit`: Maximum number of results (1-100, default: 10)
- `min_score`: Minimum similarity score (0.0-1.0, default: 0.5)
- `status_filter`: Optional status filter
- `category_filter`: Optional category filter

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


