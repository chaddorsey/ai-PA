"""Coordination block handler for multi-agent tasks.

Manages per-identity blocks:
- coordination_task_{identity_id}: Task context (handler writes, agents read)
- coordination_gathered_{identity_id}_{agent}: Per-agent findings (one block per agent, no race)
- coordination_status_{identity_id}: Completion tracking (handler only)

Each agent gets its own gathered block to write to, eliminating the race
condition that occurs when multiple agents call memory_insert on a shared block
simultaneously (Letta's read-modify-write has no locking).

The orchestrator consolidates per-agent blocks when collecting findings.

Agents write findings in natural language format: [AgentName HH:MM] findings...
This is easier for LLMs than JSON and the handler parses via get_gathered_findings().

See: docs/plans/2026-01-28-multi-agent-coordination-design.md
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger()

# Block configuration
BLOCK_LIMIT = 2000
ROTATION_THRESHOLD = 1500


class CoordinationBlockHandler:
    """Handler for coordination memory blocks."""

    def __init__(self, letta_base_url: str, timeout: float = 10.0):
        """Initialize with Letta API base URL."""
        self.base_url = letta_base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout)

    async def get_block_from_agent(
        self, agent_id: str, label: str
    ) -> Optional[dict]:
        """
        Get block from a specific agent's memory by label.

        Agent-attached blocks aren't in the global blocks list, so we must
        query the agent's core-memory blocks directly.

        Args:
            agent_id: Agent ID to query blocks from
            label: Block label to find

        Returns:
            Block dict with id, value, label, or None if not found
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/v1/agents/{agent_id}/core-memory/blocks"
                )
                if response.status_code == 200:
                    blocks = response.json()
                    for block in blocks:
                        if block.get("label") == label:
                            return block
                return None
        except Exception as e:
            logger.warning(
                "block_get_from_agent_error",
                agent_id=agent_id,
                label=label,
                error=str(e)
            )
            return None

    async def get_or_create_block(
        self,
        label: str,
        initial_value: str = "",
        description: str = "",
    ) -> Optional[str]:
        """
        Get existing block by label or create new one.

        Args:
            label: Block label (e.g., coordination_task_identity-abc)
            initial_value: Initial value if creating new block
            description: Block description if creating new

        Returns:
            Block ID if found/created, None on failure
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Check for existing block
                response = await client.get(
                    f"{self.base_url}/v1/blocks/",
                    params={"label": label}
                )

                if response.status_code == 200:
                    blocks = response.json()
                    if blocks and len(blocks) > 0:
                        block_id = blocks[0].get("id")
                        logger.debug("block_found", label=label, block_id=block_id)
                        return block_id

                # Create new block
                response = await client.post(
                    f"{self.base_url}/v1/blocks/",
                    json={
                        "label": label,
                        "value": initial_value,
                        "description": description,
                        "limit": BLOCK_LIMIT,
                    }
                )

                if response.status_code == 200:
                    block_id = response.json().get("id")
                    logger.info("block_created", label=label, block_id=block_id)
                    return block_id

                logger.warning(
                    "block_create_failed",
                    label=label,
                    status=response.status_code
                )
                return None

        except Exception as e:
            logger.warning("block_operation_failed", label=label, error=str(e))
            return None

    async def update_block(self, block_id: str, value: str) -> bool:
        """
        Update block value.

        Args:
            block_id: Block ID to update
            value: New value

        Returns:
            True on success, False on failure
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.patch(
                    f"{self.base_url}/v1/blocks/{block_id}",
                    json={"value": value}
                )

                if response.status_code == 200:
                    logger.debug("block_updated", block_id=block_id)
                    return True

                logger.warning(
                    "block_update_failed",
                    block_id=block_id,
                    status=response.status_code
                )
                return False

        except Exception as e:
            logger.warning("block_update_error", block_id=block_id, error=str(e))
            return False

    async def get_block_value(self, block_id: str) -> Optional[str]:
        """
        Get block value by ID.

        Args:
            block_id: Block ID to retrieve

        Returns:
            Block value string, or None if not found
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/v1/blocks/{block_id}")

                if response.status_code == 200:
                    return response.json().get("value")

                return None

        except Exception as e:
            logger.warning("block_get_error", block_id=block_id, error=str(e))
            return None

    async def get_block_by_label(self, label: str) -> Optional[dict]:
        """
        Get block by label.

        Args:
            label: Block label to find

        Returns:
            Block dict with id, value, label, or None if not found
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Letta has a 50 char limit on label query param
                # For longer labels, fetch all blocks and filter client-side
                if len(label) <= 50:
                    response = await client.get(
                        f"{self.base_url}/v1/blocks/",
                        params={"label": label}
                    )
                    if response.status_code == 200:
                        blocks = response.json()
                        if blocks and len(blocks) > 0:
                            return blocks[0]
                else:
                    # Long label - fetch all and filter
                    response = await client.get(f"{self.base_url}/v1/blocks/")
                    if response.status_code == 200:
                        blocks = response.json()
                        for block in blocks:
                            if block.get("label") == label:
                                return block

                return None

        except Exception as e:
            logger.warning("block_get_by_label_error", label=label, error=str(e))
            return None

    async def attach_block_to_agent(self, block_id: str, agent_id: str) -> bool:
        """
        Attach a block to an agent's memory.

        Args:
            block_id: Block ID to attach
            agent_id: Agent ID to attach to

        Returns:
            True if successful, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.patch(
                    f"{self.base_url}/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}"
                )
                if response.status_code == 200:
                    logger.info("block_attached", block_id=block_id, agent_id=agent_id)
                    return True
                logger.warning(
                    "block_attach_failed",
                    block_id=block_id,
                    agent_id=agent_id,
                    status=response.status_code
                )
                return False
        except Exception as e:
            logger.warning("block_attach_error", block_id=block_id, error=str(e))
            return False

    async def detach_block_from_agent(self, block_id: str, agent_id: str) -> bool:
        """
        Detach a block from an agent's memory.

        Args:
            block_id: Block ID to detach
            agent_id: Agent ID to detach from

        Returns:
            True if successful, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.patch(
                    f"{self.base_url}/v1/agents/{agent_id}/core-memory/blocks/detach/{block_id}"
                )
                if response.status_code == 200:
                    logger.info("block_detached", block_id=block_id, agent_id=agent_id)
                    return True
                logger.warning(
                    "block_detach_failed",
                    block_id=block_id,
                    agent_id=agent_id,
                    status=response.status_code
                )
                return False
        except Exception as e:
            logger.warning("block_detach_error", block_id=block_id, error=str(e))
            return False

    async def start_coordinated_task(
        self,
        identity_id: str,
        task_type: str,
        title: str,
        event_id: Optional[str] = None,
        participants: Optional[list[str]] = None,
        required_agents: Optional[list[str]] = None,
        agent_ids: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """
        Initialize coordination blocks for a multi-agent task.

        Creates three blocks:
        - coordination_task_{identity_id}: Task context for agents
        - coordination_gathered_{identity_id}: Empty, for agent findings
        - coordination_status_{identity_id}: Status tracking

        If agent_ids provided, attaches task and gathered blocks to all
        participating agents so they can read context and write findings.

        Args:
            identity_id: User's identity ID
            task_type: Type of task (e.g., "meeting_prep")
            title: Human-readable task title
            event_id: Optional event ID for calendar tasks
            participants: Optional list of participant names
            required_agents: List of agent names that should contribute
            agent_ids: Optional mapping of agent_name -> agent_id for block attachment

        Returns:
            Task ID string, or None on failure
        """
        task_id = f"task-{task_type}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        agents = required_agents or ["calendar", "document", "email", "pulse"]
        parts = participants or []

        # Build task block content
        task_content = f"""{task_type.replace('_', ' ').title()} for {title}
Task ID: {task_id}
Agents: {', '.join(agents)}"""

        if event_id:
            task_content = f"""Event ID: {event_id}
{task_content}"""

        if parts:
            task_content += f"\nParticipants: {', '.join(parts)}"

        task_content += """

Expected contributions:
- Calendar: event details, conflicts
- Document: agenda summary, action items
- Email: relevant threads (last 7 days)
- Pulse: availability/status updates"""

        # Create task block
        task_block_id = await self.get_or_create_block(
            label=f"coordination_task_{identity_id}",
            initial_value=task_content,
            description="Task context for coordinated multi-agent task"
        )
        if not task_block_id:
            return None

        # Update task block value (in case it existed with old content)
        await self.update_block(task_block_id, task_content)

        # Create per-agent gathered blocks (one per agent, no shared-write race)
        gathered_block_ids: Dict[str, str] = {}
        for agent_name in agents:
            agent_label = f"coordination_gathered_{identity_id}_{agent_name}"
            block_id = await self.get_or_create_block(
                label=agent_label,
                initial_value="",
                description=f"Findings from {agent_name} agent"
            )
            if block_id:
                await self.update_block(block_id, "")
                gathered_block_ids[agent_name] = block_id

        # Create/initialize status block
        status = {agent: "pending" for agent in agents}
        status["task_id"] = task_id

        status_block_id = await self.get_or_create_block(
            label=f"coordination_status_{identity_id}",
            initial_value=json.dumps(status),
            description="Task completion status (handler only)"
        )
        if status_block_id:
            await self.update_block(status_block_id, json.dumps(status))

        # Attach task block + agent's own gathered block to each agent
        # (Status block is handler-only, not attached to agents)
        if agent_ids and task_block_id:
            for agent_name, agent_id in agent_ids.items():
                if agent_name in agents:
                    # Attach task block (read-only for agents)
                    await self.attach_block_to_agent(task_block_id, agent_id)
                    # Attach this agent's own gathered block
                    agent_gathered_id = gathered_block_ids.get(agent_name)
                    if agent_gathered_id:
                        await self.attach_block_to_agent(agent_gathered_id, agent_id)
                    logger.info(
                        "coordination_blocks_attached",
                        agent_name=agent_name,
                        agent_id=agent_id,
                        identity_id=identity_id
                    )

        logger.info(
            "coordinated_task_started",
            task_id=task_id,
            identity_id=identity_id,
            agents=agents
        )

        return task_id

    async def check_agent_contribution(
        self,
        identity_id: str,
        agent_name: str,
        agent_id: Optional[str] = None,
    ) -> bool:
        """
        Check if agent has added findings to its per-agent gathered block.

        Each agent has its own block: coordination_gathered_{identity_id}_{agent_name}.
        Looks for [AgentName pattern. If found, updates status block to "done".

        Args:
            identity_id: User's identity ID
            agent_name: Agent name to check (calendar, email, etc.)
            agent_id: Optional agent ID to query blocks from
                (needed because agent-attached blocks aren't in global list)

        Returns:
            True if agent has contributed, False otherwise
        """
        # Read from agent's own gathered block
        label = f"coordination_gathered_{identity_id}_{agent_name}"
        if agent_id:
            gathered = await self.get_block_from_agent(agent_id, label)
        else:
            gathered = await self.get_block_by_label(label)
        if not gathered:
            return False

        gathered_value = gathered.get("value", "")

        # Check for agent's entry (case-insensitive match)
        agent_pattern = f"[{agent_name.title()}"
        if agent_pattern not in gathered_value:
            return False

        # Agent has contributed - update status
        status_block = await self.get_block_by_label(f"coordination_status_{identity_id}")
        if status_block:
            try:
                status = json.loads(status_block.get("value", "{}"))
                status[agent_name.lower()] = "done"
                await self.update_block(status_block["id"], json.dumps(status))
                logger.info(
                    "agent_contribution_recorded",
                    identity_id=identity_id,
                    agent=agent_name
                )
            except json.JSONDecodeError:
                logger.warning("status_block_parse_error", identity_id=identity_id)

        return True

    async def get_task_status(self, identity_id: str) -> Optional[dict]:
        """
        Get current task status.

        Args:
            identity_id: User's identity ID

        Returns:
            Status dict with agent statuses and task_id, or None
        """
        status_block = await self.get_block_by_label(f"coordination_status_{identity_id}")
        if not status_block:
            return None

        try:
            return json.loads(status_block.get("value", "{}"))
        except json.JSONDecodeError:
            return None

    async def is_task_complete(self, identity_id: str) -> bool:
        """
        Check if all agents have completed their contributions.

        Args:
            identity_id: User's identity ID

        Returns:
            True if all agents are "done", False otherwise
        """
        status = await self.get_task_status(identity_id)
        if not status:
            return False

        # Check all agents except task_id
        for key, value in status.items():
            if key != "task_id" and value != "done":
                return False

        return True

    async def check_and_rotate_gathered(
        self,
        identity_id: str,
        main_agent_id: str,
    ) -> bool:
        """
        Archive gathered blocks if approaching capacity.

        With per-agent blocks, rotation is rarely needed since each block
        only holds one agent's findings. Kept for backwards compatibility.

        Returns:
            False (rotation not needed with per-agent blocks)
        """
        return False

    async def complete_task(
        self,
        identity_id: str,
        main_agent_id: str,
        agent_ids: Optional[Dict[str, str]] = None,
        agent_names: Optional[List[str]] = None,
    ) -> bool:
        """
        Archive coordination state and reset blocks.

        Consolidates per-agent gathered blocks into a single archive,
        detaches blocks from agents, and resets everything.

        Args:
            identity_id: User's identity ID
            main_agent_id: Main agent ID for archival storage
            agent_ids: Optional mapping of agent_name -> agent_id for block detachment
            agent_names: List of agent names that participated (for block cleanup)

        Returns:
            True on success, False on failure
        """
        agents = agent_names or list(agent_ids.keys()) if agent_ids else []

        # Get shared blocks
        task_block = await self.get_block_by_label(f"coordination_task_{identity_id}")
        status_block = await self.get_block_by_label(f"coordination_status_{identity_id}")

        task_value = task_block.get("value", "") if task_block else ""
        status_value = status_block.get("value", "{}") if status_block else "{}"

        # Consolidate per-agent gathered blocks
        gathered_parts = []
        per_agent_blocks = []
        for agent_name in agents:
            label = f"coordination_gathered_{identity_id}_{agent_name}"
            agent_id = agent_ids.get(agent_name) if agent_ids else None
            if agent_id:
                block = await self.get_block_from_agent(agent_id, label)
            else:
                block = await self.get_block_by_label(label)
            if block:
                per_agent_blocks.append((agent_name, block))
                value = block.get("value", "").strip()
                if value:
                    gathered_parts.append(value)

        gathered_value = "\n".join(gathered_parts)

        # Archive complete session
        archive_text = f"""COMPLETED COORDINATION TASK

{task_value}

Gathered Findings:
{gathered_value}

Status: {status_value}
Completed: {datetime.now(timezone.utc).isoformat()}"""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/agents/{main_agent_id}/archival-memory",
                    json={
                        "text": archive_text,
                        "tags": [
                            f"identity:{identity_id}",
                            "status:completed",
                            "type:coordination_session",
                        ]
                    }
                )

                if response.status_code != 200:
                    logger.warning("task_complete_archive_failed", status=response.status_code)

        except Exception as e:
            logger.warning("task_complete_archive_error", error=str(e))

        # Detach blocks from agents before cleanup
        if agent_ids:
            for agent_name, agent_id in agent_ids.items():
                if task_block:
                    await self.detach_block_from_agent(task_block["id"], agent_id)
                # Detach agent's own gathered block
                for an, block in per_agent_blocks:
                    if an == agent_name:
                        await self.detach_block_from_agent(block["id"], agent_id)
                        break
            logger.info(
                "coordination_blocks_detached",
                identity_id=identity_id,
                agent_count=len(agent_ids)
            )

        # Reset all blocks
        if task_block:
            await self.update_block(task_block["id"], "")
        for _, block in per_agent_blocks:
            await self.update_block(block["id"], "")
        if status_block:
            await self.update_block(status_block["id"], "{}")

        logger.info("coordinated_task_completed", identity_id=identity_id)
        return True

    async def get_gathered_findings(
        self,
        identity_id: str,
        agent_ids: Optional[Dict[str, str]] = None,
        agent_names: Optional[List[str]] = None,
    ) -> dict[str, str]:
        """
        Read per-agent gathered blocks and parse into findings dictionary.

        Each agent writes to its own block: coordination_gathered_{identity_id}_{agent}.
        This reads each one and extracts the [AgentName HH:MM] content.

        Args:
            identity_id: User's identity ID
            agent_ids: Mapping of agent_name -> agent_id for block lookup
            agent_names: List of agent names to check

        Returns:
            Dict mapping agent name (lowercase) to their finding text
        """
        import re

        agents = agent_names or list(agent_ids.keys()) if agent_ids else []
        findings: dict[str, str] = {}

        pattern = r"\[([A-Za-z]+)\s+\d{1,2}:\d{2}\]"

        for agent_name in agents:
            label = f"coordination_gathered_{identity_id}_{agent_name}"
            agent_id = agent_ids.get(agent_name) if agent_ids else None

            if agent_id:
                block = await self.get_block_from_agent(agent_id, label)
            else:
                block = await self.get_block_by_label(label)

            if not block:
                continue

            value = block.get("value", "").strip()
            if not value:
                continue

            # Parse [AgentName HH:MM] pattern from this agent's block
            matches = list(re.finditer(pattern, value))
            if matches:
                # Take last match (in case agent wrote multiple times)
                match = matches[-1]
                finding_text = value[match.end():].strip()
                findings[agent_name] = finding_text
            else:
                # Agent wrote something but not in expected format — include it anyway
                findings[agent_name] = value

        return findings
