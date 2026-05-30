"""Coordination orchestrator - executes multi-agent coordination tasks.

This is the core orchestration engine for multi-agent coordination.
It loads task types, dispatches to specialist agents, collects findings,
and synthesizes responses.

V2 Architecture (2026-02-27):
  Phase 0 (Resolve): Calendar agent resolves meeting details
  Phase 1 (Gather): Remaining agents search in parallel with resolved context
  Phase 2 (Evaluate): Main agent evaluates findings and requests follow-ups
  Phase 3 (Refine): Follow-up agents re-search with targeted prompts
  Phase 4 (Synthesize): Template or main-agent synthesis

See: docs/plans/2026-02-27-coordination-v2-design.md
"""

import asyncio
import re
import time
from typing import Any, Dict, List, Optional, Tuple

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
    "calendar": "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
    "task": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "email": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "pulse": "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
    "document": "agent-398b4f6c-6afa-493f-8063-897c6b171a0d",
    "main": "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",
}

# Main agent ID for archival and evaluation
MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"


class CoordinationOrchestrator:
    """Orchestrates multi-agent coordination tasks.

    Manages phase transitions:
    1. Resolve: Calendar agent identifies meeting (serial)
    2. Gather: Specialist agents search in parallel with resolved context
    3. Evaluate: Main agent reviews findings and search strategies
    4. Refine: Follow-up dispatches directed by main agent (optional)
    5. Synthesize: Compile final response
    """

    def __init__(
        self,
        task_type_loader: TaskTypeLoader,
        coordination_handler: CoordinationBlockHandler,
        coordination_logger: CoordinationLogger,
        letta_base_url: str,
    ):
        self._loader = task_type_loader
        self._handler = coordination_handler
        self._logger = coordination_logger
        self._letta_url = letta_base_url

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def coordinate(self, request: CoordinateRequest) -> CoordinateResponse:
        """Execute a phased coordination task."""
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

        if not task_type.is_executable():
            return CoordinateResponse(
                status="error",
                task_id="",
                error_message=f"Task type '{request.task_type}' is in draft stage",
            )

        # Get all enabled agents for block setup
        enabled_agents = task_type.get_enabled_agents()
        agent_ids = {
            name: AGENT_IDS[name]
            for name in enabled_agents
            if name in AGENT_IDS
        }

        # Initialize coordination blocks
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

        self._logger.log_event(
            event_type="start",
            task_id=task_id,
            identity_id=request.identity_id,
            task_type=request.task_type,
            task_version=task_type.version,
            data={
                "context": request.context,
                "agents": list(enabled_agents.keys()),
                "phased": task_type.resolve_agent is not None,
            },
        )

        # Build enriched context
        context = {**request.context, "identity_id": request.identity_id}
        if "meeting_title" not in context:
            context["meeting_title"] = context.get(
                "meeting_identifier", task_type.name
            )

        agents_completed = []
        agents_failed = []
        agents_skipped = []

        # ---- Phase 0: Resolve (calendar-first) ----
        resolved_context = {}
        if task_type.resolve_agent and task_type.resolve_agent in enabled_agents:
            resolve_name = task_type.resolve_agent
            logger.info("phase_resolve_start", agent=resolve_name, task_id=task_id)

            resolved_context, resolve_ok = await self._run_resolve_phase(
                resolve_agent_name=resolve_name,
                task_type=task_type,
                context=context,
                identity_id=request.identity_id,
                task_id=task_id,
                agent_ids=agent_ids,
            )

            if resolve_ok:
                agents_completed.append(resolve_name)
            else:
                agents_failed.append(resolve_name)

            # If NO_MATCH, return early with error
            if resolved_context.get("no_match"):
                await self._handler.complete_task(
                    request.identity_id, MAIN_AGENT_ID,
                    agent_ids=agent_ids,
                    agent_names=list(enabled_agents.keys()),
                )
                elapsed_ms = int((time.time() - start_time) * 1000)
                return CoordinateResponse(
                    status="error",
                    task_id=task_id,
                    error_message=f"No matching meeting found for '{context.get('meeting_identifier', '')}'",
                    agents_completed=agents_completed,
                    agents_failed=agents_failed,
                    coordination_time_ms=elapsed_ms,
                )

            # Merge resolved fields into context for gather agents
            context.update(resolved_context)
            logger.info(
                "phase_resolve_complete",
                task_id=task_id,
                resolved_title=resolved_context.get("resolved_title", "?"),
                participant_count=len(resolved_context.get("resolved_participants", "").split(",")),
            )

        # ---- Phase 1: Gather (parallel) ----
        gather_agents = task_type.get_gather_agents()
        gather_agent_ids = {
            name: AGENT_IDS[name]
            for name in gather_agents
            if name in AGENT_IDS
        }

        if gather_agents:
            logger.info("phase_gather_start", agents=list(gather_agents.keys()), task_id=task_id)
            dispatch_tasks = self._launch_agent_dispatches(
                task_id=task_id,
                identity_id=request.identity_id,
                task_type=task_type,
                context=context,
                agents_override=gather_agents,
            )

            gather_findings = await self._wait_for_contributions(
                identity_id=request.identity_id,
                task_type=task_type,
                task_id=task_id,
                agent_ids=gather_agent_ids,
                agents_override=gather_agents,
            )

            for task in dispatch_tasks:
                if not task.done():
                    task.cancel()

            for name in gather_agents:
                if name in gather_findings:
                    agents_completed.append(name)
                elif name not in gather_agent_ids:
                    agents_skipped.append(name)
                else:
                    agents_failed.append(name)

        # ---- Collect all findings (resolve + gather) ----
        all_findings = await self._handler.get_gathered_findings(
            request.identity_id,
            agent_ids=agent_ids,
            agent_names=list(enabled_agents.keys()),
        )

        # ---- Assistant-message fallback ----
        # If an agent's block is empty (tool call failed), check if we captured
        # an assistant_message response we can use instead
        # (This is handled implicitly: _dispatch_to_agent stores responses,
        #  and get_gathered_findings already includes non-pattern content)

        # ---- Phase 2: Evaluate (main agent) ----
        followup_requests: Dict[str, str] = {}
        if task_type.synthesis.evaluation_prompt and all_findings:
            logger.info("phase_evaluate_start", task_id=task_id)
            followup_requests = await self._run_evaluation_phase(
                task_type=task_type,
                findings=all_findings,
                context=context,
                identity_id=request.identity_id,
                task_id=task_id,
            )
            logger.info(
                "phase_evaluate_complete",
                task_id=task_id,
                followup_agents=list(followup_requests.keys()),
            )

        # ---- Phase 3: Refine (targeted follow-ups) ----
        if followup_requests:
            logger.info("phase_refine_start", task_id=task_id, agents=list(followup_requests.keys()))
            await self._run_refinement_phase(
                followup_requests=followup_requests,
                task_type=task_type,
                context=context,
                identity_id=request.identity_id,
                task_id=task_id,
                agent_ids=agent_ids,
            )

            # Re-collect findings after refinement (blocks may have been updated)
            all_findings = await self._handler.get_gathered_findings(
                request.identity_id,
                agent_ids=agent_ids,
                agent_names=list(enabled_agents.keys()),
            )
            logger.info("phase_refine_complete", task_id=task_id)

        # ---- Phase 4: Synthesize ----
        synthesis = await self._synthesize(
            task_type=task_type,
            findings=all_findings,
            context=context,
        )

        # Cleanup
        await self._handler.complete_task(
            request.identity_id,
            MAIN_AGENT_ID,
            agent_ids=agent_ids,
            agent_names=list(enabled_agents.keys()),
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

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
                "refinement_agents": list(followup_requests.keys()),
            },
        )

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
            findings=all_findings,
            agents_completed=agents_completed,
            agents_failed=agents_failed,
            agents_skipped=agents_skipped,
            coordination_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Phase 0: Resolve
    # ------------------------------------------------------------------

    async def _run_resolve_phase(
        self,
        resolve_agent_name: str,
        task_type: TaskType,
        context: Dict[str, Any],
        identity_id: str,
        task_id: str,
        agent_ids: Dict[str, str],
    ) -> Tuple[Dict[str, str], bool]:
        """Run the resolve phase (calendar-first).

        Returns:
            Tuple of (resolved_context_dict, success_bool)
        """
        agent_config = task_type.agents[resolve_agent_name]
        agent_context = {
            **context,
            "gathered_label": f"coordination_gathered_{identity_id}_{resolve_agent_name}",
        }
        prompt = self._build_agent_prompt(agent_config, agent_context)

        # Dispatch and get full response (we need the assistant message as fallback)
        result = await self._dispatch_to_agent(
            agent_name=resolve_agent_name,
            prompt=prompt,
            identity_id=identity_id,
            task_id=task_id,
            task_type=task_type.name,
            timeout=agent_config.timeout_seconds,
        )

        if not result or result.get("status") != "success":
            return {}, False

        # Wait briefly for block write to complete
        await asyncio.sleep(2)

        # Read the calendar agent's block
        agent_id = agent_ids.get(resolve_agent_name)
        findings = await self._handler.get_gathered_findings(
            identity_id,
            agent_ids={resolve_agent_name: agent_id} if agent_id else None,
            agent_names=[resolve_agent_name],
        )

        calendar_text = findings.get(resolve_agent_name, "")

        # Fallback: if block is empty, use assistant_message from dispatch
        if not calendar_text and result.get("assistant_message"):
            calendar_text = result["assistant_message"]
            logger.info("resolve_using_assistant_fallback", task_id=task_id)

        if not calendar_text:
            return {}, False

        # Parse structured calendar response
        resolved = self._parse_calendar_response(calendar_text)
        return resolved, True

    def _parse_calendar_response(self, text: str) -> Dict[str, str]:
        """Parse structured calendar agent response into resolved context fields.

        Expected format:
        [Calendar HH:MM] TITLE: ... | TIME: ... | PARTICIPANTS: Name1 (email1), ... | LINK: ... | LOCATION: ...

        Returns dict with keys: resolved_title, resolved_time, resolved_participants,
        resolved_emails, resolved_link, resolved_location. Also no_match=True if NO_MATCH.
        """
        result: Dict[str, str] = {}

        if "NO_MATCH" in text:
            result["no_match"] = "true"
            return result

        # Try pipe-delimited parsing first
        fields = {}
        for segment in text.split("|"):
            segment = segment.strip()
            if ":" in segment:
                key, _, value = segment.partition(":")
                fields[key.strip().upper()] = value.strip()

        result["resolved_title"] = fields.get("TITLE", "")
        result["resolved_time"] = fields.get("TIME", "")
        result["resolved_location"] = fields.get("LOCATION", "none")
        result["resolved_link"] = fields.get("LINK", "none")

        # Parse participants: "Name1 (email1), Name2 (email2)"
        participants_raw = fields.get("PARTICIPANTS", "")
        if participants_raw:
            names = []
            emails = []
            # Match "Name (email)" patterns
            for match in re.finditer(r"([^,(]+?)\s*\(([^)]+)\)", participants_raw):
                names.append(match.group(1).strip())
                emails.append(match.group(2).strip())

            if names:
                result["resolved_participants"] = ", ".join(names)
                result["resolved_emails"] = ", ".join(emails)
                result["resolved_first_names"] = ", ".join(
                    n.split()[0] for n in names if n
                )
            else:
                # No email pattern — use raw
                result["resolved_participants"] = participants_raw
                result["resolved_emails"] = ""
                result["resolved_first_names"] = ", ".join(
                    p.strip().split()[0] for p in participants_raw.split(",") if p.strip()
                )
        else:
            result["resolved_participants"] = "unknown"
            result["resolved_emails"] = ""
            result["resolved_first_names"] = ""

        # If title is empty, try to extract from raw text
        if not result["resolved_title"]:
            # Try after the [Calendar HH:MM] prefix
            prefix_match = re.search(r"\[Calendar\s+\d{1,2}:\d{2}\]\s*(.+)", text)
            if prefix_match:
                result["resolved_title"] = prefix_match.group(1).split("|")[0].strip()

        return result

    # ------------------------------------------------------------------
    # Phase 2: Evaluate
    # ------------------------------------------------------------------

    async def _run_evaluation_phase(
        self,
        task_type: TaskType,
        findings: Dict[str, str],
        context: Dict[str, Any],
        identity_id: str,
        task_id: str,
    ) -> Dict[str, str]:
        """Send findings to main agent for evaluation, return follow-up requests.

        Returns:
            Dict mapping agent_name -> followup_prompt (empty if no follow-ups needed)
        """
        eval_prompt = task_type.synthesis.evaluation_prompt
        if not eval_prompt:
            return {}

        # Substitute context and findings into evaluation prompt
        prompt = self._substitute_template(eval_prompt, findings, context)

        self._logger.log_event(
            event_type="evaluation_dispatch",
            task_id=task_id,
            identity_id=identity_id,
            task_type=task_type.name,
            data={"findings_agents": list(findings.keys())},
        )

        # Send to main agent and get full response (need tool_call_messages)
        full_response = await self._send_to_letta_full(
            MAIN_AGENT_ID, prompt, identity_id
        )

        if not full_response:
            return {}

        # Parse request_agent_followup tool calls from response
        followups = self._parse_followup_tool_calls(full_response)

        self._logger.log_event(
            event_type="evaluation_complete",
            task_id=task_id,
            identity_id=identity_id,
            task_type=task_type.name,
            data={"followup_agents": list(followups.keys())},
        )

        return followups

    def _parse_followup_tool_calls(
        self, response_messages: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Extract request_agent_followup calls from Letta API response messages.

        Returns:
            Dict mapping agent_name -> followup_prompt
        """
        followups: Dict[str, str] = {}

        for msg in response_messages:
            if msg.get("message_type") != "tool_call_message":
                continue

            tool_call = msg.get("tool_call", {})
            if tool_call.get("name") != "request_agent_followup":
                continue

            # Arguments may be a JSON string or already parsed
            args = tool_call.get("arguments", {})
            if isinstance(args, str):
                import json
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    continue

            agent_name = args.get("agent_name", "").strip().lower()
            followup_prompt = args.get("followup_prompt", "")

            if agent_name and followup_prompt:
                followups[agent_name] = followup_prompt

        return followups

    # ------------------------------------------------------------------
    # Phase 3: Refine
    # ------------------------------------------------------------------

    async def _run_refinement_phase(
        self,
        followup_requests: Dict[str, str],
        task_type: TaskType,
        context: Dict[str, Any],
        identity_id: str,
        task_id: str,
        agent_ids: Dict[str, str],
    ) -> None:
        """Dispatch follow-up prompts to specified agents."""
        for agent_name, followup_prompt in followup_requests.items():
            agent_id = AGENT_IDS.get(agent_name)
            if not agent_id:
                logger.warning("refinement_agent_not_found", agent_name=agent_name)
                continue

            # Build a follow-up prompt that includes the agent's gathered block label
            full_prompt = (
                f"FOLLOW-UP SEARCH REQUEST:\n\n{followup_prompt}\n\n"
                f"Write your additional findings using memory tool:\n"
                f'memory("insert", "coordination_gathered_{identity_id}_{agent_name}", '
                f'insert_text="[{agent_name.title()} HH:MM] REFINEMENT: <your additional findings>", '
                f"insert_line=0)"
            )

            self._logger.log_event(
                event_type="refinement_dispatch",
                task_id=task_id,
                identity_id=identity_id,
                task_type=task_type.name,
                data={"agent": agent_name},
            )

            agent_config = task_type.agents.get(agent_name)
            timeout = agent_config.timeout_seconds if agent_config else 60

            await self._dispatch_to_agent(
                agent_name=agent_name,
                prompt=full_prompt,
                identity_id=identity_id,
                task_id=task_id,
                task_type=task_type.name,
                timeout=timeout,
            )

        # Brief wait for blocks to be updated
        if followup_requests:
            await asyncio.sleep(3)

    # ------------------------------------------------------------------
    # Dispatch and communication
    # ------------------------------------------------------------------

    def _launch_agent_dispatches(
        self,
        task_id: str,
        identity_id: str,
        task_type: TaskType,
        context: Dict[str, Any],
        agents_override: Optional[Dict[str, AgentConfig]] = None,
    ) -> List[asyncio.Task]:
        """Launch agent dispatches as background tasks.

        Args:
            agents_override: If provided, dispatch only these agents (for gather phase)
        """
        agents = agents_override or task_type.get_enabled_agents()

        stagger_delay_ms = 2000

        enriched_context = {**context}
        if "participants" not in enriched_context:
            enriched_context["participants"] = enriched_context.get(
                "resolved_participants", "unknown"
            )

        async def dispatch_with_delay(
            agent_name: str,
            agent_config: Any,
            delay_ms: int,
        ) -> None:
            try:
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000.0)
                agent_context = {
                    **enriched_context,
                    "gathered_label": f"coordination_gathered_{identity_id}_{agent_name}",
                }
                prompt = self._build_agent_prompt(agent_config, agent_context)
                await self._dispatch_to_agent(
                    agent_name=agent_name,
                    prompt=prompt,
                    identity_id=identity_id,
                    task_id=task_id,
                    task_type=task_type.name,
                    timeout=agent_config.timeout_seconds,
                )
            except asyncio.CancelledError:
                logger.info("dispatch_cancelled", agent_name=agent_name)
            except Exception as e:
                logger.warning(
                    "dispatch_background_error",
                    agent_name=agent_name,
                    error=str(e),
                )

        background_tasks = []
        for i, (agent_name, agent_config) in enumerate(agents.items()):
            delay = i * stagger_delay_ms
            task = asyncio.create_task(
                dispatch_with_delay(agent_name, agent_config, delay),
                name=f"dispatch_{agent_name}",
            )
            background_tasks.append(task)

        return background_tasks

    def _build_agent_prompt(
        self,
        agent_config: AgentConfig,
        context: Dict[str, Any],
    ) -> str:
        """Build agent prompt from template and context."""
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
        """Dispatch to a single agent, returning status and assistant message."""
        agent_id = AGENT_IDS.get(agent_name)
        if not agent_id:
            logger.warning("agent_not_found", agent_name=agent_name)
            return None

        self._logger.log_event(
            event_type="agent_dispatch",
            task_id=task_id,
            identity_id=identity_id,
            task_type=task_type,
            data={"agent": agent_name, "timeout_seconds": timeout},
        )

        try:
            response = await asyncio.wait_for(
                self._send_to_letta_full(agent_id, prompt, identity_id),
                timeout=timeout,
            )

            # Extract assistant message for fallback use
            assistant_msg = None
            if response:
                for msg in response:
                    if msg.get("message_type") == "assistant_message":
                        assistant_msg = msg.get("content")
                        break

            return {"status": "success", "assistant_message": assistant_msg}

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

    async def _send_to_letta_full(
        self,
        agent_id: str,
        message: str,
        identity_id: str,
        max_retries: int = 5,
    ) -> Optional[List[Dict[str, Any]]]:
        """Send message to Letta agent, return full message list from response.

        Unlike the old _send_to_letta which returned only the assistant message,
        this returns all messages so we can inspect tool_call_messages too.
        """
        url = f"{self._letta_url}/v1/agents/{agent_id}/messages"
        payload = {
            "messages": [{"role": "user", "content": message}],
        }

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                    response = await client.post(url, json=payload)

                    if response.status_code == 502:
                        if attempt < max_retries:
                            backoff_seconds = 2 ** attempt
                            logger.warning(
                                "letta_502_retry",
                                agent_id=agent_id,
                                attempt=attempt + 1,
                                backoff_seconds=backoff_seconds,
                            )
                            await asyncio.sleep(backoff_seconds)
                            continue
                        else:
                            logger.error(
                                "letta_502_exhausted",
                                agent_id=agent_id,
                                max_retries=max_retries,
                            )
                            raise httpx.HTTPStatusError(
                                f"502 Bad Gateway after {max_retries} retries",
                                request=response.request,
                                response=response,
                            )

                    response.raise_for_status()
                    data = response.json()
                    return data.get("messages", [])

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code != 502:
                    logger.error("letta_send_failed", agent_id=agent_id, error=str(e))
                    raise

            except Exception as e:
                last_error = e
                logger.error("letta_send_failed", agent_id=agent_id, error=str(e))
                raise

        if last_error:
            raise last_error
        return None

    # ------------------------------------------------------------------
    # Contribution polling
    # ------------------------------------------------------------------

    async def _wait_for_contributions(
        self,
        identity_id: str,
        task_type: TaskType,
        task_id: str,
        agent_ids: Optional[Dict[str, str]] = None,
        agents_override: Optional[Dict[str, AgentConfig]] = None,
    ) -> Dict[str, str]:
        """Wait for agent contributions by polling per-agent gathered blocks."""
        agents = agents_override or task_type.get_enabled_agents()
        agents_found: set[str] = set()

        max_timeout = max(
            agent.timeout_seconds for agent in agents.values()
        )
        buffer_seconds = 5
        deadline = time.time() + max_timeout + buffer_seconds
        polling_interval = 1.0

        while time.time() < deadline:
            for agent_name in agents:
                if agent_name in agents_found:
                    continue

                this_agent_id = agent_ids.get(agent_name) if agent_ids else None
                contributed = await self._handler.check_agent_contribution(
                    identity_id, agent_name, agent_id=this_agent_id
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

            if agents_found == set(agents.keys()):
                logger.info(
                    "all_agents_contributed",
                    task_id=task_id,
                    agents=list(agents_found),
                )
                break

            await asyncio.sleep(polling_interval)

        # Collect findings
        target_agent_ids = agent_ids or {}
        findings = await self._handler.get_gathered_findings(
            identity_id,
            agent_ids=target_agent_ids,
            agent_names=list(agents.keys()),
        )
        return findings

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    async def _synthesize(
        self,
        task_type: TaskType,
        findings: Dict[str, str],
        context: Dict[str, Any],
    ) -> str:
        """Synthesize final response from findings."""
        synthesis_config = task_type.synthesis

        if synthesis_config.mode == "main_agent_evaluation":
            # Use template if available, otherwise join findings
            if synthesis_config.template:
                return self._substitute_template(
                    synthesis_config.template, findings, context
                )
            return "\n\n".join(
                f"**{name.title()}:** {text}" for name, text in findings.items()
            )
        elif synthesis_config.mode == "template_only":
            return self._substitute_template(
                synthesis_config.template, findings, context
            )
        elif synthesis_config.mode == "template_with_enhancement":
            return self._substitute_template(
                synthesis_config.template, findings, context
            )
        elif synthesis_config.mode == "main_agent_only":
            return "\n\n".join(findings.values())

        return self._substitute_template(
            synthesis_config.template, findings, context
        )

    def _substitute_template(
        self,
        template: Optional[str],
        findings: Dict[str, str],
        context: Dict[str, Any],
    ) -> str:
        """Substitute placeholders in a template string."""
        if not template:
            return "\n\n".join(findings.values())

        result = template

        # Context values
        for key, value in context.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))

        # Combined findings
        all_findings_text = "\n\n".join(
            f"**{name.title()}:** {text}" for name, text in findings.items()
        )
        result = result.replace("{findings}", "\n".join(findings.values()))
        result = result.replace("{all_findings}", all_findings_text)

        # Agent-specific findings
        for agent_name, finding in findings.items():
            placeholder = "{" + agent_name + "_findings}"
            if placeholder in result:
                result = result.replace(placeholder, finding)

        # Clean up any remaining unresolved placeholders for missing agents
        result = re.sub(r"\{[a-z_]+_findings\}", "(no findings)", result)

        return result
