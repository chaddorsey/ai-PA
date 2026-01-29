"""Coordination orchestrator - executes multi-agent coordination tasks.

This is the core orchestration engine for multi-agent coordination.
It loads task types, dispatches to specialist agents, collects findings,
and synthesizes responses.

See: docs/plans/2026-01-28-multi-agent-coordination-design.md
"""

import asyncio
import time
from typing import Any, Dict, Optional

import httpx
import structlog

from pa_routing.models.requests import CoordinateRequest
from pa_routing.models.responses import CoordinateResponse
from pa_routing.services.coordination_handler import CoordinationBlockHandler
from pa_routing.services.coordination_logger import CoordinationLogger
from pa_routing.services.task_type_loader import (
    AgentConfig,
    TaskType,
    TaskTypeLoader,
    TaskTypeNotFoundError,
)

logger = structlog.get_logger()

# Agent ID mapping (from Letta)
AGENT_IDS = {
    "calendar": "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218",
    "task": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "email": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "pulse": "agent-6eb765bf-7268-4f6d-a380-c527c9c53000",
    "main": "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",
}

# Main agent ID for archival operations
MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"


class CoordinationOrchestrator:
    """Orchestrates multi-agent coordination tasks.

    This class is responsible for:
    1. Loading task type definitions
    2. Initializing coordination state
    3. Dispatching messages to specialist agents in parallel
    4. Collecting and synthesizing findings
    5. Logging all coordination events for analysis
    """

    def __init__(
        self,
        task_type_loader: TaskTypeLoader,
        coordination_handler: CoordinationBlockHandler,
        coordination_logger: CoordinationLogger,
        letta_base_url: str,
    ):
        """Initialize the orchestrator.

        Args:
            task_type_loader: Loads task type definitions from YAML files
            coordination_handler: Manages Letta memory blocks for coordination
            coordination_logger: Logs events to Supabase for analysis
            letta_base_url: Base URL for Letta API (e.g., http://letta:8283)
        """
        self._loader = task_type_loader
        self._handler = coordination_handler
        self._logger = coordination_logger
        self._letta_url = letta_base_url

    async def coordinate(self, request: CoordinateRequest) -> CoordinateResponse:
        """Execute a coordination task.

        Orchestrates multi-agent coordination:
        1. Loads task type definition
        2. Initializes coordination blocks
        3. Dispatches to all enabled agents in parallel
        4. Waits for contributions
        5. Synthesizes final response

        Args:
            request: Coordination request with identity, task type, and context

        Returns:
            CoordinateResponse with synthesis, findings, and status
        """
        start_time = time.time()

        # Load task type
        try:
            task_type = self._loader.load(request.task_type)
        except TaskTypeNotFoundError:
            return CoordinateResponse(
                status="error",
                task_id="",
                error_message=f"Task type not found: {request.task_type}",
            )

        # Verify task type is executable
        if not task_type.is_executable():
            return CoordinateResponse(
                status="error",
                task_id="",
                error_message=f"Task type '{request.task_type}' is in draft stage",
            )

        # Get enabled agents
        enabled_agents = task_type.get_enabled_agents()

        # Build agent_ids mapping for enabled agents
        agent_ids = {
            name: AGENT_IDS[name]
            for name in enabled_agents
            if name in AGENT_IDS
        }

        # Initialize coordination blocks and attach to agents
        task_id = await self._handler.start_coordinated_task(
            identity_id=request.identity_id,
            task_type=request.task_type,
            title=request.context.get("meeting_title", request.task_type),
            required_agents=list(enabled_agents.keys()),
            agent_ids=agent_ids,
        )

        if not task_id:
            return CoordinateResponse(
                status="error",
                task_id="",
                error_message="Failed to initialize coordination blocks",
            )

        # Log start event
        self._logger.log_event(
            event_type="start",
            task_id=task_id,
            identity_id=request.identity_id,
            task_type=request.task_type,
            task_version=task_type.version,
            data={
                "context": request.context,
                "questions_asked": request.questions_asked,
                "agents": list(enabled_agents.keys()),
            },
        )

        # Dispatch agents in parallel (they will write to gathered block)
        dispatch_results = await self._dispatch_all_agents(
            task_id=task_id,
            identity_id=request.identity_id,
            task_type=task_type,
            context=request.context,
        )

        # Wait for contributions by polling the gathered block
        findings = await self._wait_for_contributions(
            identity_id=request.identity_id,
            task_type=task_type,
            task_id=task_id,
        )

        # Determine completion status from gathered findings
        agents_completed = list(findings.keys())
        agents_failed = []
        agents_skipped = []

        for agent_name in enabled_agents:
            if agent_name not in agent_ids:
                # Agent not in AGENT_IDS mapping
                agents_skipped.append(agent_name)
            elif agent_name not in findings:
                # Agent didn't write to gathered block
                result = dispatch_results.get(agent_name)
                if result and result.get("status") == "timeout":
                    agents_failed.append(agent_name)
                elif result and result.get("status") == "error":
                    agents_failed.append(agent_name)
                else:
                    # Message was sent but agent didn't write findings
                    agents_failed.append(agent_name)

        # Synthesize response
        synthesis = await self._synthesize(
            task_type=task_type,
            findings=findings,
            context=request.context,
        )

        # Complete task (archive and detach blocks from agents)
        await self._handler.complete_task(
            request.identity_id,
            MAIN_AGENT_ID,
            agent_ids=agent_ids,
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Log completion event
        self._logger.log_event(
            event_type="complete",
            task_id=task_id,
            identity_id=request.identity_id,
            task_type=request.task_type,
            task_version=task_type.version,
            elapsed_ms=elapsed_ms,
            data={
                "agents_completed": agents_completed,
                "agents_failed": agents_failed,
                "agents_skipped": agents_skipped,
                "synthesis_length": len(synthesis) if synthesis else 0,
            },
        )

        # Determine overall status
        if not agents_completed:
            overall_status = "error"
        elif agents_failed:
            overall_status = "partial"
        else:
            overall_status = "complete"

        return CoordinateResponse(
            status=overall_status,
            task_id=task_id,
            synthesis=synthesis,
            findings=findings,
            agents_completed=agents_completed,
            agents_failed=agents_failed,
            agents_skipped=agents_skipped,
            coordination_time_ms=elapsed_ms,
        )

    async def _dispatch_all_agents(
        self,
        task_id: str,
        identity_id: str,
        task_type: TaskType,
        context: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """Dispatch all enabled agents in parallel.

        Args:
            task_id: Current task identifier
            identity_id: User identity
            task_type: Loaded task type definition
            context: Request context for prompt substitution

        Returns:
            Dict mapping agent name to result dict with status and response
        """
        enabled_agents = task_type.get_enabled_agents()
        agent_names = list(enabled_agents.keys())
        tasks = []

        for agent_name, agent_config in enabled_agents.items():
            prompt = self._build_agent_prompt(agent_config, context)
            tasks.append(
                self._dispatch_to_agent(
                    agent_name=agent_name,
                    prompt=prompt,
                    identity_id=identity_id,
                    task_id=task_id,
                    task_type=task_type.name,
                    timeout=agent_config.timeout_seconds,
                )
            )

        # Run all dispatches concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build results dict mapping agent name to result
        dispatch_results: Dict[str, Dict[str, Any]] = {}
        for i, result in enumerate(results):
            agent_name = agent_names[i]
            if isinstance(result, Exception):
                dispatch_results[agent_name] = {"status": "error", "error": str(result)}
            elif result is not None:
                dispatch_results[agent_name] = result
            # If result is None, agent_name won't be in dispatch_results

        return dispatch_results

    def _build_agent_prompt(
        self,
        agent_config: AgentConfig,
        context: Dict[str, Any],
    ) -> str:
        """Build agent prompt from template and context.

        Substitutes {placeholder} patterns in the prompt template
        with values from the context dictionary.

        Args:
            agent_config: Agent configuration with prompt template
            context: Values to substitute into template

        Returns:
            Prompt string with placeholders replaced
        """
        prompt = agent_config.prompt_template

        for key, value in context.items():
            placeholder = "{" + key + "}"
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(value))

        return prompt

    async def _dispatch_to_agent(
        self,
        agent_name: str,
        prompt: str,
        identity_id: str,
        task_id: str,
        task_type: str,
        timeout: int,
    ) -> Optional[Dict[str, Any]]:
        """Dispatch a single agent.

        Sends message to agent. The agent is expected to write findings
        to the coordination_gathered block via memory_insert.

        Args:
            agent_name: Name of agent to dispatch
            prompt: Message to send to agent
            identity_id: User identity
            task_id: Current task identifier
            task_type: Task type name for logging
            timeout: Timeout in seconds

        Returns:
            Result dict with status (success/timeout/error), or None if agent not found
        """
        agent_id = AGENT_IDS.get(agent_name)
        if not agent_id:
            logger.warning("agent_not_found", agent_name=agent_name)
            return None

        # Log dispatch event
        self._logger.log_event(
            event_type="agent_dispatch",
            task_id=task_id,
            identity_id=identity_id,
            task_type=task_type,
            data={"agent": agent_name, "timeout_seconds": timeout},
        )

        try:
            # Send message to agent - agent will process and memory_insert to gathered block
            await asyncio.wait_for(
                self._send_to_letta(agent_id, prompt, identity_id),
                timeout=timeout,
            )
            # Note: We don't capture the response here - agent should write to gathered block
            return {"status": "success"}

        except asyncio.TimeoutError:
            self._logger.log_event(
                event_type="agent_timeout",
                task_id=task_id,
                identity_id=identity_id,
                task_type=task_type,
                data={"agent": agent_name, "timeout_seconds": timeout},
            )
            return {"status": "timeout"}

        except Exception as e:
            self._logger.log_event(
                event_type="agent_error",
                task_id=task_id,
                identity_id=identity_id,
                task_type=task_type,
                data={"agent": agent_name, "error": str(e)},
            )
            return {"status": "error", "error": str(e)}

    async def _send_to_letta(
        self,
        agent_id: str,
        message: str,
        identity_id: str,
    ) -> Optional[str]:
        """Send message to Letta agent via HTTP.

        Args:
            agent_id: Letta agent identifier
            message: Message to send
            identity_id: User identity (for context)

        Returns:
            Assistant message response or None
        """
        try:
            url = f"{self._letta_url}/v1/agents/{agent_id}/messages"
            payload = {
                "messages": [{"role": "user", "content": message}],
            }

            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

            # Extract assistant message from response
            for msg in data.get("messages", []):
                if msg.get("message_type") == "assistant_message":
                    return msg.get("content")

            return None

        except Exception as e:
            logger.error("letta_send_failed", agent_id=agent_id, error=str(e))
            return None

    async def _wait_for_contributions(
        self,
        identity_id: str,
        task_type: TaskType,
        task_id: str,
    ) -> Dict[str, str]:
        """Wait for agent contributions by polling the gathered block.

        Polls coordination_gathered_{identity_id} block looking for
        [AgentName HH:MM] patterns indicating agent contributions.

        Args:
            identity_id: User identity
            task_type: Task type definition with agent timeouts
            task_id: Current task identifier

        Returns:
            Dict mapping agent name (lowercase) to their findings
        """
        enabled_agents = task_type.get_enabled_agents()
        agents_found: set[str] = set()

        # Calculate deadline from max agent timeout + buffer
        max_timeout = max(
            agent.timeout_seconds for agent in enabled_agents.values()
        )
        buffer_seconds = 5
        deadline = time.time() + max_timeout + buffer_seconds

        polling_interval = 1.0  # Check every second

        while time.time() < deadline:
            # Check each agent for contributions
            for agent_name in enabled_agents:
                if agent_name in agents_found:
                    continue

                contributed = await self._handler.check_agent_contribution(
                    identity_id, agent_name
                )
                if contributed:
                    agents_found.add(agent_name)
                    self._logger.log_event(
                        event_type="agent_contributed",
                        task_id=task_id,
                        identity_id=identity_id,
                        task_type=task_type.name,
                        data={"agent": agent_name},
                    )

            # Check if all agents done
            if agents_found == set(enabled_agents.keys()):
                logger.info(
                    "all_agents_contributed",
                    task_id=task_id,
                    agents=list(agents_found)
                )
                break

            await asyncio.sleep(polling_interval)

        # Parse and return findings from gathered block
        findings = await self._handler.get_gathered_findings(identity_id)
        return findings

    async def _synthesize(
        self,
        task_type: TaskType,
        findings: Dict[str, str],
        context: Dict[str, Any],
    ) -> str:
        """Synthesize response from findings.

        Applies synthesis mode defined in task type:
        - template_only: Apply template with context and findings
        - template_with_enhancement: Template + LLM enhancement
        - main_agent_only: Join all findings

        Args:
            task_type: Task type definition with synthesis config
            findings: Dictionary of agent findings
            context: Original request context

        Returns:
            Synthesized response string
        """
        synthesis_config = task_type.synthesis

        if synthesis_config.mode == "template_only":
            return self._apply_template(synthesis_config.template, findings, context)
        elif synthesis_config.mode == "template_with_enhancement":
            # For now, treat same as template_only
            # Future: Send to main agent for enhancement
            return self._apply_template(synthesis_config.template, findings, context)
        elif synthesis_config.mode == "main_agent_only":
            return "\n\n".join(findings.values())

        return ""

    def _apply_template(
        self,
        template: Optional[str],
        findings: Dict[str, str],
        context: Dict[str, Any],
    ) -> str:
        """Apply template with findings and context.

        Substitutes placeholders:
        - {context_key}: Values from context dict
        - {findings}: All findings joined
        - {agent_findings}: Specific agent's findings

        Args:
            template: Template string with placeholders
            findings: Dictionary of agent findings
            context: Request context values

        Returns:
            Template with placeholders replaced
        """
        if not template:
            return "\n\n".join(findings.values())

        result = template

        # Substitute context values
        for key, value in context.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))

        # Substitute combined findings
        result = result.replace("{findings}", "\n".join(findings.values()))

        # Substitute agent-specific findings
        for agent_name, finding in findings.items():
            placeholder = "{" + agent_name + "_findings}"
            if placeholder in result:
                result = result.replace(placeholder, finding)

        return result
