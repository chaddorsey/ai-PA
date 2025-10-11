import asyncio
import json
from typing import Any, Dict

import pytest

from scheduler_mcp.client import SchedulerClient


class MockResponse:
    def __init__(self, status_code: int, json_data: Dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._json = json_data or {}
        self.text = json.dumps(self._json)
        self.content = self.text.encode()

    def json(self) -> Dict[str, Any]:
        return self._json


class MockClient(SchedulerClient):
    def __init__(self) -> None:  # type: ignore[override]
        pass

    async def list_jobs(self) -> Dict[str, Any]:
        return {"jobs": []}


@pytest.mark.asyncio
async def test_mock_client_list_jobs() -> None:
    client = MockClient()
    data = await client.list_jobs()
    assert "jobs" in data


