# Scheduler MCP Server

This MCP server exposes the scheduler service REST API as Model Context Protocol tools.

## Development

```bash
cd scheduler-mcp
poetry install
poetry run uvicorn scheduler_mcp.server:create_app --reload --port 8088
```

## Tools
- `scheduler_list_jobs`
- `scheduler_get_job`
- `scheduler_create_job`
- `scheduler_update_job`
- `scheduler_delete_job`
- `scheduler_list_executions`
- `scheduler_get_execution`


