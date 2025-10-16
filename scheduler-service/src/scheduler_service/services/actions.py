"""External action execution services."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import httpx

from scheduler_service.services.logs import logger, job_logger, execution_logger, action_logger
from scheduler_service.settings import settings


class ActionExecutionError(Exception):
    """Raised when action execution fails."""


async def execute_http_action(action_config: Dict[str, Any]) -> Dict[str, Any]:
    method = action_config.get("method", "GET").upper()
    url = action_config.get("url")
    if not url:
        raise ActionExecutionError("HTTP action requires 'url'")

    headers = action_config.get("headers", {})
    timeout_seconds = action_config.get("timeout", settings.http_timeout_seconds)
    retries = action_config.get("retries", settings.http_retries)
    body = action_config.get("body")
    json_payload = action_config.get("json")

    started_at = datetime.utcnow()
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for attempt in range(1, retries + 2):
            try:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    content=body,
                    json=json_payload,
                )
                logger.info(
                    "HTTP action executed",
                    url=url,
                    method=method,
                    status_code=response.status_code,
                    attempt=attempt,
                )
                response.raise_for_status()
                try:
                    data = response.json()
                except json.JSONDecodeError:
                    data = {"text": response.text}
                return {
                    "status": "success",
                    "output": {
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "data": data,
                        "started_at": started_at.isoformat(),
                        "completed_at": datetime.utcnow().isoformat(),
                    },
                }
            except Exception as exc:
                logger.warning(
                    "HTTP action failed",
                    url=url,
                    method=method,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt > retries:
                    raise ActionExecutionError(str(exc)) from exc
                await asyncio.sleep(settings.http_retry_backoff * attempt)


def _resolve_allowlisted_script(script: str) -> Path:
    allow_dir = Path(settings.allowlist_script_dir).resolve()
    script_path = (allow_dir / script).resolve()
    if allow_dir not in script_path.parents:
        raise ActionExecutionError("Script must reside in allow-listed directory")
    if not script_path.exists():
        raise ActionExecutionError(f"Script not found: {script_path}")
    return script_path


async def execute_script_action(action_config: Dict[str, Any]) -> Dict[str, Any]:
    script = action_config.get("script")
    if not script:
        raise ActionExecutionError("Script action requires 'script'")

    script_path = _resolve_allowlisted_script(script)

    args = [str(arg) for arg in action_config.get("args", [])]
    env = {**settings.script_env_defaults, **action_config.get("env", {})}

    started_at = datetime.utcnow()
    process = await asyncio.create_subprocess_exec(
        str(script_path),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout_bytes, stderr_bytes = await process.communicate()
    stdout_text = stdout_bytes.decode().strip()
    stderr_text = stderr_bytes.decode().strip()
    completed_at = datetime.utcnow()

    if process.returncode != 0:
        raise ActionExecutionError(
            json.dumps(
                {
                    "returncode": process.returncode,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                }
            )
        )

    return {
        "status": "success",
        "output": {
            "returncode": process.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
        },
    }


async def execute_agent_message_action(action_config: Dict[str, Any]) -> Dict[str, Any]:
    """Send message to Letta agent via REST API."""
    agent_id = action_config.get("agent_id")
    message = action_config.get("message")
    
    if not agent_id:
        raise ActionExecutionError("agent_message action requires 'agent_id'")
    if not message:
        raise ActionExecutionError("agent_message action requires 'message'")
    
    # Get Letta API URL from settings
    letta_url = settings.letta_callback_url
    if not letta_url:
        logger.warning("LETTA_CALLBACK_URL not configured, logging message instead")
        logger.info(
            "Agent message (would send to Letta)",
            agent_id=agent_id,
            message=message,
            category=action_config.get("category"),
        )
        return {
            "status": "success",
            "output": {
                "method": "log_only",
                "agent_id": agent_id,
                "message": message,
                "note": "LETTA_CALLBACK_URL not configured",
            },
        }
    
    # Construct Letta API endpoint
    # Supports multiple placeholder formats:
    # - %agent_id% (preferred)
    # - {agent_id} (fallback)
    # - URL-encoded versions
    # Convert Pydantic URL to string
    letta_url_str = str(letta_url)
    
    # Handle various placeholder formats
    if "%agent_id%" in letta_url_str:
        # Preferred format: %agent_id%
        url = letta_url_str.replace("%agent_id%", agent_id)
    elif "%7Bagent_id%7D" in letta_url_str:
        # URL-encoded {agent_id}
        url = letta_url_str.replace("%7Bagent_id%7D", agent_id)
    elif "{agent_id}" in letta_url_str:
        # Plain text {agent_id}
        url = letta_url_str.replace("{agent_id}", agent_id)
    else:
        # No template, construct full URL
        base_url = letta_url_str.rstrip('/')
        # If base_url already has /api/agents or /v1/agents, don't add it again
        if "/agents" in base_url:
            url = f"{base_url}/{agent_id}/messages"
        else:
            # Assume we need to add the full path
            url = f"{base_url}/v1/agents/{agent_id}/messages"
    
    # Send message to Letta
    # Letta API expects: {"messages": [{"role": "user"|"system", "content": "text"}]}
    started_at = datetime.utcnow()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={
                    "messages": [
                        {
                            "role": "system",  # Scheduler messages come as system messages
                            "content": message,
                        }
                    ]
                },
            )
            response.raise_for_status()
            
            logger.info(
                "Agent message delivered",
                agent_id=agent_id,
                url=url,
                status_code=response.status_code,
            )
            
            return {
                "status": "success",
                "output": {
                    "agent_id": agent_id,
                    "message": message,
                    "status_code": response.status_code,
                    "started_at": started_at.isoformat(),
                    "completed_at": datetime.utcnow().isoformat(),
                },
            }
    
    except Exception as exc:
        logger.error(
            "Failed to deliver agent message",
            agent_id=agent_id,
            url=url,
            error=str(exc),
        )
        raise ActionExecutionError(f"Failed to send message to agent {agent_id}: {exc}") from exc


ACTION_EXECUTORS = {
    "http": execute_http_action,
    "webhook": execute_http_action,
    "script": execute_script_action,
    "agent_message": execute_agent_message_action,
}


async def execute_action(action_type: str, action_config: Dict[str, Any]) -> Dict[str, Any]:
    executor = ACTION_EXECUTORS.get(action_type)
    if not executor:
        raise ActionExecutionError(f"Unsupported action type: {action_type}")

    logger.info("Executing action", action_type=action_type)
    return await executor(action_config)


