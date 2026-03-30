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
    """Send message to a Letta agent.

    Routing:
      - route="lettabot" (recommended): Routes through a LettaBot instance's
        OpenAI-compatible API. The agent gets full client-side tools (Bash, Read,
        Write, Edit, Glob, Grep, Task, etc.) in addition to server-side tools.
        Requires lettabot_url and lettabot_api_key in config.
      - route="letta" (default): Routes directly to the Letta server API.
        The agent gets server-side tools only (no Bash/Read/Write).

    Config fields:
      agent_id:         Letta agent UUID (required for route=letta)
      message:          Message content (required)
      role:             "system" or "user" (default "system")
      route:            "lettabot" or "letta" (default "letta")
      lettabot_url:     LettaBot base URL (e.g. http://host.docker.internal:8080)
      lettabot_api_key: LettaBot API key
      timeout:          Request timeout in seconds (default from settings)
    """
    message = action_config.get("message")
    if not message:
        raise ActionExecutionError("agent_message action requires 'message'")

    role = action_config.get("role", "system")
    timeout_seconds = action_config.get("timeout", settings.agent_message_timeout_seconds)
    started_at = datetime.utcnow()

    # Auto-resolve routing: check if the agent has a LettaBot endpoint registered.
    # Explicit route in config overrides auto-detection.
    route = action_config.get("route")
    if route is None:
        agent_id = action_config.get("agent_id", "")
        lb_entry = settings.lettabot_agents.get(agent_id)
        if lb_entry:
            route = "lettabot"
            # Inject registry values as defaults (config overrides registry)
            action_config.setdefault("lettabot_url", lb_entry.get("url"))
            action_config.setdefault("lettabot_api_key", lb_entry.get("api_key"))
            logger.info("Auto-routed agent via LettaBot", agent_id=agent_id)
        else:
            route = "letta"

    if route == "lettabot":
        return await _send_via_lettabot(action_config, message, role, timeout_seconds, started_at)
    else:
        return await _send_via_letta(action_config, message, role, timeout_seconds, started_at)


async def _send_via_lettabot(
    config: Dict[str, Any], message: str, role: str,
    timeout_seconds: float, started_at: datetime,
) -> Dict[str, Any]:
    """Route through LettaBot's OpenAI-compatible API (full tool access)."""
    lettabot_url = config.get("lettabot_url")
    lettabot_api_key = config.get("lettabot_api_key")

    if not lettabot_url:
        raise ActionExecutionError(
            "route=lettabot requires 'lettabot_url' "
            "(e.g. http://host.docker.internal:8080)"
        )

    url = f"{lettabot_url.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if lettabot_api_key:
        headers["Authorization"] = f"Bearer {lettabot_api_key}"

    payload = {
        "messages": [{"role": role, "content": message}],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            logger.info(
                "Agent message delivered via LettaBot",
                lettabot_url=lettabot_url,
                status_code=response.status_code,
            )

            # Extract response content
            try:
                data = response.json()
                agent_response = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
            except (json.JSONDecodeError, IndexError, KeyError):
                agent_response = ""

            return {
                "status": "success",
                "output": {
                    "route": "lettabot",
                    "message": message,
                    "agent_response": agent_response[:500],
                    "status_code": response.status_code,
                    "started_at": started_at.isoformat(),
                    "completed_at": datetime.utcnow().isoformat(),
                },
            }

    except Exception as exc:
        logger.error(
            "Failed to deliver agent message via LettaBot",
            lettabot_url=lettabot_url,
            error=str(exc),
        )
        raise ActionExecutionError(
            f"Failed to send message via LettaBot: {exc}"
        ) from exc


async def _send_via_letta(
    config: Dict[str, Any], message: str, role: str,
    timeout_seconds: float, started_at: datetime,
) -> Dict[str, Any]:
    """Route directly to Letta server API (server-side tools only)."""
    agent_id = config.get("agent_id")
    if not agent_id:
        raise ActionExecutionError(
            "agent_message with route=letta requires 'agent_id'"
        )

    letta_url = settings.letta_callback_url
    if not letta_url:
        logger.warning("LETTA_CALLBACK_URL not configured, logging message instead")
        return {
            "status": "success",
            "output": {
                "method": "log_only",
                "route": "letta",
                "agent_id": agent_id,
                "message": message,
                "note": "LETTA_CALLBACK_URL not configured",
            },
        }

    letta_url_str = str(letta_url)

    if "%agent_id%" in letta_url_str:
        url = letta_url_str.replace("%agent_id%", agent_id)
    elif "%7Bagent_id%7D" in letta_url_str:
        url = letta_url_str.replace("%7Bagent_id%7D", agent_id)
    elif "{agent_id}" in letta_url_str:
        url = letta_url_str.replace("{agent_id}", agent_id)
    else:
        base_url = letta_url_str.rstrip("/")
        if "/agents" in base_url:
            url = f"{base_url}/{agent_id}/messages"
        else:
            url = f"{base_url}/v1/agents/{agent_id}/messages"

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                url,
                json={"messages": [{"role": role, "content": message}]},
            )
            response.raise_for_status()

            logger.info(
                "Agent message delivered via Letta API",
                agent_id=agent_id,
                url=url,
                status_code=response.status_code,
            )

            return {
                "status": "success",
                "output": {
                    "route": "letta",
                    "agent_id": agent_id,
                    "message": message,
                    "status_code": response.status_code,
                    "started_at": started_at.isoformat(),
                    "completed_at": datetime.utcnow().isoformat(),
                },
            }

    except Exception as exc:
        logger.error(
            "Failed to deliver agent message via Letta API",
            agent_id=agent_id,
            url=url,
            error=str(exc),
        )
        raise ActionExecutionError(
            f"Failed to send message to agent {agent_id}: {exc}"
        ) from exc


async def execute_lettabot_heartbeat_action(action_config: Dict[str, Any]) -> Dict[str, Any]:
    """Fire-and-forget message to a LettaBot agent.

    Uses LettaBot's /api/v1/chat/async endpoint — returns 202 immediately,
    agent processes in background with full client-side tools, silent by default
    (agent must explicitly call lettabot-message to notify user).

    Optionally sets conversation routing before sending.

    Config fields:
      agent_id:          Letta agent UUID (used to look up LettaBot from registry)
      agent_name:        LettaBot agent name (e.g. "Mission Control")
      message:           Prompt to send
      conversation_id:   Target conversation UUID (optional — sets routing before send)
      conversation_key:  Conversation key for routing (optional, e.g. "heartbeat", "scheduler")
      lettabot_url:      Override LettaBot URL (optional — auto-resolved from registry)
      lettabot_api_key:  Override API key (optional — auto-resolved from registry)
      model:             Override model for this message (optional, e.g. "gpt-5.4-mini")
      skip_if_busy:      Skip if agent has an active run (default True). Prevents overlap.
    """
    message = action_config.get("message")
    if not message:
        raise ActionExecutionError("lettabot_heartbeat requires 'message'")

    # Resolve LettaBot endpoint from registry or explicit config
    agent_id = action_config.get("agent_id", "")
    lb_entry = settings.lettabot_agents.get(agent_id, {})

    # Skip if agent has an active run (simple mutex to prevent overlap)
    skip_if_busy = action_config.get("skip_if_busy", True)
    if skip_if_busy and agent_id and settings.letta_callback_url:
        try:
            letta_base = str(settings.letta_callback_url).split("/v1/")[0]
            async with httpx.AsyncClient(timeout=5) as check_client:
                resp = await check_client.get(
                    f"{letta_base}/v1/runs/",
                    params={"agent_id": agent_id, "limit": 1},
                )
                if resp.status_code == 200:
                    runs = resp.json()
                    if runs and runs[0].get("status") in ("running", "pending", "queued"):
                        logger.info(
                            "Skipping heartbeat — agent has active run",
                            agent_id=agent_id,
                            run_id=runs[0].get("id"),
                            run_status=runs[0].get("status"),
                        )
                        return {
                            "status": "skipped",
                            "output": {
                                "reason": "agent_busy",
                                "active_run": runs[0].get("id"),
                                "active_status": runs[0].get("status"),
                            },
                        }
        except Exception as e:
            logger.warning("Run check failed, proceeding with heartbeat", error=str(e))
    lettabot_url = action_config.get("lettabot_url") or lb_entry.get("url")
    lettabot_api_key = action_config.get("lettabot_api_key") or lb_entry.get("api_key")

    if not lettabot_url:
        raise ActionExecutionError(
            "lettabot_heartbeat requires lettabot_url or agent_id in LETTABOT_AGENTS registry"
        )

    agent_name = action_config.get("agent_name", "Mission Control")
    base_url = lettabot_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if lettabot_api_key:
        headers["X-Api-Key"] = lettabot_api_key

    started_at = datetime.utcnow()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1 (optional): Set conversation routing
            conv_id = action_config.get("conversation_id")
            conv_key = action_config.get("conversation_key")
            if conv_id:
                conv_payload = {
                    "conversationId": conv_id,
                    "agent": agent_name,
                }
                if conv_key:
                    conv_payload["key"] = conv_key
                conv_resp = await client.post(
                    f"{base_url}/api/v1/conversation",
                    json=conv_payload,
                    headers=headers,
                )
                if conv_resp.status_code != 200:
                    logger.warning(
                        "Conversation routing failed",
                        status=conv_resp.status_code,
                        body=conv_resp.text[:200],
                    )

            # Step 2: Fire-and-forget async message
            payload: Dict[str, Any] = {
                "message": message,
                "agent": agent_name,
            }
            # Optional model override
            model = action_config.get("model")
            if model:
                payload["model"] = model

            response = await client.post(
                f"{base_url}/api/v1/chat/async",
                json=payload,
                headers=headers,
            )

            if response.status_code != 202:
                raise ActionExecutionError(
                    f"Expected 202, got {response.status_code}: {response.text[:200]}"
                )

            logger.info(
                "LettaBot heartbeat queued",
                agent_name=agent_name,
                agent_id=agent_id,
            )

            return {
                "status": "success",
                "output": {
                    "route": "lettabot_heartbeat",
                    "agent_name": agent_name,
                    "agent_id": agent_id,
                    "message": message[:200],
                    "conversation_id": conv_id,
                    "model": model,
                    "started_at": started_at.isoformat(),
                    "completed_at": datetime.utcnow().isoformat(),
                },
            }

    except ActionExecutionError:
        raise
    except Exception as exc:
        logger.error(
            "LettaBot heartbeat failed",
            agent_name=agent_name,
            error=str(exc),
        )
        raise ActionExecutionError(
            f"LettaBot heartbeat failed for {agent_name}: {exc}"
        ) from exc


ACTION_EXECUTORS = {
    "http": execute_http_action,
    "webhook": execute_http_action,
    "script": execute_script_action,
    "agent_message": execute_agent_message_action,
    "lettabot_heartbeat": execute_lettabot_heartbeat_action,
}


async def execute_action(action_type: str, action_config: Dict[str, Any]) -> Dict[str, Any]:
    executor = ACTION_EXECUTORS.get(action_type)
    if not executor:
        raise ActionExecutionError(f"Unsupported action type: {action_type}")

    logger.info("Executing action", action_type=action_type)
    return await executor(action_config)


