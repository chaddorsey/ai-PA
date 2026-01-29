# Multi-Agent Coordination Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement shared coordination blocks that enable multiple specialist agents to contribute to coordinated tasks like "prep me for my next meeting".

**Architecture:** Three-block system per identity (`coordination_task`, `coordination_gathered`, `coordination_status`) managed by a CoordinationBlockHandler in the routing handler. Agents use `memory_insert` (append-only) to add findings. Handler orchestrates task flow.

**Tech Stack:** Python 3.9+, FastAPI, Letta Blocks API, httpx, pytest

**Design Document:** `docs/plans/2026-01-28-multi-agent-coordination-design.md`

---

## Agent IDs Reference

| Agent | ID |
|-------|-----|
| Main Agent | `agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a` |
| Calendar Agent | `agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218` |
| Task Agent | `agent-dd15479e-6543-400e-8463-b2a48b13cd4a` |
| Email Agent | `agent-b4928949-8012-4436-a3c7-a9e510785147` |
| Pulse Agent | `agent-6eb765bf-7268-4f6d-a380-c527c9c53000` |

---

## Task 1: Create CoordinationBlockHandler Service

**Files:**
- Create: `pa-routing-handler/src/pa_routing/services/coordination_handler.py`
- Test: `pa-routing-handler/tests/services/test_coordination_handler.py`

### Step 1: Write failing test for block creation

```python
# pa-routing-handler/tests/services/test_coordination_handler.py
"""Tests for coordination block handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for Letta API calls."""
    with patch("httpx.AsyncClient") as mock:
        client = AsyncMock()
        mock.return_value.__aenter__.return_value = client
        yield client

class TestCoordinationBlockHandler:
    """Tests for CoordinationBlockHandler."""

    @pytest.mark.asyncio
    async def test_get_or_create_block_creates_new(self, mock_httpx_client):
        """Creates new block when none exists."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        # Mock: no existing block found
        mock_httpx_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: []
        )
        # Mock: block creation succeeds
        mock_httpx_client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"id": "block-new-123", "label": "coordination_task_identity-abc"}
        )

        handler = CoordinationBlockHandler("http://letta:8283")
        block_id = await handler.get_or_create_block(
            label="coordination_task_identity-abc",
            initial_value="",
            description="Task context block"
        )

        assert block_id == "block-new-123"
        mock_httpx_client.post.assert_called_once()
```

### Step 2: Run test to verify it fails

Run: `cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_handler.py -v`
Expected: FAIL with "No module named 'pa_routing.services.coordination_handler'"

### Step 3: Write minimal implementation

```python
# pa-routing-handler/src/pa_routing/services/coordination_handler.py
"""Coordination block handler for multi-agent tasks.

Manages three per-identity blocks:
- coordination_task_{identity_id}: Task context (handler writes, agents read)
- coordination_gathered_{identity_id}: Agent findings (agents append, handler reads)
- coordination_status_{identity_id}: Completion tracking (handler only)

See: docs/plans/2026-01-28-multi-agent-coordination-design.md
"""

import json
from datetime import datetime
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
```

### Step 4: Run test to verify it passes

Run: `cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_handler.py::TestCoordinationBlockHandler::test_get_or_create_block_creates_new -v`
Expected: PASS

### Step 5: Commit

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_handler.py
git add pa-routing-handler/tests/services/test_coordination_handler.py
git commit -m "feat: add CoordinationBlockHandler with get_or_create_block"
```

---

## Task 2: Add Block Update and Retrieval Methods

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_handler.py`
- Modify: `pa-routing-handler/tests/services/test_coordination_handler.py`

### Step 1: Write failing test for update_block

```python
# Add to tests/services/test_coordination_handler.py

    @pytest.mark.asyncio
    async def test_update_block_succeeds(self, mock_httpx_client):
        """Updates block value via PATCH."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        mock_httpx_client.patch.return_value = MagicMock(
            status_code=200,
            json=lambda: {"id": "block-123", "value": "new value"}
        )

        handler = CoordinationBlockHandler("http://letta:8283")
        result = await handler.update_block("block-123", "new value")

        assert result is True
        mock_httpx_client.patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_block_value_returns_content(self, mock_httpx_client):
        """Retrieves block value by ID."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        mock_httpx_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"id": "block-123", "value": "block content", "label": "test"}
        )

        handler = CoordinationBlockHandler("http://letta:8283")
        value = await handler.get_block_value("block-123")

        assert value == "block content"
```

### Step 2: Run test to verify it fails

Run: `cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_handler.py -v -k "update_block or get_block_value"`
Expected: FAIL with "AttributeError: 'CoordinationBlockHandler' object has no attribute 'update_block'"

### Step 3: Add update_block and get_block_value methods

```python
# Add to coordination_handler.py

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
```

### Step 4: Run test to verify it passes

Run: `cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_handler.py -v`
Expected: PASS

### Step 5: Commit

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_handler.py
git add pa-routing-handler/tests/services/test_coordination_handler.py
git commit -m "feat: add update_block, get_block_value, get_block_by_label methods"
```

---

## Task 3: Add Coordinated Task Lifecycle Methods

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_handler.py`
- Modify: `pa-routing-handler/tests/services/test_coordination_handler.py`

### Step 1: Write failing test for start_coordinated_task

```python
# Add to tests/services/test_coordination_handler.py

    @pytest.mark.asyncio
    async def test_start_coordinated_task_creates_three_blocks(self, mock_httpx_client):
        """Starting task creates task, gathered, and status blocks."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        created_blocks = []

        def track_post(*args, **kwargs):
            label = kwargs.get("json", {}).get("label", "")
            block_id = f"block-{len(created_blocks)}"
            created_blocks.append(label)
            return MagicMock(
                status_code=200,
                json=lambda bid=block_id: {"id": bid, "label": label}
            )

        mock_httpx_client.get.return_value = MagicMock(status_code=200, json=lambda: [])
        mock_httpx_client.post.side_effect = track_post

        handler = CoordinationBlockHandler("http://letta:8283")
        task_id = await handler.start_coordinated_task(
            identity_id="identity-abc",
            task_type="meeting_prep",
            title="Board Meeting",
            event_id="event-123",
            participants=["Alice", "Bob"],
            required_agents=["calendar", "email"]
        )

        assert task_id is not None
        assert "task-meeting_prep-" in task_id
        assert len(created_blocks) == 3
        assert any("coordination_task_" in label for label in created_blocks)
        assert any("coordination_gathered_" in label for label in created_blocks)
        assert any("coordination_status_" in label for label in created_blocks)
```

### Step 2: Run test to verify it fails

Run: `cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_handler.py -v -k "start_coordinated_task"`
Expected: FAIL

### Step 3: Implement start_coordinated_task

```python
# Add to coordination_handler.py

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
        task_id = f"task-{task_type}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
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
```

### Step 4: Run test to verify it passes

Run: `cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_handler.py -v -k "start_coordinated_task"`
Expected: PASS

### Step 5: Commit

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_handler.py
git add pa-routing-handler/tests/services/test_coordination_handler.py
git commit -m "feat: add start_coordinated_task method"
```

---

## Task 4: Add Agent Contribution Checking

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_handler.py`
- Modify: `pa-routing-handler/tests/services/test_coordination_handler.py`

### Step 1: Write failing test

```python
# Add to tests/services/test_coordination_handler.py

    @pytest.mark.asyncio
    async def test_check_agent_contribution_detects_entry(self, mock_httpx_client):
        """Detects when agent has added entry to gathered block."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        # Mock gathered block with Calendar entry
        mock_httpx_client.get.side_effect = [
            # First call: get gathered block by label
            MagicMock(
                status_code=200,
                json=lambda: [{
                    "id": "gathered-block-123",
                    "value": "[Calendar 10:30] Board Meeting, 2pm, 3 participants"
                }]
            ),
            # Second call: get status block by label
            MagicMock(
                status_code=200,
                json=lambda: [{
                    "id": "status-block-456",
                    "value": '{"calendar": "pending", "email": "pending", "task_id": "task-123"}'
                }]
            ),
        ]
        mock_httpx_client.patch.return_value = MagicMock(status_code=200, json=lambda: {})

        handler = CoordinationBlockHandler("http://letta:8283")
        result = await handler.check_agent_contribution("identity-abc", "calendar")

        assert result is True
        # Should have updated status block
        mock_httpx_client.patch.assert_called_once()
```

### Step 2: Run test to verify it fails

Run: `cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_handler.py -v -k "check_agent_contribution"`
Expected: FAIL

### Step 3: Implement check_agent_contribution

```python
# Add to coordination_handler.py

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
```

### Step 4: Run test to verify it passes

Run: `cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_handler.py -v -k "check_agent_contribution"`
Expected: PASS

### Step 5: Commit

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_handler.py
git add pa-routing-handler/tests/services/test_coordination_handler.py
git commit -m "feat: add check_agent_contribution and status methods"
```

---

## Task 5: Add Rotation and Completion Methods

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_handler.py`
- Modify: `pa-routing-handler/tests/services/test_coordination_handler.py`

### Step 1: Write failing test for rotation

```python
# Add to tests/services/test_coordination_handler.py

    @pytest.mark.asyncio
    async def test_check_and_rotate_archives_when_full(self, mock_httpx_client):
        """Archives gathered block when approaching capacity."""
        from pa_routing.services.coordination_handler import (
            CoordinationBlockHandler,
            ROTATION_THRESHOLD
        )

        # Create content that exceeds threshold
        large_content = "[Calendar 10:30] " + "x" * (ROTATION_THRESHOLD + 100)

        mock_httpx_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"id": "gathered-123", "value": large_content}]
        )
        mock_httpx_client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {}
        )
        mock_httpx_client.patch.return_value = MagicMock(
            status_code=200,
            json=lambda: {}
        )

        handler = CoordinationBlockHandler("http://letta:8283")
        rotated = await handler.check_and_rotate_gathered(
            identity_id="identity-abc",
            main_agent_id="agent-main-123"
        )

        assert rotated is True
        # Should have called archival memory POST
        assert mock_httpx_client.post.called
```

### Step 2: Run test to verify it fails

Run: `cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_handler.py -v -k "check_and_rotate"`
Expected: FAIL

### Step 3: Implement rotation and completion

```python
# Add to coordination_handler.py

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
Timestamp: {datetime.utcnow().isoformat()}

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
        reset_value = f"[Archived at {datetime.utcnow().strftime('%H:%M')}]\n\n"
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
Completed: {datetime.utcnow().isoformat()}"""

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
```

### Step 4: Run test to verify it passes

Run: `cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_handler.py -v -k "check_and_rotate"`
Expected: PASS

### Step 5: Commit

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_handler.py
git add pa-routing-handler/tests/services/test_coordination_handler.py
git commit -m "feat: add rotation and task completion methods"
```

---

## Task 6: Create Agent Persona Update Script

**Files:**
- Create: `letta/update_agents_coordination_protocol.py`

### Step 1: Create the update script

```python
#!/usr/bin/env python3
"""
Update Agent Personas with Coordination Protocol

Adds the coordination_protocol instructions to specialist agents
(Calendar, Task, Email, Pulse) so they know how to participate in
coordinated multi-agent tasks.

See: docs/plans/2026-01-28-multi-agent-coordination-design.md
"""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Specialist agents that participate in coordinated tasks
AGENTS = {
    "Calendar Agent": "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218",
    "Task Agent": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "Email Agent": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "Pulse Agent": "agent-6eb765bf-7268-4f6d-a380-c527c9c53000",
}

# Coordination protocol to add to agent personas
COORDINATION_PROTOCOL = """

<coordination_protocol>
When participating in multi-agent tasks, you'll see these memory blocks:

1. coordination_task (READ ONLY)
   - Contains current task context and what you need to contribute
   - Read this to understand your role
   - DO NOT modify this block

2. coordination_gathered (APPEND ONLY)
   - When you finish your work, call memory_insert to add ONE line
   - Tool: memory_insert("coordination_gathered", "[YourName HH:MM] Summary")
   - Format: [AgentName HH:MM] Brief summary (under 100 chars)
   - Example: [Calendar 10:30] Board Meeting, 2pm Jan 30, 3 participants
   - DO NOT use memory_replace or memory_rethink on this block

3. coordination_status (DO NOT TOUCH)
   - Handler uses this to track progress
   - You never need to read or modify this

Workflow:
1. Read coordination_task to understand what's needed
2. Do your specialized work (search, analyze, etc.)
3. Summarize findings in ONE line via memory_insert to coordination_gathered
4. Your part is done - handler will route to next agent if needed

If you encounter errors or can't complete your part, note it in your response and still add a line like:
[YourName HH:MM] Unable to complete - {brief reason}
</coordination_protocol>
"""


def http_get(url):
    """Make HTTP GET request."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"  GET Error: {e}")
        return None


def http_patch(url, data):
    """Make HTTP PATCH request."""
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method='PATCH'
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error {e.code}: {e.read().decode('utf-8')[:200]}")
        return None
    except Exception as e:
        print(f"  PATCH Error: {e}")
        return None


def update_agent_persona(agent_name, agent_id):
    """Add coordination protocol to agent's persona."""
    print(f"\nProcessing {agent_name}...")

    # Get agent's memory blocks
    blocks = http_get(f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks")
    if not blocks:
        print(f"  Could not get blocks")
        return False

    # Find persona block
    persona_block = None
    for block in blocks:
        if block.get("label") == "persona":
            persona_block = block
            break

    if not persona_block:
        print(f"  No persona block found")
        return False

    current_persona = persona_block.get("value", "")
    block_id = persona_block.get("id")

    # Check if already has coordination protocol
    if "<coordination_protocol>" in current_persona:
        print(f"  Already has coordination protocol")
        return "skipped"

    # Add coordination protocol
    new_persona = current_persona + COORDINATION_PROTOCOL

    # Check length
    if len(new_persona) > 5000:
        print(f"  ERROR: New persona exceeds 5000 chars ({len(new_persona)})")
        return False

    print(f"  Length: {len(current_persona)} -> {len(new_persona)} chars")

    # Update the block
    result = http_patch(
        f"{LETTA_BASE}/v1/blocks/{block_id}",
        {"value": new_persona}
    )

    if result:
        print(f"  Added coordination protocol")
        return "updated"
    else:
        print(f"  Failed to update")
        return False


def main():
    print("=" * 60)
    print("Update Agents with Coordination Protocol")
    print("=" * 60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agents to update: {len(AGENTS)}")

    updated = 0
    skipped = 0
    failed = 0

    for agent_name, agent_id in AGENTS.items():
        result = update_agent_persona(agent_name, agent_id)
        if result == "updated":
            updated += 1
        elif result == "skipped":
            skipped += 1
        else:
            failed += 1

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Updated: {updated}")
    print(f"  Skipped (already has protocol): {skipped}")
    print(f"  Failed: {failed}")
    print()

    if failed == 0:
        print("All agents now have coordination protocol!")
    else:
        print(f"Warning: {failed} agents failed")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
```

### Step 2: Make script executable and test

Run: `chmod +x letta/update_agents_coordination_protocol.py`
Run: `python letta/update_agents_coordination_protocol.py`
Expected: Outputs update status for each agent

### Step 3: Commit

```bash
git add letta/update_agents_coordination_protocol.py
git commit -m "feat: add script to update agent personas with coordination protocol"
```

---

## Task 7: Attach Coordination Blocks to Agents

**Files:**
- Create: `letta/attach_coordination_blocks_to_agents.py`

### Step 1: Create block attachment script

```python
#!/usr/bin/env python3
"""
Attach Coordination Blocks to Specialist Agents

Creates and attaches the three coordination blocks to each specialist agent
so they can participate in coordinated tasks.

Blocks:
- coordination_task_{identity_id} - Attached for reading
- coordination_gathered_{identity_id} - Attached for appending

Note: Status block is handler-only and not attached to agents.

See: docs/plans/2026-01-28-multi-agent-coordination-design.md
"""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

# Default identity ID (for initial setup)
DEFAULT_IDENTITY_ID = os.getenv(
    "DEFAULT_IDENTITY_ID",
    "identity-e80a4f2b-a157-47c4-af45-0a4e8f1aec3e"  # Chad's identity
)

# Specialist agents
AGENTS = {
    "Calendar Agent": "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218",
    "Task Agent": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "Email Agent": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "Pulse Agent": "agent-6eb765bf-7268-4f6d-a380-c527c9c53000",
}

# Block configurations
BLOCK_CONFIGS = [
    {
        "label_template": "coordination_task_{identity_id}",
        "description": "Task context for coordinated multi-agent task (READ ONLY)",
        "initial_value": "",
        "limit": 500,
    },
    {
        "label_template": "coordination_gathered_{identity_id}",
        "description": "Agent findings (APPEND ONLY via memory_insert)",
        "initial_value": "",
        "limit": 2000,
    },
]


def http_get(url):
    """Make HTTP GET request."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"  GET Error: {e}")
        return None


def http_post(url, data):
    """Make HTTP POST request."""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"  POST Error {e.code}: {error_body[:200]}")
        return None
    except Exception as e:
        print(f"  POST Error: {e}")
        return None


def http_patch(url, data):
    """Make HTTP PATCH request."""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='PATCH'
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"  PATCH Error: {e}")
        return None


def get_or_create_block(label, description, initial_value, limit):
    """Get existing block or create new one."""
    # Check for existing
    existing = http_get(f"{LETTA_BASE}/v1/blocks/?label={label}")
    if existing and len(existing) > 0:
        print(f"    Found existing block: {existing[0]['id']}")
        return existing[0]['id']

    # Create new
    result = http_post(
        f"{LETTA_BASE}/v1/blocks/",
        {
            "label": label,
            "description": description,
            "value": initial_value,
            "limit": limit,
        }
    )
    if result and result.get('id'):
        print(f"    Created block: {result['id']}")
        return result['id']

    return None


def attach_block_to_agent(agent_id, block_id):
    """Attach block to agent's core memory."""
    result = http_patch(
        f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}",
        {}
    )
    return result is not None


def is_block_attached(agent_id, block_id):
    """Check if block is already attached to agent."""
    blocks = http_get(f"{LETTA_BASE}/v1/agents/{agent_id}/core-memory/blocks")
    if blocks:
        return any(b.get('id') == block_id for b in blocks)
    return False


def main():
    print("=" * 60)
    print("Attach Coordination Blocks to Agents")
    print("=" * 60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Identity ID: {DEFAULT_IDENTITY_ID}")
    print(f"Agents: {len(AGENTS)}")
    print()

    # Create blocks
    print("Creating coordination blocks...")
    block_ids = {}

    for config in BLOCK_CONFIGS:
        label = config["label_template"].format(identity_id=DEFAULT_IDENTITY_ID)
        print(f"  {label}")
        block_id = get_or_create_block(
            label,
            config["description"],
            config["initial_value"],
            config["limit"]
        )
        if block_id:
            block_ids[label] = block_id
        else:
            print(f"    FAILED to create block")

    print()

    # Attach blocks to each agent
    success_count = 0

    for agent_name, agent_id in AGENTS.items():
        print(f"Processing {agent_name}...")

        agent_success = True
        for label, block_id in block_ids.items():
            if is_block_attached(agent_id, block_id):
                print(f"  {label}: already attached")
            else:
                if attach_block_to_agent(agent_id, block_id):
                    print(f"  {label}: attached")
                else:
                    print(f"  {label}: FAILED to attach")
                    agent_success = False

        if agent_success:
            success_count += 1
        print()

    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Blocks created: {len(block_ids)}")
    print(f"  Agents updated: {success_count}/{len(AGENTS)}")
    print()

    return 0 if success_count == len(AGENTS) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
```

### Step 2: Test the script

Run: `python letta/attach_coordination_blocks_to_agents.py`
Expected: Creates blocks and attaches to all agents

### Step 3: Commit

```bash
git add letta/attach_coordination_blocks_to_agents.py
git commit -m "feat: add script to attach coordination blocks to agents"
```

---

## Task 8: Integration Test

**Files:**
- Create: `pa-routing-handler/tests/integration/test_coordination_integration.py`

### Step 1: Write integration test

```python
# pa-routing-handler/tests/integration/test_coordination_integration.py
"""Integration tests for coordination block handling.

Requires running Letta server at LETTA_BASE_URL.
"""

import os
import pytest

# Skip if no Letta server
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
SKIP_INTEGRATION = os.getenv("SKIP_INTEGRATION_TESTS", "false").lower() == "true"


@pytest.mark.skipif(SKIP_INTEGRATION, reason="Integration tests disabled")
class TestCoordinationIntegration:
    """Integration tests for coordination handler with real Letta."""

    @pytest.fixture
    def handler(self):
        from pa_routing.services.coordination_handler import CoordinationBlockHandler
        return CoordinationBlockHandler(LETTA_BASE_URL)

    @pytest.mark.asyncio
    async def test_full_coordination_lifecycle(self, handler):
        """Test complete coordination task lifecycle."""
        identity_id = "test-identity-integration"

        # Start task
        task_id = await handler.start_coordinated_task(
            identity_id=identity_id,
            task_type="integration_test",
            title="Test Meeting",
            required_agents=["calendar", "email"]
        )

        assert task_id is not None
        assert "task-integration_test-" in task_id

        # Check status
        status = await handler.get_task_status(identity_id)
        assert status is not None
        assert status.get("calendar") == "pending"
        assert status.get("email") == "pending"

        # Simulate agent contribution (normally done by agent via memory_insert)
        gathered = await handler.get_block_by_label(f"coordination_gathered_{identity_id}")
        if gathered:
            new_value = "[Calendar 10:30] Test event found"
            await handler.update_block(gathered["id"], new_value)

        # Check contribution
        contributed = await handler.check_agent_contribution(identity_id, "calendar")
        assert contributed is True

        # Check status updated
        status = await handler.get_task_status(identity_id)
        assert status.get("calendar") == "done"

        # Clean up (complete task)
        await handler.complete_task(
            identity_id=identity_id,
            main_agent_id="agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"
        )

        # Verify blocks are reset
        task_block = await handler.get_block_by_label(f"coordination_task_{identity_id}")
        if task_block:
            assert task_block.get("value") == ""
```

### Step 2: Run integration test

Run: `cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/integration/test_coordination_integration.py -v`
Expected: PASS (requires running Letta server)

### Step 3: Commit

```bash
git add pa-routing-handler/tests/integration/test_coordination_integration.py
git commit -m "test: add coordination integration tests"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Create CoordinationBlockHandler | `coordination_handler.py`, tests |
| 2 | Add update/retrieval methods | `coordination_handler.py`, tests |
| 3 | Add task lifecycle methods | `coordination_handler.py`, tests |
| 4 | Add contribution checking | `coordination_handler.py`, tests |
| 5 | Add rotation/completion | `coordination_handler.py`, tests |
| 6 | Update agent personas | `update_agents_coordination_protocol.py` |
| 7 | Attach blocks to agents | `attach_coordination_blocks_to_agents.py` |
| 8 | Integration tests | `test_coordination_integration.py` |

---

## Post-Implementation

After completing all tasks:

1. **Run full test suite:**
   ```bash
   cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest -v
   ```

2. **Update agent personas:**
   ```bash
   python letta/update_agents_coordination_protocol.py
   ```

3. **Attach coordination blocks:**
   ```bash
   python letta/attach_coordination_blocks_to_agents.py
   ```

4. **Test manually:**
   - Start a coordinated task via handler
   - Verify blocks are created
   - Verify agents can read task block
   - Verify agents can append to gathered block
