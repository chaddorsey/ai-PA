"""HTTP client for interacting with the scheduler service REST API."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

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
        include_archived: bool = False,
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
            if include_archived:
                params["include_archived"] = "true"
            
            response = await self._request("GET", "/jobs", params=params)
            return response.json()
        except RetryError as exc:  # pragma: no cover
            raise SchedulerClientError(
                "Scheduler service unavailable after retries. "
                "The scheduler service may be down or not responding. "
                "Please check the service status and try again."
            ) from exc
        except httpx.HTTPStatusError as exc:
            error_detail = exc.response.text
            try:
                error_json = exc.response.json()
                if "detail" in error_json:
                    error_detail = error_json["detail"]
            except:
                pass
            raise SchedulerClientError(
                f"Failed to list jobs: {error_detail}. "
                f"Status code: {exc.response.status_code}. "
                f"Check your filter parameters (status_filter, category_filter, created_by_filter) are valid."
            ) from exc

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        try:
            response = await self._request("GET", f"/jobs/{job_id}")
            return response.json()
        except httpx.HTTPStatusError as exc:
            error_detail = exc.response.text
            try:
                error_json = exc.response.json()
                if "detail" in error_json:
                    error_detail = error_json["detail"]
            except:
                pass
            if exc.response.status_code == 404:
                raise SchedulerClientError(
                    f"Job not found: '{job_id}'. "
                    f"The job may have been deleted, or the ID is incorrect. "
                    f"Use scheduler_list_jobs() or scheduler_search_jobs() to find valid job IDs."
                ) from exc
            raise SchedulerClientError(
                f"Failed to retrieve job '{job_id}': {error_detail}. "
                f"Status code: {exc.response.status_code}. "
                f"Ensure the job_id is a valid UUID format."
            ) from exc

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

    async def batch_archive_jobs(self, job_ids: List[str]) -> Dict[str, Any]:
        """Archive multiple jobs at once."""
        try:
            response = await self._request("POST", "/jobs/batch/archive", json=job_ids)
            return response.json()
        except RetryError as exc:  # pragma: no cover
            raise SchedulerClientError(
                "Scheduler service unavailable after retries. "
                "The scheduler service may be down or not responding. "
                "Please check the service status and try again."
            ) from exc
        except httpx.HTTPStatusError as exc:
            error_detail = exc.response.text
            try:
                error_json = exc.response.json()
                if "detail" in error_json:
                    error_detail = error_json["detail"]
            except:
                pass
            raise SchedulerClientError(
                f"Failed to batch archive jobs: {error_detail}. "
                f"Status code: {exc.response.status_code}. "
                f"Ensure all job_ids are valid UUIDs. Use scheduler_list_jobs() to find valid job IDs."
            ) from exc

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

    async def search_jobs(
        self,
        query_text: str,
        limit: int = 10,
        min_score: float = 0.5,
        status_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        include_archived: bool = False,
    ) -> Dict[str, Any]:
        """Search jobs using semantic similarity on embeddings."""
        try:
            params = {
                "query_text": query_text,
                "limit": limit,
                "min_score": min_score,
            }
            if status_filter:
                params["status_filter"] = status_filter
            if category_filter:
                params["category_filter"] = category_filter
            if include_archived:
                params["include_archived"] = "true"
            
            response = await self._request("GET", "/jobs/search", params=params)
            return response.json()
        except RetryError as exc:  # pragma: no cover
            raise SchedulerClientError(
                "Scheduler service unavailable after retries. "
                "The scheduler service may be down or not responding. "
                "Please check the service status and try again."
            ) from exc
        except httpx.HTTPStatusError as exc:
            error_detail = exc.response.text
            try:
                error_json = exc.response.json()
                if "detail" in error_json:
                    error_detail = error_json["detail"]
            except:
                pass
            raise SchedulerClientError(
                f"Failed to search jobs: {error_detail}. "
                f"Status code: {exc.response.status_code}. "
                f"Check your search parameters (query_text, status_filter, category_filter) are valid. "
                f"Valid status_filter values: scheduled, active, paused, cancelled, completed, archived, or 'all'."
            ) from exc


def _format_error(action: str, exc: httpx.HTTPStatusError) -> str:
    """Format error messages with helpful guidance for LLMs."""
    detail: str
    try:
        data = exc.response.json()
        if isinstance(data, dict) and "detail" in data:
            detail = data["detail"]
        else:
            detail = json.dumps(data, indent=2)
    except Exception:
        detail = exc.response.text or f"HTTP {exc.response.status_code}"
    
    # Add context-specific guidance
    guidance = ""
    if exc.response.status_code == 400:
        guidance = " Check your input parameters match the expected schema."
    elif exc.response.status_code == 404:
        guidance = " The resource may not exist. Verify the ID is correct."
    elif exc.response.status_code >= 500:
        guidance = " This appears to be a server error. Please try again or check service logs."
    
    return f"Failed to {action}: {detail}.{guidance} HTTP status: {exc.response.status_code}"


