"""Bridge layer — wraps notebooklm-py's async client for sync CLI use."""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
from typing import Any

from notebooklm_cli.validate import validate_path

logger = logging.getLogger(__name__)

# Method routing table: group -> sub-API attribute on NotebookLMClient
_API_MAP = {
    "notebook": "notebooks",
    "source": "sources",
    "artifact": "artifacts",
    "chat": "chat",
    "research": "research",
    "note": "notes",
}

# Path-bearing params that need traversal validation before dispatch
_PATH_PARAMS = ("filePath", "outputPath")


def _camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case: notebookId -> notebook_id."""
    import re
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def serialize(obj: Any) -> Any:
    """Convert dataclasses, lists, enums to JSON-safe dicts."""
    if obj is None:
        return None
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: serialize(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if hasattr(obj, "value") and hasattr(type(obj), "__mro__"):
        # Enum-like: has .value attribute
        import enum
        if isinstance(obj, enum.Enum):
            return obj.value
    return obj


def call(method: str, params: dict) -> dict:
    """Sync entry point. Route method to notebooklm-py client."""
    try:
        return asyncio.run(_async_call(method, params))
    except Exception as e:
        logger.error("Bridge error: %s", e)
        return {"status": "error", "error_message": str(e)}


async def _create_client():
    """Create NotebookLMClient from storage. Separated for testability."""
    from pathlib import Path

    from notebooklm.auth import AuthTokens
    from notebooklm.client import NotebookLMClient

    storage_path = os.environ.get("NOTEBOOKLM_STORAGE")
    auth = await AuthTokens.from_storage(
        path=Path(storage_path) if storage_path else None
    )
    return NotebookLMClient(auth)


async def _async_call(method: str, params: dict) -> dict:
    """Resolve group.action to client sub-API method, call it, serialize."""
    parts = method.split(".", 1)
    if len(parts) != 2:
        return {"status": "error", "error_message": f"Invalid method format: {method}"}

    group, action = parts
    api_attr = _API_MAP.get(group)
    if not api_attr:
        return {"status": "error", "error_message": f"Unknown group: {group}"}

    # Validate file paths before creating client
    for path_field in _PATH_PARAMS:
        if path_field in params:
            err = validate_path(params[path_field])
            if err:
                return {"status": "error", "error_message": f"{path_field}: {err}"}

    client = await _create_client()
    async with client:
        api = getattr(client, api_attr)
        method_name = action.replace("-", "_")
        fn = getattr(api, method_name, None)
        if fn is None:
            return {"status": "error", "error_message": f"Unknown method: {group}.{action}"}

        # Convert camelCase param names to snake_case for notebooklm-py
        snake_params = {_camel_to_snake(k): v for k, v in params.items()}

        # Attempt call with one auth refresh retry
        try:
            result = await fn(**snake_params)
        except ValueError as e:
            if "expired" in str(e).lower() or "invalid" in str(e).lower():
                logger.info("Auth expired, attempting refresh...")
                await client.refresh_auth()
                result = await fn(**snake_params)
            else:
                raise

        return {"status": "ok", "result": serialize(result)}
