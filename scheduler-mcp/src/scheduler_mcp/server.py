"""Scheduler MCP server implementation using FastMCP."""

from __future__ import annotations

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from scheduler_mcp.client import SchedulerClient
from scheduler_mcp.tools import ExecutionResponseModel, JobCreateModel, JobResponseModel, JobUpdateModel
from scheduler_mcp.settings import settings


async def _get_client() -> SchedulerClient:
    return SchedulerClient(base_url=settings.scheduler_base_url, api_key=settings.api_key)


def create_mcp_server() -> FastMCP:
    mcp = FastMCP("scheduler-tools")

    @mcp.tool(description="List jobs managed by the scheduler service.")
    async def scheduler_list_jobs():
        client = await _get_client()
        return await client.list_jobs()

    @mcp.tool(description="Fetch a single job by id.")
    async def scheduler_get_job(job_id: str):
        client = await _get_client()
        response = await client.get_job(job_id)
        return JobResponseModel(**response).model_dump()

    @mcp.tool(description="Create a new scheduled job.")
    async def scheduler_create_job(data: JobCreateModel):
        client = await _get_client()
        response = await client.create_job(data.model_dump())
        return JobResponseModel(**response).model_dump()

    @mcp.tool(description="Update an existing job.")
    async def scheduler_update_job(job_id: str, data: JobUpdateModel):
        client = await _get_client()
        response = await client.update_job(job_id, data.model_dump(exclude_none=True))
        return JobResponseModel(**response).model_dump()

    @mcp.tool(description="Cancel a scheduled job.")
    async def scheduler_delete_job(job_id: str):
        client = await _get_client()
        await client.delete_job(job_id)
        return {"status": "deleted", "job_id": job_id}

    @mcp.tool(description="List execution history for a job.")
    async def scheduler_list_executions(job_id: str):
        client = await _get_client()
        return await client.list_executions(job_id)

    @mcp.tool(description="Retrieve a specific execution record.")
    async def scheduler_get_execution(execution_id: str):
        client = await _get_client()
        response = await client.get_execution(execution_id)
        return ExecutionResponseModel(**response).model_dump()

    return mcp


def create_app() -> FastAPI:
    server = create_mcp_server()
    app = server.streamable_http_app()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": settings.app_name}

    return app


