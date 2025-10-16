"""HTTP client for interacting with the scheduler service REST API."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from scheduler_mcp.settings import settings


class SchedulerClientError(Exception):
    """Raised when scheduler client encounters an error."""


class SchedulerClient:
    """Thin wrapper around scheduler REST API with retry and error handling."""

    def __init__(self, base_url: str | None = None, api_key: Optional[str] = None) -> None:
        self.base_url = base_url or str(settings.scheduler_base_url).rstrip("/")
        self.api_key = api_key or settings.api_key
        self._client = httpx.AsyncClient(timeout=settings.timeout_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    @retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=5), stop=stop_after_attempt(settings.request_retries))
    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self.base_url}{path}"
        response = await self._client.request(method, url, headers=self._headers(), **kwargs)
        response.raise_for_status()
        return response

    async def list_jobs(
        self,
        status_filter: str = None,
        created_by_filter: str = None,
        category_filter: str = None,
    ) -> Dict[str, Any]:
        try:
            # Build query parameters
            params = {}
            if status_filter:
                params["status_filter"] = status_filter
            if created_by_filter:
                params["created_by_filter"] = created_by_filter
            if category_filter:
                params["category_filter"] = category_filter
            
            response = await self._request("GET", "/jobs", params=params)
            return response.json()
        except RetryError as exc:  # pragma: no cover
            raise SchedulerClientError("Scheduler service unavailable after retries") from exc
        except httpx.HTTPStatusError as exc:
            raise SchedulerClientError(f"Failed to list jobs: {exc.response.text}") from exc

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        try:
            response = await self._request("GET", f"/jobs/{job_id}")
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise SchedulerClientError(f"Job '{job_id}' not found") from exc
            raise SchedulerClientError(f"Failed to retrieve job '{job_id}': {exc.response.text}") from exc

    async def create_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = await self._request("POST", "/jobs", json=payload)
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise SchedulerClientError(_format_error("create job", exc)) from exc

    async def update_job(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = await self._request("PATCH", f"/jobs/{job_id}", json=payload)
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise SchedulerClientError(_format_error("update job", exc)) from exc

    async def delete_job(self, job_id: str) -> Dict[str, Any]:
        try:
            response = await self._request("DELETE", f"/jobs/{job_id}")
            if response.content:
                return response.json()
            return {"status": "cancelled", "job_id": job_id}
        except httpx.HTTPStatusError as exc:
            raise SchedulerClientError(_format_error("delete job", exc)) from exc

    async def list_executions(self, job_id: str) -> Dict[str, Any]:
        try:
            response = await self._request("GET", f"/jobs/{job_id}/executions")
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise SchedulerClientError(_format_error("list executions", exc)) from exc

    async def get_execution(self, execution_id: str) -> Dict[str, Any]:
        try:
            response = await self._request("GET", f"/jobs/executions/{execution_id}")
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise SchedulerClientError(_format_error("get execution", exc)) from exc


def _format_error(action: str, exc: httpx.HTTPStatusError) -> str:
    detail: str
    try:
        data = exc.response.json()
        detail = json.dumps(data, indent=2)
    except Exception:
        detail = exc.response.text
    return f"Failed to {action}: HTTP {exc.response.status_code}. Response: {detail}"


