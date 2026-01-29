"""Coordination block handler for multi-agent tasks.

Manages three per-identity blocks:
- coordination_task_{identity_id}: Task context (handler writes, agents read)
- coordination_gathered_{identity_id}: Agent findings (agents append, handler reads)
- coordination_status_{identity_id}: Completion tracking (handler only)

See: docs/plans/2026-01-28-multi-agent-coordination-design.md
"""

import json
from datetime import datetime, timezone
from typing import Optional

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
                response = await client.get(
                    f"{self.base_url}/v1/blocks/",
                    params={"label": label}
                )

                if response.status_code == 200:
                    blocks = response.json()
                    if blocks and len(blocks) > 0:
                        return blocks[0]

                return None

        except Exception as e:
            logger.warning("block_get_by_label_error", label=label, error=str(e))
            return None

    async def start_coordinated_task(
        self,
        identity_id: str,
        task_type: str,
        title: str,
        event_id: Optional[str] = None,
        participants: Optional[list[str]] = None,
        required_agents: Optional[list[str]] = None,
    ) -> Optional[str]:
        """
        Initialize coordination blocks for a multi-agent task.

        Creates three blocks:
        - coordination_task_{identity_id}: Task context for agents
        - coordination_gathered_{identity_id}: Empty, for agent findings
        - coordination_status_{identity_id}: Status tracking

        Args:
            identity_id: User's identity ID
            task_type: Type of task (e.g., "meeting_prep")
            title: Human-readable task title
            event_id: Optional event ID for calendar tasks
            participants: Optional list of participant names
            required_agents: List of agent names that should contribute

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

        # Create/reset gathered block
        gathered_block_id = await self.get_or_create_block(
            label=f"coordination_gathered_{identity_id}",
            initial_value="",
            description="Agent findings (append-only)"
        )
        if gathered_block_id:
            await self.update_block(gathered_block_id, "")

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
    ) -> bool:
        """
        Check if agent has added findings to gathered block.

        Looks for [AgentName pattern in gathered block. If found,
        updates status block to mark agent as "done".

        Args:
            identity_id: User's identity ID
            agent_name: Agent name to check (calendar, email, etc.)

        Returns:
            True if agent has contributed, False otherwise
        """
        # Get gathered block
        gathered = await self.get_block_by_label(f"coordination_gathered_{identity_id}")
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
        Archive gathered block if approaching capacity.

        Writes current content to main agent's archival memory,
        then resets block with archive marker.

        Args:
            identity_id: User's identity ID
            main_agent_id: Main agent ID for archival storage

        Returns:
            True if rotation occurred, False otherwise
        """
        gathered = await self.get_block_by_label(f"coordination_gathered_{identity_id}")
        if not gathered:
            return False

        value = gathered.get("value", "")
        if len(value) < ROTATION_THRESHOLD:
            return False

        # Get task context for archive
        task_block = await self.get_block_by_label(f"coordination_task_{identity_id}")
        task_context = task_block.get("value", "") if task_block else "Unknown task"

        # Archive to main agent's archival memory
        archive_text = f"""Coordination Session Findings

Task: {task_context}
Timestamp: {datetime.now(timezone.utc).isoformat()}

{value}"""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/agents/{main_agent_id}/archival-memory",
                    json={
                        "text": archive_text,
                        "tags": [
                            f"identity:{identity_id}",
                            "type:coordination_findings",
                        ]
                    }
                )

                if response.status_code != 200:
                    logger.warning(
                        "coordination_archive_failed",
                        identity_id=identity_id,
                        status=response.status_code
                    )
                    return False

        except Exception as e:
            logger.warning("coordination_archive_error", error=str(e))
            return False

        # Reset gathered block with archive marker
        reset_value = f"[Archived at {datetime.now(timezone.utc).strftime('%H:%M')}]\n\n"
        await self.update_block(gathered["id"], reset_value)

        logger.info("coordination_block_rotated", identity_id=identity_id)
        return True

    async def complete_task(
        self,
        identity_id: str,
        main_agent_id: str,
    ) -> bool:
        """
        Archive coordination state and reset blocks.

        Called when all agents have completed their contributions.

        Args:
            identity_id: User's identity ID
            main_agent_id: Main agent ID for archival storage

        Returns:
            True on success, False on failure
        """
        # Get all blocks
        task_block = await self.get_block_by_label(f"coordination_task_{identity_id}")
        gathered_block = await self.get_block_by_label(f"coordination_gathered_{identity_id}")
        status_block = await self.get_block_by_label(f"coordination_status_{identity_id}")

        task_value = task_block.get("value", "") if task_block else ""
        gathered_value = gathered_block.get("value", "") if gathered_block else ""
        status_value = status_block.get("value", "{}") if status_block else "{}"

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

        # Reset all blocks
        if task_block:
            await self.update_block(task_block["id"], "")
        if gathered_block:
            await self.update_block(gathered_block["id"], "")
        if status_block:
            await self.update_block(status_block["id"], "{}")

        logger.info("coordinated_task_completed", identity_id=identity_id)
        return True
