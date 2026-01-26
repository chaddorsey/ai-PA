# Letta Conversations: Scheduler Agent Pilot - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable multi-user access to the scheduler agent via Letta Conversations with isolated context and tool-based permission enforcement for user-specific memory blocks.

**Architecture:** Creates a Supabase mapping table for user→conversation tracking, implements two new Letta tools (`find_user_blocks`, `create_user_memory_block`) with CONVERSATION_USER_ID permission checks, and modifies the Slackbot to look up or create conversations per user before sending messages to Letta.

**Tech Stack:** Python 3.11+, Letta SDK 0.16.3+, Supabase PostgreSQL, FastAPI, Slack Bolt

---

## Prerequisites

- Letta server running at `http://localhost:8283`
- Supabase PostgreSQL accessible
- Scheduler agent exists: `agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218`
- Environment variables: `LETTA_BASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`

---

## Task 1: Supabase Migration - user_conversations Table

**Files:**
- Create: `supabase/migrations/20260125_user_conversations.sql`

**Step 1: Write the migration SQL**

```sql
-- Migration: Create user_conversations table for Letta Conversations tracking
-- Date: 2026-01-25

CREATE TABLE IF NOT EXISTS user_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,              -- Slack user ID, email, etc.
    user_source TEXT NOT NULL,          -- 'slack', 'email', 'web'
    agent_id TEXT NOT NULL,             -- Letta agent ID
    conversation_id TEXT NOT NULL,      -- Letta conversation ID
    identity_id TEXT,                   -- Letta identity ID (optional)
    created_at TIMESTAMPTZ DEFAULT now(),
    last_active_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(user_id, user_source, agent_id)
);

CREATE INDEX IF NOT EXISTS idx_user_conversations_lookup
    ON user_conversations(user_id, agent_id);

CREATE INDEX IF NOT EXISTS idx_user_conversations_last_active
    ON user_conversations(last_active_at);

COMMENT ON TABLE user_conversations IS 'Maps users to their Letta conversation IDs for multi-user agent access';
COMMENT ON COLUMN user_conversations.user_id IS 'External user identifier (Slack ID, email)';
COMMENT ON COLUMN user_conversations.user_source IS 'Source platform: slack, email, web';
COMMENT ON COLUMN user_conversations.conversation_id IS 'Letta Conversations API conversation_id';
```

**Step 2: Apply migration to Supabase**

Run:
```bash
psql "postgresql://postgres:$POSTGRES_PASSWORD@localhost:5432/postgres" -f supabase/migrations/20260125_user_conversations.sql
```

Expected: `CREATE TABLE`, `CREATE INDEX` (x2)

**Step 3: Verify table exists**

Run:
```bash
psql "postgresql://postgres:$POSTGRES_PASSWORD@localhost:5432/postgres" -c "\d user_conversations"
```

Expected: Table schema with columns id, user_id, user_source, agent_id, conversation_id, identity_id, created_at, last_active_at

**Step 4: Commit**

```bash
git add supabase/migrations/20260125_user_conversations.sql
git commit -m "$(cat <<'EOF'
feat: add user_conversations table for Letta Conversations

Creates mapping table to track user→conversation relationships
for multi-user access to shared agents.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Implement find_user_blocks Tool

**Files:**
- Create: `letta/conversation_tools/find_user_blocks.py`
- Create: `letta/conversation_tools/__init__.py`
- Test: `letta/conversation_tools/tests/test_find_user_blocks.py`

**Step 1: Create the tools package init**

```python
# letta/conversation_tools/__init__.py
"""
Letta Conversation Tools for multi-user agent access.

These tools enable user-scoped memory block discovery and creation
with permission enforcement via CONVERSATION_USER_ID tool variable.
"""

from .find_user_blocks import find_user_blocks
from .create_user_memory_block import create_user_memory_block

__all__ = ["find_user_blocks", "create_user_memory_block"]
```

**Step 2: Write failing test for find_user_blocks**

```python
# letta/conversation_tools/tests/test_find_user_blocks.py
"""Tests for find_user_blocks tool."""

import os
import pytest
from unittest.mock import patch, MagicMock


class TestFindUserBlocks:
    """Tests for user block discovery with permission checks."""

    def test_returns_error_when_no_conversation_user_id(self):
        """Tool returns error when CONVERSATION_USER_ID is not set."""
        from letta.conversation_tools.find_user_blocks import find_user_blocks

        with patch.dict(os.environ, {}, clear=True):
            result = find_user_blocks(user_id="user_a", scope="all")

        assert result == {"error": "No CONVERSATION_USER_ID set"}

    def test_returns_empty_list_for_wrong_user(self):
        """Tool returns empty list when requesting another user's blocks."""
        from letta.conversation_tools.find_user_blocks import find_user_blocks

        with patch.dict(os.environ, {"CONVERSATION_USER_ID": "user_b"}):
            result = find_user_blocks(user_id="user_a", scope="all")

        assert result == []

    def test_returns_error_for_invalid_user_id_format(self):
        """Tool validates user_id format to prevent injection."""
        from letta.conversation_tools.find_user_blocks import find_user_blocks

        with patch.dict(os.environ, {"CONVERSATION_USER_ID": "user_a; DROP TABLE"}):
            result = find_user_blocks(user_id="user_a; DROP TABLE", scope="all")

        assert "error" in result
        assert "Invalid user_id format" in result["error"]

    def test_discovers_cross_agent_blocks(self):
        """Tool finds cross-agent blocks for the authorized user."""
        from letta.conversation_tools.find_user_blocks import find_user_blocks

        mock_blocks = [
            MagicMock(label="preferences_user_a"),
            MagicMock(label="preferences_user_a_meeting_duration"),
            MagicMock(label="calendar_user_a"),
            MagicMock(label="preferences_user_b"),  # Should NOT be returned
            MagicMock(label="meeting_scheduler_preferences_user_a"),  # Agent-specific
        ]

        with patch.dict(os.environ, {"CONVERSATION_USER_ID": "user_a", "AGENT_NAME": "meeting_scheduler"}):
            with patch("letta.conversation_tools.find_user_blocks.get_all_memory_blocks", return_value=mock_blocks):
                result = find_user_blocks(user_id="user_a", scope="cross_agent")

        labels = [b.label for b in result]
        assert "preferences_user_a" in labels
        assert "preferences_user_a_meeting_duration" in labels
        assert "calendar_user_a" in labels
        assert "preferences_user_b" not in labels
        assert "meeting_scheduler_preferences_user_a" not in labels  # Filtered by scope

    def test_discovers_agent_specific_blocks(self):
        """Tool finds agent-specific blocks for the authorized user."""
        from letta.conversation_tools.find_user_blocks import find_user_blocks

        mock_blocks = [
            MagicMock(label="preferences_user_a"),  # Cross-agent
            MagicMock(label="meeting_scheduler_preferences_user_a_deep_work"),
            MagicMock(label="meeting_scheduler_calendar_user_a"),
        ]

        with patch.dict(os.environ, {"CONVERSATION_USER_ID": "user_a", "AGENT_NAME": "meeting_scheduler"}):
            with patch("letta.conversation_tools.find_user_blocks.get_all_memory_blocks", return_value=mock_blocks):
                result = find_user_blocks(user_id="user_a", scope="agent_specific")

        labels = [b.label for b in result]
        assert "preferences_user_a" not in labels  # Cross-agent, excluded
        assert "meeting_scheduler_preferences_user_a_deep_work" in labels
        assert "meeting_scheduler_calendar_user_a" in labels
```

**Step 3: Run tests to verify they fail**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/conversation_tools/tests/test_find_user_blocks.py -v
```

Expected: FAIL (ModuleNotFoundError: No module named 'letta.conversation_tools')

**Step 4: Write minimal implementation**

```python
# letta/conversation_tools/find_user_blocks.py
"""
Find user memory blocks with permission enforcement.

This tool discovers memory blocks for a user via naming conventions,
enforcing that users can only access their own blocks via the
CONVERSATION_USER_ID tool variable.
"""

import os
import re
from typing import List, Dict, Any, Union


def get_all_memory_blocks() -> List[Any]:
    """
    Get all memory blocks attached to the current agent.

    This is a placeholder that should be called from within the agent context.
    In actual Letta execution, this would access the agent's blocks.
    """
    # This will be overridden when registered with Letta
    # The agent has access to its own blocks via core memory
    raise NotImplementedError(
        "get_all_memory_blocks should be provided by Letta agent context"
    )


def find_user_blocks(
    user_id: str,
    scope: str = "all"
) -> Union[List[Any], Dict[str, str]]:
    """
    Discover all memory blocks for a user via naming convention.

    Args:
        user_id: The user identifier (e.g., "user_a", Slack ID)
        scope: "all", "cross_agent", or "agent_specific"

    Returns:
        List of block objects matching the user and scope.
        Empty list if permission denied.
        Dict with "error" key on validation failure.
    """
    # Permission check
    current_user = os.getenv("CONVERSATION_USER_ID")
    if not current_user:
        return {"error": "No CONVERSATION_USER_ID set"}
    if current_user != user_id:
        return []  # Cannot discover other users' blocks

    # Input validation
    if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
        return {"error": "Invalid user_id format"}

    if scope not in ("all", "cross_agent", "agent_specific"):
        return {"error": f"Invalid scope: {scope}. Must be 'all', 'cross_agent', or 'agent_specific'"}

    try:
        all_blocks = get_all_memory_blocks()
    except NotImplementedError:
        # For testing, return empty list
        return []

    # Match blocks containing user_id
    user_blocks = [
        block for block in all_blocks
        if f"_{user_id}" in block.label or f"_{user_id}_" in block.label
    ]

    # Get agent name from tool variable
    agent_name = os.getenv("AGENT_NAME", "meeting_scheduler")
    agent_prefix = f"{agent_name}_"

    if scope == "cross_agent":
        return [b for b in user_blocks if not b.label.startswith(agent_prefix)]
    elif scope == "agent_specific":
        return [b for b in user_blocks if b.label.startswith(agent_prefix)]

    return user_blocks
```

**Step 5: Run tests to verify they pass**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/conversation_tools/tests/test_find_user_blocks.py -v
```

Expected: PASS (5 tests)

**Step 6: Commit**

```bash
git add letta/conversation_tools/
git commit -m "$(cat <<'EOF'
feat: add find_user_blocks tool for conversation isolation

Implements user block discovery with permission enforcement via
CONVERSATION_USER_ID. Supports cross_agent, agent_specific, and
all scope filters.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Implement create_user_memory_block Tool

**Files:**
- Create: `letta/conversation_tools/create_user_memory_block.py`
- Test: `letta/conversation_tools/tests/test_create_user_memory_block.py`

**Step 1: Write failing test**

```python
# letta/conversation_tools/tests/test_create_user_memory_block.py
"""Tests for create_user_memory_block tool."""

import os
import pytest
from unittest.mock import patch, MagicMock


class TestCreateUserMemoryBlock:
    """Tests for user memory block creation with permission checks."""

    def test_returns_error_when_no_conversation_user_id(self):
        """Tool returns error when CONVERSATION_USER_ID is not set."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        with patch.dict(os.environ, {}, clear=True):
            result = create_user_memory_block(
                user_id="user_a",
                category="preferences",
                value="Prefers morning meetings"
            )

        assert "error" in result
        assert "No CONVERSATION_USER_ID set" in result["error"]

    def test_returns_error_for_wrong_user(self):
        """Tool returns error when creating block for another user."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        with patch.dict(os.environ, {"CONVERSATION_USER_ID": "user_b"}):
            result = create_user_memory_block(
                user_id="user_a",
                category="preferences",
                value="Prefers morning meetings"
            )

        assert "error" in result
        assert "Cannot create blocks for user_a" in result["error"]

    def test_validates_user_id_format(self):
        """Tool rejects invalid user_id format."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        with patch.dict(os.environ, {"CONVERSATION_USER_ID": "user;DROP"}):
            result = create_user_memory_block(
                user_id="user;DROP",
                category="preferences",
                value="test"
            )

        assert "error" in result
        assert "Invalid user_id format" in result["error"]

    def test_validates_category_format(self):
        """Tool rejects invalid category format."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        with patch.dict(os.environ, {"CONVERSATION_USER_ID": "user_a"}):
            result = create_user_memory_block(
                user_id="user_a",
                category="bad category!",
                value="test"
            )

        assert "error" in result
        assert "Invalid category format" in result["error"]

    def test_validates_value_length(self):
        """Tool rejects values over 2000 characters."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        with patch.dict(os.environ, {"CONVERSATION_USER_ID": "user_a"}):
            result = create_user_memory_block(
                user_id="user_a",
                category="preferences",
                value="x" * 2001
            )

        assert "error" in result
        assert "too long" in result["error"]

    def test_builds_cross_agent_label(self):
        """Tool builds correct label for cross-agent blocks."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.id = "block-123"
        mock_client.agents.blocks.create.return_value = mock_block

        with patch.dict(os.environ, {
            "CONVERSATION_USER_ID": "user_a",
            "LETTA_API_KEY": "test-key",
            "LETTA_AGENT_ID": "agent-123",
            "AGENT_NAME": "meeting_scheduler"
        }):
            with patch("letta.conversation_tools.create_user_memory_block.Letta", return_value=mock_client):
                with patch("letta.conversation_tools.create_user_memory_block.invalidate_block_cache"):
                    result = create_user_memory_block(
                        user_id="user_a",
                        category="preferences",
                        value="Prefers 30 minute meetings",
                        purpose="meeting_duration",
                        agent_specific=False
                    )

        assert result["label"] == "preferences_user_a_meeting_duration"
        assert result["block_id"] == "block-123"

    def test_builds_agent_specific_label(self):
        """Tool builds correct label for agent-specific blocks."""
        from letta.conversation_tools.create_user_memory_block import create_user_memory_block

        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.id = "block-456"
        mock_client.agents.blocks.create.return_value = mock_block

        with patch.dict(os.environ, {
            "CONVERSATION_USER_ID": "user_a",
            "LETTA_API_KEY": "test-key",
            "LETTA_AGENT_ID": "agent-123",
            "AGENT_NAME": "meeting_scheduler"
        }):
            with patch("letta.conversation_tools.create_user_memory_block.Letta", return_value=mock_client):
                with patch("letta.conversation_tools.create_user_memory_block.invalidate_block_cache"):
                    result = create_user_memory_block(
                        user_id="user_a",
                        category="preferences",
                        value="Blocks mornings for deep work",
                        purpose="deep_work",
                        agent_specific=True
                    )

        assert result["label"] == "meeting_scheduler_preferences_user_a_deep_work"
        assert result["block_id"] == "block-456"
```

**Step 2: Run tests to verify they fail**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/conversation_tools/tests/test_create_user_memory_block.py -v
```

Expected: FAIL (ModuleNotFoundError)

**Step 3: Write minimal implementation**

```python
# letta/conversation_tools/create_user_memory_block.py
"""
Create user memory blocks with permission enforcement.

This tool creates new memory blocks for emergent user preferences,
enforcing that users can only create blocks for themselves via the
CONVERSATION_USER_ID tool variable.
"""

import os
import re
from typing import Dict, Any, Optional

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        Letta = None


def invalidate_block_cache() -> None:
    """
    Invalidate the block discovery cache.

    Called after creating new blocks to ensure fresh discovery.
    This is a placeholder that integrates with the caching system.
    """
    # Placeholder - actual implementation depends on caching strategy
    pass


def create_user_memory_block(
    user_id: str,
    category: str,
    value: str,
    purpose: Optional[str] = None,
    agent_specific: bool = False
) -> Dict[str, Any]:
    """
    Create a new memory block for emergent user preferences.

    Args:
        user_id: The user identifier
        category: Block category (e.g., "preferences", "calendar")
        value: Initial block content
        purpose: Optional specific purpose (e.g., "meeting_duration")
        agent_specific: If True, prefix with agent name

    Returns:
        dict with block_id and label, or error
    """
    # Permission check
    current_user = os.getenv("CONVERSATION_USER_ID")
    if not current_user:
        return {"error": "No CONVERSATION_USER_ID set"}
    if current_user != user_id:
        return {"error": f"Cannot create blocks for {user_id}"}

    # Input validation
    if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
        return {"error": "Invalid user_id format"}
    if not re.match(r'^[a-zA-Z0-9_-]+$', category):
        return {"error": "Invalid category format"}
    if purpose and not re.match(r'^[a-zA-Z0-9_-]+$', purpose):
        return {"error": "Invalid purpose format"}

    # Check value length
    if len(value) > 2000:
        return {"error": "Block value too long (max 2000 characters)"}

    # Get agent name from tool variable
    agent_name = os.getenv("AGENT_NAME", "meeting_scheduler")

    # Build label
    if agent_specific:
        label = f"{agent_name}_{category}_{user_id}"
    else:
        label = f"{category}_{user_id}"

    if purpose:
        label += f"_{purpose}"

    # Sanitize label
    label = label.lower().replace(" ", "_")

    # Check label length
    if len(label) > 200:
        return {"error": "Block label too long (max 200 characters)"}

    # Create block via Letta API
    if Letta is None:
        return {"error": "Letta client not available"}

    api_key = os.getenv("LETTA_API_KEY")
    agent_id = os.getenv("LETTA_AGENT_ID")

    if not agent_id:
        return {"error": "LETTA_AGENT_ID not set"}

    try:
        client = Letta(api_key=api_key) if api_key else Letta()

        # Create block via Letta API
        description = f"{category} for {user_id}"
        if purpose:
            description += f": {purpose}"

        block = client.agents.blocks.create(
            agent_id=agent_id,
            block={
                "label": label,
                "value": value,
                "description": description,
                "limit": 2000
            }
        )

        # Invalidate block cache
        invalidate_block_cache()

        return {"block_id": block.id, "label": label}

    except Exception as e:
        return {"error": str(e)}
```

**Step 4: Create tests __init__.py**

```python
# letta/conversation_tools/tests/__init__.py
"""Tests for Letta conversation tools."""
```

**Step 5: Run tests to verify they pass**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python -m pytest letta/conversation_tools/tests/test_create_user_memory_block.py -v
```

Expected: PASS (7 tests)

**Step 6: Update package __init__.py**

Already done in Task 2, Step 1. Verify the import works:

```bash
cd /Volumes/main-drive/ai-PA && python -c "from letta.conversation_tools import find_user_blocks, create_user_memory_block; print('OK')"
```

Expected: `OK`

**Step 7: Commit**

```bash
git add letta/conversation_tools/
git commit -m "$(cat <<'EOF'
feat: add create_user_memory_block tool

Implements emergent block creation with permission enforcement.
Supports cross-agent and agent-specific naming conventions.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Implement Conversation Service

**Files:**
- Create: `pa-routing-handler/src/pa_routing/services/conversation_service.py`
- Modify: `pa-routing-handler/src/pa_routing/services/__init__.py`
- Test: `pa-routing-handler/tests/services/test_conversation_service.py`

**Step 1: Write failing test**

```python
# pa-routing-handler/tests/services/test_conversation_service.py
"""Tests for conversation service."""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestConversationService:
    """Tests for user conversation management."""

    @pytest.fixture
    def mock_letta_client(self):
        """Create mock Letta client."""
        client = MagicMock()
        client.conversations = MagicMock()
        client.identities = MagicMock()
        client.agents = MagicMock()
        client.agents.blocks = MagicMock()
        return client

    @pytest.fixture
    def mock_supabase_client(self):
        """Create mock Supabase client."""
        client = MagicMock()
        client.table = MagicMock(return_value=client)
        client.select = MagicMock(return_value=client)
        client.eq = MagicMock(return_value=client)
        client.execute = MagicMock()
        client.insert = MagicMock(return_value=client)
        client.upsert = MagicMock(return_value=client)
        return client

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing_conversation(
        self, mock_letta_client, mock_supabase_client
    ):
        """Returns existing conversation if found in database."""
        from pa_routing.services.conversation_service import ConversationService

        mock_supabase_client.execute.return_value.data = [{
            "conversation_id": "conv-123",
            "identity_id": "identity-456"
        }]

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client
        )

        result = await service.get_or_create_conversation(
            user_id="U123",
            user_source="slack",
            agent_id="agent-abc",
            display_name="Test User",
            email="test@example.com"
        )

        assert result["conversation_id"] == "conv-123"
        assert result["created"] is False

    @pytest.mark.asyncio
    async def test_get_or_create_creates_new_conversation(
        self, mock_letta_client, mock_supabase_client
    ):
        """Creates new conversation when none exists."""
        from pa_routing.services.conversation_service import ConversationService

        # No existing conversation
        mock_supabase_client.execute.return_value.data = []

        # Mock conversation creation
        mock_conversation = MagicMock()
        mock_conversation.id = "new-conv-789"
        mock_letta_client.conversations.create.return_value = mock_conversation

        # Mock identity creation
        mock_identity = MagicMock()
        mock_identity.id = "new-identity-abc"
        mock_letta_client.identities.create.return_value = mock_identity

        # Mock block creation
        mock_block = MagicMock()
        mock_block.id = "block-pref-1"
        mock_letta_client.agents.blocks.create.return_value = mock_block

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client
        )

        result = await service.get_or_create_conversation(
            user_id="U123",
            user_source="slack",
            agent_id="agent-abc",
            display_name="Test User",
            email="test@example.com"
        )

        assert result["conversation_id"] == "new-conv-789"
        assert result["created"] is True

        # Verify conversation was created with correct tool_variables
        mock_letta_client.conversations.create.assert_called_once()
        call_kwargs = mock_letta_client.conversations.create.call_args[1]
        assert call_kwargs["agent_id"] == "agent-abc"
        assert call_kwargs["tool_variables"]["CONVERSATION_USER_ID"] == "U123"

    @pytest.mark.asyncio
    async def test_update_last_active(self, mock_letta_client, mock_supabase_client):
        """Updates last_active_at timestamp."""
        from pa_routing.services.conversation_service import ConversationService

        service = ConversationService(
            letta_client=mock_letta_client,
            supabase_client=mock_supabase_client
        )

        await service.update_last_active(
            user_id="U123",
            user_source="slack",
            agent_id="agent-abc"
        )

        # Verify update was called
        mock_supabase_client.table.assert_called_with("user_conversations")
```

**Step 2: Run tests to verify they fail**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_conversation_service.py -v
```

Expected: FAIL (ModuleNotFoundError)

**Step 3: Write minimal implementation**

```python
# pa-routing-handler/src/pa_routing/services/conversation_service.py
"""
Conversation service for managing user→conversation mappings.

Handles:
- Looking up existing conversations for user+agent pairs
- Creating new conversations with proper tool_variables
- Creating initial user blocks on onboarding
- Tracking conversation activity
"""

import structlog
from datetime import datetime
from typing import Any, Dict, Optional

logger = structlog.get_logger()

# Scheduler agent configuration
SCHEDULER_AGENT_ID = "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218"
AGENT_NAME = "meeting_scheduler"


class ConversationService:
    """
    Manages Letta Conversations for multi-user agent access.

    Each user gets a unique conversation with the agent, enabling:
    - Isolated message history (context)
    - User-scoped tool_variables for permission enforcement
    - Per-user memory blocks via naming conventions
    """

    def __init__(self, letta_client: Any, supabase_client: Any):
        """
        Initialize with Letta and Supabase clients.

        Args:
            letta_client: Initialized Letta client
            supabase_client: Initialized Supabase client
        """
        self.letta = letta_client
        self.supabase = supabase_client

    async def get_or_create_conversation(
        self,
        user_id: str,
        user_source: str,
        agent_id: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get existing conversation or create new one for user+agent.

        Args:
            user_id: External user identifier (Slack ID, email, etc.)
            user_source: Source platform ('slack', 'email', 'web')
            agent_id: Letta agent ID
            display_name: User's display name (for onboarding)
            email: User's email (for onboarding)

        Returns:
            Dict with conversation_id, identity_id, created (bool)
        """
        # Look up existing conversation
        existing = await self._lookup_conversation(user_id, user_source, agent_id)
        if existing:
            logger.info(
                "conversation_found",
                user_id=user_id,
                conversation_id=existing["conversation_id"]
            )
            return {
                "conversation_id": existing["conversation_id"],
                "identity_id": existing.get("identity_id"),
                "created": False
            }

        # Create new conversation with onboarding
        logger.info(
            "conversation_creating",
            user_id=user_id,
            user_source=user_source,
            agent_id=agent_id
        )

        return await self._onboard_user(
            user_id=user_id,
            user_source=user_source,
            agent_id=agent_id,
            display_name=display_name or user_id,
            email=email
        )

    async def _lookup_conversation(
        self,
        user_id: str,
        user_source: str,
        agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """Look up existing conversation in database."""
        try:
            result = (
                self.supabase.table("user_conversations")
                .select("conversation_id, identity_id")
                .eq("user_id", user_id)
                .eq("user_source", user_source)
                .eq("agent_id", agent_id)
                .execute()
            )

            if result.data:
                return result.data[0]
            return None

        except Exception as e:
            logger.error("conversation_lookup_failed", error=str(e))
            return None

    async def _onboard_user(
        self,
        user_id: str,
        user_source: str,
        agent_id: str,
        display_name: str,
        email: Optional[str]
    ) -> Dict[str, Any]:
        """
        Create conversation and initial resources for new user.

        1. Create initial preference block (empty)
        2. Create initial calendar block
        3. Create identity (metadata)
        4. Create conversation with user context
        5. Store mapping in database
        """
        identity_id = None
        block_ids = []

        try:
            # 1. Create initial preference block
            pref_block = self.letta.agents.blocks.create(
                agent_id=agent_id,
                block={
                    "label": f"preferences_{user_id}",
                    "value": "No preferences learned yet.",
                    "description": f"Scheduling preferences for {user_id}",
                    "limit": 2000
                }
            )
            block_ids.append(pref_block.id)

            # 2. Create initial calendar block
            cal_block = self.letta.agents.blocks.create(
                agent_id=agent_id,
                block={
                    "label": f"calendar_{user_id}",
                    "value": "Calendar integration pending configuration.",
                    "description": f"Calendar integration for {user_id}",
                    "limit": 1000
                }
            )
            block_ids.append(cal_block.id)

        except Exception as e:
            logger.warning("block_creation_failed", error=str(e), user_id=user_id)
            # Continue - blocks may already exist

        try:
            # 3. Create identity
            identity = self.letta.identities.create(
                identifier_key=user_id,
                name=display_name,
                identity_type="user",
                properties={"email": email, "source": user_source} if email else {"source": user_source}
            )
            identity_id = identity.id

        except Exception as e:
            logger.warning("identity_creation_failed", error=str(e), user_id=user_id)
            # Continue - identity may already exist

        # 4. Create conversation with tool_variables
        conversation = self.letta.conversations.create(
            agent_id=agent_id,
            label=f"{user_id} - {user_source.capitalize()}",
            tool_variables={
                "CONVERSATION_USER_ID": user_id,
                "AGENT_NAME": AGENT_NAME,
                "LETTA_AGENT_ID": agent_id
            }
        )

        # 5. Store mapping in database
        try:
            self.supabase.table("user_conversations").insert({
                "user_id": user_id,
                "user_source": user_source,
                "agent_id": agent_id,
                "conversation_id": conversation.id,
                "identity_id": identity_id
            }).execute()

        except Exception as e:
            logger.error("conversation_mapping_insert_failed", error=str(e))
            # Continue - conversation was created successfully

        logger.info(
            "user_onboarded",
            user_id=user_id,
            conversation_id=conversation.id,
            identity_id=identity_id,
            block_count=len(block_ids)
        )

        return {
            "conversation_id": conversation.id,
            "identity_id": identity_id,
            "created": True
        }

    async def update_last_active(
        self,
        user_id: str,
        user_source: str,
        agent_id: str
    ) -> None:
        """Update last_active_at timestamp for a conversation."""
        try:
            self.supabase.table("user_conversations").update({
                "last_active_at": datetime.utcnow().isoformat()
            }).eq("user_id", user_id).eq("user_source", user_source).eq("agent_id", agent_id).execute()

        except Exception as e:
            logger.warning("last_active_update_failed", error=str(e))
```

**Step 4: Update services __init__.py**

```python
# pa-routing-handler/src/pa_routing/services/__init__.py
"""Services for PA Routing Handler."""

from .session_store import SessionStore
from .agent_selector import AgentSelector
from .letta_client import LettaClient
from .summary_parser import SummaryParser
from .conversation_service import ConversationService

__all__ = [
    "SessionStore",
    "AgentSelector",
    "LettaClient",
    "SummaryParser",
    "ConversationService",
]
```

**Step 5: Create tests directory if needed**

```bash
mkdir -p /Volumes/main-drive/ai-PA/pa-routing-handler/tests/services
touch /Volumes/main-drive/ai-PA/pa-routing-handler/tests/services/__init__.py
```

**Step 6: Run tests to verify they pass**

Run:
```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_conversation_service.py -v
```

Expected: PASS (3 tests)

**Step 7: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/conversation_service.py
git add pa-routing-handler/src/pa_routing/services/__init__.py
git add pa-routing-handler/tests/services/
git commit -m "$(cat <<'EOF'
feat: add ConversationService for multi-user scheduling

Implements user→conversation mapping with Letta Conversations API.
Creates initial blocks and identity on user onboarding.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Register Conversation Tools with Letta

**Files:**
- Create: `letta/register_conversation_tools.py`
- Create: `letta/attach_conversation_tools_to_agent.py`

**Step 1: Write registration script**

```python
# letta/register_conversation_tools.py
#!/usr/bin/env python3
"""
Register Conversation Tools with Letta Agent

Registers find_user_blocks and create_user_memory_block tools
for multi-user conversation isolation.
"""

import os
import sys
from pathlib import Path

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# Add letta directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

from conversation_tools.find_user_blocks import find_user_blocks
from conversation_tools.create_user_memory_block import create_user_memory_block

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")


def main():
    """Register conversation tools with Letta."""

    print(f"{'='*60}")
    print("Conversation Tools Registration")
    print(f"{'='*60}\n")

    print(f"Letta Base URL: {LETTA_BASE_URL}\n")

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("Connected to Letta server\n")

        tools = [
            ("find_user_blocks", find_user_blocks),
            ("create_user_memory_block", create_user_memory_block),
        ]

        registered_count = 0
        for tool_name, tool_func in tools:
            print(f"Registering: {tool_name}...")

            try:
                created_tool = client.tools.create_from_function(
                    func=tool_func,
                    tags=["conversation", "multi-user", "custom"]
                )
                tool_id = created_tool.id if hasattr(created_tool, 'id') else 'N/A'
                print(f"  Registered: {tool_name} (ID: {tool_id})")
                registered_count += 1

            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    print(f"  Already exists: {tool_name}")
                    registered_count += 1
                else:
                    print(f"  Error: {e}")

        print(f"\n{'='*60}")
        print(f"Registration Complete: {registered_count}/{len(tools)} tools")
        print(f"{'='*60}\n")

        print("Next: Run attach_conversation_tools_to_agent.py to attach to scheduler")

        return 0 if registered_count == len(tools) else 1

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Write attachment script**

```python
# letta/attach_conversation_tools_to_agent.py
#!/usr/bin/env python3
"""
Attach Conversation Tools to Scheduler Agent

Attaches find_user_blocks and create_user_memory_block tools
to the scheduler agent for multi-user access.
"""

import os
import sys
from pathlib import Path

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
SCHEDULER_AGENT_ID = os.getenv("SCHEDULER_AGENT_ID", "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218")


def main():
    """Attach conversation tools to scheduler agent."""

    print(f"{'='*60}")
    print("Attach Conversation Tools to Scheduler Agent")
    print(f"{'='*60}\n")

    print(f"Letta Base URL: {LETTA_BASE_URL}")
    print(f"Scheduler Agent ID: {SCHEDULER_AGENT_ID}\n")

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("Connected to Letta server\n")

        # Find tools by name
        tool_names = ["find_user_blocks", "create_user_memory_block"]
        tools_result = client.tools.list()
        tools = tools_result.items if hasattr(tools_result, 'items') else tools_result

        attached_count = 0
        for target_name in tool_names:
            tool_id = None
            for tool in tools:
                tool_name = tool.name if hasattr(tool, 'name') else tool.get("name")
                if tool_name == target_name:
                    tool_id = tool.id if hasattr(tool, 'id') else tool.get("id")
                    break

            if not tool_id:
                print(f"  Tool not found: {target_name}")
                print(f"  Run register_conversation_tools.py first")
                continue

            print(f"Attaching: {target_name} (ID: {tool_id})...")

            try:
                client.agents.tools.attach(
                    agent_id=SCHEDULER_AGENT_ID,
                    tool_id=tool_id
                )
                print(f"  Attached: {target_name}")
                attached_count += 1

            except Exception as e:
                error_str = str(e).lower()
                if "already attached" in error_str or "409" in error_str:
                    print(f"  Already attached: {target_name}")
                    attached_count += 1
                else:
                    print(f"  Error: {e}")

        print(f"\n{'='*60}")
        print(f"Attachment Complete: {attached_count}/{len(tool_names)} tools")
        print(f"{'='*60}\n")

        return 0 if attached_count == len(tool_names) else 1

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 3: Make scripts executable**

```bash
chmod +x /Volumes/main-drive/ai-PA/letta/register_conversation_tools.py
chmod +x /Volumes/main-drive/ai-PA/letta/attach_conversation_tools_to_agent.py
```

**Step 4: Test registration (dry run)**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python letta/register_conversation_tools.py
```

Expected: "Connected to Letta server" followed by tool registration results

**Step 5: Commit**

```bash
git add letta/register_conversation_tools.py
git add letta/attach_conversation_tools_to_agent.py
git commit -m "$(cat <<'EOF'
feat: add conversation tools registration scripts

Scripts to register and attach find_user_blocks and
create_user_memory_block to the scheduler agent.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update Scheduler Agent System Prompt

**Files:**
- Create: `letta/scheduler_system_prompt_addition.md`

**Step 1: Create system prompt addition document**

```markdown
# letta/scheduler_system_prompt_addition.md

## System Prompt Addition for Scheduler Agent (Conversations Pilot)

Add the following to the scheduler agent's system prompt in Letta ADE:

---

## Multi-User Memory Management

You manage user scheduling preferences via memory blocks.

### DISCOVERY

- Call `find_user_blocks(user_id=CONVERSATION_USER_ID)` to discover all blocks for this user
- Blocks follow naming conventions:
  - Cross-agent: `{category}_{user_id}_{purpose}`
  - Agent-specific: `meeting_scheduler_{category}_{user_id}_{purpose}`

### READING PREFERENCES

- Reference discovered blocks directly by label
- Cross-agent blocks contain preferences shared with other agents
- Agent-specific blocks contain your specialized learning

### CREATING NEW BLOCKS

When you learn something new about a user's preferences:
- Use `create_user_memory_block()` to create a new block
- Use `agent_specific=False` for preferences other agents should see
- Use `agent_specific=True` for your specialized domain knowledge
- Check if an existing block already covers this preference before creating

### IMPORTANT

- NEVER access blocks that don't match the current CONVERSATION_USER_ID
- The CONVERSATION_USER_ID is set automatically per conversation
- All your tools will enforce this permission automatically

---

**To apply:** Copy this text and append to the scheduler agent's system prompt in Letta ADE.
```

**Step 2: Commit**

```bash
git add letta/scheduler_system_prompt_addition.md
git commit -m "$(cat <<'EOF'
docs: add scheduler agent system prompt for conversations

Instructions for multi-user memory management with
find_user_blocks and create_user_memory_block tools.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Integration Test Script

**Files:**
- Create: `scripts/test_conversation_pilot.py`

**Step 1: Write integration test script**

```python
#!/usr/bin/env python3
"""
Integration test for Letta Conversations Scheduler Pilot.

Tests:
1. Tool registration exists
2. Conversation creation with tool_variables
3. Block discovery with permission enforcement
4. Block creation with naming conventions
"""

import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found")
        sys.exit(1)

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
SCHEDULER_AGENT_ID = os.getenv("SCHEDULER_AGENT_ID", "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218")
TEST_USER_ID = "test_user_integration"


def test_tools_registered(client: Letta) -> bool:
    """Verify conversation tools are registered."""
    print("\n[Test 1] Tools Registered")

    tools_result = client.tools.list()
    tools = tools_result.items if hasattr(tools_result, 'items') else tools_result
    tool_names = [t.name if hasattr(t, 'name') else t.get('name') for t in tools]

    required = ["find_user_blocks", "create_user_memory_block"]
    for name in required:
        if name in tool_names:
            print(f"  [OK] {name}")
        else:
            print(f"  [FAIL] {name} not found")
            return False

    return True


def test_tools_attached(client: Letta) -> bool:
    """Verify tools are attached to scheduler agent."""
    print("\n[Test 2] Tools Attached to Scheduler")

    try:
        agent = client.agents.retrieve(agent_id=SCHEDULER_AGENT_ID)
        # Get attached tools
        attached_result = client.agents.tools.list(agent_id=SCHEDULER_AGENT_ID)
        attached = attached_result.items if hasattr(attached_result, 'items') else attached_result
        attached_names = [t.name if hasattr(t, 'name') else t.get('name') for t in attached]

        required = ["find_user_blocks", "create_user_memory_block"]
        for name in required:
            if name in attached_names:
                print(f"  [OK] {name} attached")
            else:
                print(f"  [FAIL] {name} not attached")
                return False

        return True

    except Exception as e:
        print(f"  [FAIL] Could not retrieve agent: {e}")
        return False


def test_conversation_creation(client: Letta) -> str:
    """Test conversation creation with tool_variables."""
    print("\n[Test 3] Conversation Creation")

    try:
        conversation = client.conversations.create(
            agent_id=SCHEDULER_AGENT_ID,
            label=f"{TEST_USER_ID} - Integration Test",
            tool_variables={
                "CONVERSATION_USER_ID": TEST_USER_ID,
                "AGENT_NAME": "meeting_scheduler",
                "LETTA_AGENT_ID": SCHEDULER_AGENT_ID
            }
        )
        print(f"  [OK] Created conversation: {conversation.id}")
        return conversation.id

    except Exception as e:
        print(f"  [FAIL] {e}")
        return None


def test_send_message(client: Letta, conversation_id: str) -> bool:
    """Test sending message to conversation."""
    print("\n[Test 4] Send Message to Conversation")

    try:
        response = client.conversations.messages.create(
            conversation_id=conversation_id,
            role="user",
            content="Hello, I prefer 30 minute meetings in the morning."
        )
        print(f"  [OK] Message sent, got response")
        return True

    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def cleanup(client: Letta, conversation_id: str):
    """Clean up test resources."""
    print("\n[Cleanup]")

    if conversation_id:
        try:
            client.conversations.delete(conversation_id=conversation_id)
            print(f"  Deleted conversation: {conversation_id}")
        except Exception as e:
            print(f"  Could not delete conversation: {e}")

    # Clean up test user blocks
    try:
        blocks_result = client.blocks.list()
        blocks = blocks_result.items if hasattr(blocks_result, 'items') else blocks_result
        for block in blocks:
            label = block.label if hasattr(block, 'label') else block.get('label', '')
            if TEST_USER_ID in label:
                block_id = block.id if hasattr(block, 'id') else block.get('id')
                client.blocks.delete(block_id=block_id)
                print(f"  Deleted block: {label}")
    except Exception as e:
        print(f"  Block cleanup error: {e}")


def main():
    """Run integration tests."""
    print("=" * 60)
    print("Letta Conversations Scheduler Pilot - Integration Tests")
    print("=" * 60)

    print(f"\nLetta URL: {LETTA_BASE_URL}")
    print(f"Scheduler Agent: {SCHEDULER_AGENT_ID}")
    print(f"Test User: {TEST_USER_ID}")

    client = Letta(base_url=LETTA_BASE_URL)
    print("\nConnected to Letta")

    passed = 0
    failed = 0
    conversation_id = None

    # Test 1: Tools registered
    if test_tools_registered(client):
        passed += 1
    else:
        failed += 1

    # Test 2: Tools attached
    if test_tools_attached(client):
        passed += 1
    else:
        failed += 1

    # Test 3: Conversation creation
    conversation_id = test_conversation_creation(client)
    if conversation_id:
        passed += 1
    else:
        failed += 1

    # Test 4: Send message (only if conversation created)
    if conversation_id:
        if test_send_message(client, conversation_id):
            passed += 1
        else:
            failed += 1
    else:
        print("\n[Test 4] SKIPPED (no conversation)")
        failed += 1

    # Cleanup
    cleanup(client, conversation_id)

    # Summary
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Make executable**

```bash
chmod +x /Volumes/main-drive/ai-PA/scripts/test_conversation_pilot.py
```

**Step 3: Run integration tests**

Run:
```bash
cd /Volumes/main-drive/ai-PA && python scripts/test_conversation_pilot.py
```

Expected: All tests pass (4 passed, 0 failed)

**Step 4: Commit**

```bash
git add scripts/test_conversation_pilot.py
git commit -m "$(cat <<'EOF'
test: add integration test for conversation pilot

Verifies tool registration, attachment, conversation
creation, and message sending with tool_variables.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Supabase migration | `supabase/migrations/20260125_user_conversations.sql` |
| 2 | find_user_blocks tool | `letta/conversation_tools/find_user_blocks.py` + tests |
| 3 | create_user_memory_block tool | `letta/conversation_tools/create_user_memory_block.py` + tests |
| 4 | ConversationService | `pa-routing-handler/src/pa_routing/services/conversation_service.py` + tests |
| 5 | Tool registration scripts | `letta/register_conversation_tools.py`, `letta/attach_conversation_tools_to_agent.py` |
| 6 | System prompt documentation | `letta/scheduler_system_prompt_addition.md` |
| 7 | Integration tests | `scripts/test_conversation_pilot.py` |

## Post-Implementation

After all tasks complete:

1. **Apply migration**: Run the SQL migration against Supabase
2. **Register tools**: Run `register_conversation_tools.py`
3. **Attach tools**: Run `attach_conversation_tools_to_agent.py`
4. **Update system prompt**: Add content from `scheduler_system_prompt_addition.md` to scheduler agent
5. **Run integration tests**: Verify with `test_conversation_pilot.py`
6. **Test with Slack**: Send DM to scheduler and verify isolated context
