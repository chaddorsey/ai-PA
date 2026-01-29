# Coordination Orchestration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Implement the multi-agent coordination orchestration system with superpowers-inspired task lifecycle.

**Architecture:** Main Agent develops task types through lifecycle phases (Brainstorm → Design → Create → Execute → Refine). Task designs stored as YAML files, execution logs in Supabase, coordination via `/v1/coordinate` endpoint.

**Tech Stack:** Python 3.9+, FastAPI, Letta API, Supabase, PyYAML, pytest

**Design Document:** `docs/plans/2026-01-29-coordination-orchestration-design.md`

---

## Implementation Phases

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | 1.1-1.3 | Infrastructure setup |
| 2 | 2.1-2.4 | Coordination endpoint |
| 3 | 3.1-3.3 | Main Agent integration |
| 4 | 4.1-4.2 | Observability layer |
| 5 | 5.1-5.2 | First task type + verification |

---

## Phase 1: Infrastructure

### Task 1.1: Create Task Types Directory Structure

**Files:**
- Create: `docs/task-types/.gitkeep`
- Create: `docs/task-types/README.md`

**Step 1: Create directory and README**

```bash
mkdir -p docs/task-types
```

**Step 2: Create README explaining the directory**

Create `docs/task-types/README.md`:
```markdown
# Task Types

This directory contains multi-agent coordination task type definitions.

## Lifecycle Stages

- `draft` - Being designed, not yet executable
- `active` - Deployed and in use
- `refined` - Improved based on execution data
- `hardened` - Stable, potentially with UI shortcuts

## File Format

Each task type is a YAML file: `{task_name}.yaml`

See `docs/plans/2026-01-29-coordination-orchestration-design.md` for schema.

## Creating New Task Types

Task types are created through conversation with the Main Agent:
1. Brainstorm the task goal and which agents could help
2. Design the prompts, templates, and success criteria
3. Main Agent creates the YAML file and registers it

## Example

```yaml
name: meeting_prep
lifecycle_stage: active
goal: "Gather relevant context before meetings"
agents:
  calendar:
    prompt_template: "Find meeting matching '{meeting_identifier}'..."
```
```

**Step 3: Create .gitkeep**

```bash
touch docs/task-types/.gitkeep
```

**Step 4: Commit**

```bash
git add docs/task-types/
git commit -m "feat: create task-types directory for coordination task definitions"
```

---

### Task 1.2: Create Coordination Logs Table in Supabase

**Files:**
- SQL migration (run in Supabase)

**Step 1: Create the table**

Run in Supabase SQL editor or via psql:
```sql
-- Coordination execution logs for pattern analysis and refinement
CREATE TABLE IF NOT EXISTS pa_web.coordination_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    event_type TEXT NOT NULL,
    task_id TEXT NOT NULL,
    identity_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    task_version TEXT,
    data JSONB DEFAULT '{}'::jsonb,
    elapsed_ms INT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_coordination_logs_task
    ON pa_web.coordination_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_coordination_logs_type
    ON pa_web.coordination_logs(task_type);
CREATE INDEX IF NOT EXISTS idx_coordination_logs_time
    ON pa_web.coordination_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_coordination_logs_event
    ON pa_web.coordination_logs(event_type);

-- Composite index for refinement queries
CREATE INDEX IF NOT EXISTS idx_coordination_logs_type_event
    ON pa_web.coordination_logs(task_type, event_type);
```

**Step 2: Verify table exists**

```bash
docker exec supabase-db psql -U postgres -d postgres -c "\d pa_web.coordination_logs"
```

Expected: Table schema displayed with all columns and indexes.

**Step 3: Document migration**

Add note to `docs/plans/2026-01-29-coordination-orchestration-impl.md` that migration was run.

---

### Task 1.3: Create Coordination Logging Utility

**Files:**
- Create: `pa-routing-handler/src/pa_routing/services/coordination_logger.py`
- Test: `pa-routing-handler/tests/services/test_coordination_logger.py`

**Step 1: Write failing test**

Create `pa-routing-handler/tests/services/test_coordination_logger.py`:
```python
"""Tests for coordination logging utility."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestCoordinationLogger:
    """Tests for CoordinationLogger."""

    def test_log_event_inserts_to_supabase(self):
        """Log event inserts record to coordination_logs table."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value = None

        logger = CoordinationLogger(mock_supabase)
        logger.log_event(
            event_type="start",
            task_id="task-123",
            identity_id="identity-456",
            task_type="meeting_prep",
            data={"context": {"meeting": "Board Meeting"}}
        )

        mock_supabase.table.assert_called_with("coordination_logs")
        call_args = mock_supabase.table.return_value.insert.call_args[0][0]
        assert call_args["event_type"] == "start"
        assert call_args["task_id"] == "task-123"
        assert call_args["task_type"] == "meeting_prep"

    def test_log_event_includes_elapsed_ms(self):
        """Log event can include elapsed_ms."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value = None

        logger = CoordinationLogger(mock_supabase)
        logger.log_event(
            event_type="complete",
            task_id="task-123",
            identity_id="identity-456",
            task_type="meeting_prep",
            elapsed_ms=4500
        )

        call_args = mock_supabase.table.return_value.insert.call_args[0][0]
        assert call_args["elapsed_ms"] == 4500

    def test_log_event_handles_supabase_error(self):
        """Log event handles Supabase errors gracefully."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.side_effect = Exception("DB error")

        logger = CoordinationLogger(mock_supabase)
        # Should not raise, just log warning
        logger.log_event(
            event_type="start",
            task_id="task-123",
            identity_id="identity-456",
            task_type="meeting_prep"
        )

    def test_query_by_task_type(self):
        """Can query logs by task type."""
        from pa_routing.services.coordination_logger import CoordinationLogger

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"event_type": "complete", "task_type": "meeting_prep"}]
        )

        logger = CoordinationLogger(mock_supabase)
        results = logger.query_by_task_type("meeting_prep", limit=10)

        assert len(results) == 1
        assert results[0]["task_type"] == "meeting_prep"
```

**Step 2: Run test to verify it fails**

```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_logger.py -v
```

Expected: FAIL (module doesn't exist)

**Step 3: Implement CoordinationLogger**

Create `pa-routing-handler/src/pa_routing/services/coordination_logger.py`:
```python
"""Coordination logging utility for pattern analysis and refinement.

Logs all coordination events to Supabase for:
- Tracking agent contribution rates
- Measuring coordination efficiency
- Enabling guided refinement
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger()


class CoordinationLogger:
    """Logs coordination events to Supabase."""

    def __init__(self, supabase_client: Any):
        """Initialize with Supabase client.

        Args:
            supabase_client: Supabase client instance
        """
        self._supabase = supabase_client

    def log_event(
        self,
        event_type: str,
        task_id: str,
        identity_id: str,
        task_type: str,
        task_version: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        elapsed_ms: Optional[int] = None
    ) -> None:
        """Log a coordination event.

        Args:
            event_type: Type of event (start, agent_dispatch, agent_contributed, etc.)
            task_id: Unique task identifier
            identity_id: User identity
            task_type: Name of task type (e.g., meeting_prep)
            task_version: Version from task type YAML
            data: Event-specific data
            elapsed_ms: Elapsed time in milliseconds
        """
        record = {
            "event_type": event_type,
            "task_id": task_id,
            "identity_id": identity_id,
            "task_type": task_type,
            "task_version": task_version,
            "data": data or {},
            "elapsed_ms": elapsed_ms,
            "timestamp": datetime.utcnow().isoformat()
        }

        try:
            self._supabase.table("coordination_logs").insert(record).execute()
            logger.debug(
                "coordination_event_logged",
                event_type=event_type,
                task_id=task_id,
                task_type=task_type
            )
        except Exception as e:
            logger.warning(
                "coordination_log_failed",
                event_type=event_type,
                task_id=task_id,
                error=str(e)
            )

    def query_by_task_type(
        self,
        task_type: str,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query logs for a specific task type.

        Args:
            task_type: Task type to query
            event_type: Optional filter by event type
            limit: Maximum records to return

        Returns:
            List of log records
        """
        try:
            query = (
                self._supabase.table("coordination_logs")
                .select("*")
                .eq("task_type", task_type)
            )

            if event_type:
                query = query.eq("event_type", event_type)

            result = query.order("timestamp", desc=True).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.warning("coordination_query_failed", error=str(e))
            return []

    def get_agent_contribution_stats(
        self,
        task_type: str,
        since_days: int = 30
    ) -> Dict[str, Dict[str, int]]:
        """Get agent contribution statistics for refinement.

        Args:
            task_type: Task type to analyze
            since_days: Look back period in days

        Returns:
            Dict mapping agent name to {dispatches, contributions, timeouts, errors}
        """
        try:
            # Get all dispatch and contribution events
            result = (
                self._supabase.table("coordination_logs")
                .select("event_type, data")
                .eq("task_type", task_type)
                .in_("event_type", ["agent_dispatch", "agent_contributed", "agent_timeout", "agent_error"])
                .execute()
            )

            stats: Dict[str, Dict[str, int]] = {}

            for record in result.data or []:
                agent = record.get("data", {}).get("agent")
                if not agent:
                    continue

                if agent not in stats:
                    stats[agent] = {
                        "dispatches": 0,
                        "contributions": 0,
                        "timeouts": 0,
                        "errors": 0
                    }

                event_type = record["event_type"]
                if event_type == "agent_dispatch":
                    stats[agent]["dispatches"] += 1
                elif event_type == "agent_contributed":
                    stats[agent]["contributions"] += 1
                elif event_type == "agent_timeout":
                    stats[agent]["timeouts"] += 1
                elif event_type == "agent_error":
                    stats[agent]["errors"] += 1

            return stats
        except Exception as e:
            logger.warning("contribution_stats_failed", error=str(e))
            return {}
```

**Step 4: Run tests to verify they pass**

```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_logger.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_logger.py
git add pa-routing-handler/tests/services/test_coordination_logger.py
git commit -m "feat: add CoordinationLogger for execution tracking and refinement"
```

---

## Phase 2: Coordination Endpoint

### Task 2.1: Create Task Type Loader

**Files:**
- Create: `pa-routing-handler/src/pa_routing/services/task_type_loader.py`
- Test: `pa-routing-handler/tests/services/test_task_type_loader.py`

**Step 1: Write failing test**

Create `pa-routing-handler/tests/services/test_task_type_loader.py`:
```python
"""Tests for task type loader."""

import pytest
import tempfile
import os
from pathlib import Path


class TestTaskTypeLoader:
    """Tests for TaskTypeLoader."""

    @pytest.fixture
    def task_types_dir(self):
        """Create temporary task types directory with test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a valid task type file
            meeting_prep = Path(tmpdir) / "meeting_prep.yaml"
            meeting_prep.write_text("""
name: meeting_prep
version: 1.0.0
lifecycle_stage: active
goal: "Gather context for meetings"

agents:
  calendar:
    prompt_template: "Find meeting {meeting_identifier}"
    timeout_seconds: 10
  email:
    prompt_template: "Find emails about {meeting_title}"
    timeout_seconds: 15

synthesis:
  mode: template_with_enhancement
  template: "**{meeting_title}**\\n{findings}"
  enhancement_prompt: "Add insights"
""")

            # Create a draft task type (should be loadable but not executable)
            draft_task = Path(tmpdir) / "draft_task.yaml"
            draft_task.write_text("""
name: draft_task
version: 0.1.0
lifecycle_stage: draft
goal: "Work in progress"
agents: {}
""")

            yield tmpdir

    def test_load_task_type(self, task_types_dir):
        """Load a valid task type from YAML."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        loader = TaskTypeLoader(task_types_dir)
        task_type = loader.load("meeting_prep")

        assert task_type.name == "meeting_prep"
        assert task_type.version == "1.0.0"
        assert task_type.lifecycle_stage == "active"
        assert "calendar" in task_type.agents
        assert task_type.agents["calendar"].timeout_seconds == 10

    def test_load_nonexistent_task_type(self, task_types_dir):
        """Loading nonexistent task type raises error."""
        from pa_routing.services.task_type_loader import TaskTypeLoader, TaskTypeNotFoundError

        loader = TaskTypeLoader(task_types_dir)

        with pytest.raises(TaskTypeNotFoundError):
            loader.load("nonexistent")

    def test_list_task_types(self, task_types_dir):
        """List all available task types."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        loader = TaskTypeLoader(task_types_dir)
        task_types = loader.list_all()

        assert "meeting_prep" in task_types
        assert "draft_task" in task_types

    def test_list_active_task_types(self, task_types_dir):
        """List only active task types."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        loader = TaskTypeLoader(task_types_dir)
        task_types = loader.list_active()

        assert "meeting_prep" in task_types
        assert "draft_task" not in task_types

    def test_get_enabled_agents(self, task_types_dir):
        """Get only enabled agents for a task type."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        loader = TaskTypeLoader(task_types_dir)
        task_type = loader.load("meeting_prep")

        enabled = task_type.get_enabled_agents()
        assert "calendar" in enabled
        assert "email" in enabled
```

**Step 2: Run test to verify it fails**

```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_task_type_loader.py -v
```

Expected: FAIL (module doesn't exist)

**Step 3: Implement TaskTypeLoader**

Create `pa-routing-handler/src/pa_routing/services/task_type_loader.py`:
```python
"""Task type loader - loads coordination task definitions from YAML files.

Task types define how multi-agent coordination works for specific use cases.
They are stored as YAML files in docs/task-types/ and loaded at runtime.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
import structlog

logger = structlog.get_logger()


class TaskTypeNotFoundError(Exception):
    """Raised when a task type is not found."""
    pass


class TaskTypeValidationError(Exception):
    """Raised when a task type file is invalid."""
    pass


@dataclass
class AgentConfig:
    """Configuration for a single agent in a task type."""
    name: str
    prompt_template: str
    timeout_seconds: int = 15
    enabled: bool = True
    expected_contribution: Optional[str] = None


@dataclass
class SynthesisConfig:
    """Configuration for response synthesis."""
    mode: str  # template_only, template_with_enhancement, main_agent_only
    template: Optional[str] = None
    enhancement_prompt: Optional[str] = None


@dataclass
class TaskType:
    """A loaded task type definition."""
    name: str
    version: str
    lifecycle_stage: str  # draft, active, refined, hardened
    goal: str
    agents: Dict[str, AgentConfig]
    synthesis: SynthesisConfig
    success_criteria: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)

    def get_enabled_agents(self) -> Dict[str, AgentConfig]:
        """Get only enabled agents."""
        return {
            name: config
            for name, config in self.agents.items()
            if config.enabled
        }

    def is_executable(self) -> bool:
        """Check if task type can be executed (not draft)."""
        return self.lifecycle_stage != "draft"


class TaskTypeLoader:
    """Loads task type definitions from YAML files."""

    def __init__(self, task_types_dir: str):
        """Initialize with path to task types directory.

        Args:
            task_types_dir: Path to directory containing task type YAML files
        """
        self._dir = Path(task_types_dir)
        self._cache: Dict[str, TaskType] = {}

    def load(self, name: str, use_cache: bool = True) -> TaskType:
        """Load a task type by name.

        Args:
            name: Task type name (without .yaml extension)
            use_cache: Whether to use cached version if available

        Returns:
            Loaded TaskType

        Raises:
            TaskTypeNotFoundError: If task type file doesn't exist
            TaskTypeValidationError: If task type file is invalid
        """
        if use_cache and name in self._cache:
            return self._cache[name]

        file_path = self._dir / f"{name}.yaml"

        if not file_path.exists():
            raise TaskTypeNotFoundError(f"Task type '{name}' not found at {file_path}")

        try:
            with open(file_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise TaskTypeValidationError(f"Invalid YAML in {file_path}: {e}")

        task_type = self._parse_task_type(data, name)
        self._cache[name] = task_type

        logger.info("task_type_loaded", name=name, version=task_type.version)
        return task_type

    def _parse_task_type(self, data: Dict[str, Any], name: str) -> TaskType:
        """Parse raw YAML data into TaskType."""
        # Parse agents
        agents = {}
        for agent_name, agent_data in data.get("agents", {}).items():
            if isinstance(agent_data, dict):
                agents[agent_name] = AgentConfig(
                    name=agent_name,
                    prompt_template=agent_data.get("prompt_template", ""),
                    timeout_seconds=agent_data.get("timeout_seconds", 15),
                    enabled=agent_data.get("enabled", True),
                    expected_contribution=agent_data.get("expected_contribution")
                )

        # Parse synthesis
        synthesis_data = data.get("synthesis", {})
        synthesis = SynthesisConfig(
            mode=synthesis_data.get("mode", "template_only"),
            template=synthesis_data.get("template"),
            enhancement_prompt=synthesis_data.get("enhancement_prompt")
        )

        return TaskType(
            name=data.get("name", name),
            version=data.get("version", "0.0.0"),
            lifecycle_stage=data.get("lifecycle_stage", "draft"),
            goal=data.get("goal", ""),
            agents=agents,
            synthesis=synthesis,
            success_criteria=data.get("success_criteria", []),
            metrics=data.get("metrics", [])
        )

    def list_all(self) -> List[str]:
        """List all available task type names."""
        if not self._dir.exists():
            return []

        return [
            f.stem for f in self._dir.glob("*.yaml")
            if not f.name.startswith(".")
        ]

    def list_active(self) -> List[str]:
        """List only active (executable) task types."""
        active = []
        for name in self.list_all():
            try:
                task_type = self.load(name)
                if task_type.is_executable():
                    active.append(name)
            except (TaskTypeNotFoundError, TaskTypeValidationError):
                continue
        return active

    def reload(self, name: str) -> TaskType:
        """Force reload a task type from disk."""
        if name in self._cache:
            del self._cache[name]
        return self.load(name, use_cache=False)

    def clear_cache(self) -> None:
        """Clear all cached task types."""
        self._cache.clear()
```

**Step 4: Run tests to verify they pass**

```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_task_type_loader.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/task_type_loader.py
git add pa-routing-handler/tests/services/test_task_type_loader.py
git commit -m "feat: add TaskTypeLoader for loading task definitions from YAML"
```

---

### Task 2.2: Create Coordination Request/Response Models

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/models/requests.py`
- Modify: `pa-routing-handler/src/pa_routing/models/responses.py`
- Test: `pa-routing-handler/tests/models/test_coordination_models.py`

**Step 1: Write failing tests**

Create `pa-routing-handler/tests/models/test_coordination_models.py`:
```python
"""Tests for coordination request/response models."""

import pytest


class TestCoordinateRequest:
    """Tests for CoordinateRequest model."""

    def test_coordinate_request_required_fields(self):
        """CoordinateRequest requires identity_id, task_type, context."""
        from pa_routing.models.requests import CoordinateRequest

        req = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={"meeting_identifier": "Board Meeting"}
        )

        assert req.identity_id == "identity-123"
        assert req.task_type == "meeting_prep"
        assert req.context["meeting_identifier"] == "Board Meeting"

    def test_coordinate_request_optional_fields(self):
        """CoordinateRequest has optional questions_asked and conversation_id."""
        from pa_routing.models.requests import CoordinateRequest

        req = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={},
            questions_asked=["which_meeting", "focus_areas"],
            conversation_id="conv-456"
        )

        assert req.questions_asked == ["which_meeting", "focus_areas"]
        assert req.conversation_id == "conv-456"


class TestCoordinateResponse:
    """Tests for CoordinateResponse model."""

    def test_coordinate_response_success(self):
        """CoordinateResponse for successful coordination."""
        from pa_routing.models.responses import CoordinateResponse

        resp = CoordinateResponse(
            status="complete",
            task_id="task-123",
            synthesis="**Meeting** - Tomorrow 2pm",
            findings={"calendar": "[Calendar] Meeting found"},
            agents_completed=["calendar", "email"],
            agents_failed=[],
            coordination_time_ms=4500
        )

        assert resp.status == "complete"
        assert resp.task_id == "task-123"
        assert "calendar" in resp.agents_completed

    def test_coordinate_response_partial_failure(self):
        """CoordinateResponse for partial failure."""
        from pa_routing.models.responses import CoordinateResponse

        resp = CoordinateResponse(
            status="partial",
            task_id="task-123",
            synthesis="**Meeting** - Partial info",
            findings={"calendar": "[Calendar] Meeting found"},
            agents_completed=["calendar"],
            agents_failed=["email"],
            coordination_time_ms=5000
        )

        assert resp.status == "partial"
        assert "email" in resp.agents_failed
```

**Step 2: Run tests to verify they fail**

```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/models/test_coordination_models.py -v
```

Expected: FAIL (models don't exist)

**Step 3: Add CoordinateRequest to requests.py**

Add to `pa-routing-handler/src/pa_routing/models/requests.py`:
```python
class CoordinateRequest(BaseModel):
    """Request to execute multi-agent coordination."""

    identity_id: str
    task_type: str
    context: Dict[str, Any]
    questions_asked: Optional[List[str]] = None
    conversation_id: Optional[str] = None
```

**Step 4: Add CoordinateResponse to responses.py**

Add to `pa-routing-handler/src/pa_routing/models/responses.py`:
```python
class CoordinateResponse(BaseModel):
    """Response from multi-agent coordination."""

    status: str  # complete, partial, error
    task_id: str
    synthesis: Optional[str] = None
    findings: Optional[Dict[str, str]] = None
    agents_completed: List[str] = []
    agents_failed: List[str] = []
    agents_skipped: List[str] = []
    coordination_time_ms: Optional[int] = None
    error_message: Optional[str] = None
```

**Step 5: Run tests to verify they pass**

```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/models/test_coordination_models.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add pa-routing-handler/src/pa_routing/models/requests.py
git add pa-routing-handler/src/pa_routing/models/responses.py
git add pa-routing-handler/tests/models/test_coordination_models.py
git commit -m "feat: add CoordinateRequest and CoordinateResponse models"
```

---

### Task 2.3: Create Coordination Orchestrator Service

**Files:**
- Create: `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`
- Test: `pa-routing-handler/tests/services/test_coordination_orchestrator.py`

**Step 1: Write failing test**

Create `pa-routing-handler/tests/services/test_coordination_orchestrator.py`:
```python
"""Tests for coordination orchestrator."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio


class TestCoordinationOrchestrator:
    """Tests for CoordinationOrchestrator."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        return {
            "task_type_loader": MagicMock(),
            "coordination_handler": MagicMock(),
            "coordination_logger": MagicMock(),
            "letta_client": MagicMock()
        }

    @pytest.fixture
    def sample_task_type(self):
        """Create sample task type."""
        from pa_routing.services.task_type_loader import TaskType, AgentConfig, SynthesisConfig

        return TaskType(
            name="meeting_prep",
            version="1.0.0",
            lifecycle_stage="active",
            goal="Gather meeting context",
            agents={
                "calendar": AgentConfig(
                    name="calendar",
                    prompt_template="Find meeting {meeting_identifier}",
                    timeout_seconds=10
                )
            },
            synthesis=SynthesisConfig(
                mode="template_only",
                template="**{meeting_title}**\n{findings}"
            )
        )

    @pytest.mark.asyncio
    async def test_coordinate_loads_task_type(self, mock_dependencies, sample_task_type):
        """Coordinate loads task type from loader."""
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator
        from pa_routing.models.requests import CoordinateRequest

        mock_dependencies["task_type_loader"].load.return_value = sample_task_type
        mock_dependencies["coordination_handler"].start_coordinated_task.return_value = "task-123"
        mock_dependencies["coordination_handler"].get_gathered_findings.return_value = {}
        mock_dependencies["coordination_handler"].is_task_complete.return_value = True
        mock_dependencies["coordination_handler"].get_task_status.return_value = {"calendar": "done"}

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={"meeting_identifier": "Board Meeting"}
        )

        with patch.object(orchestrator, '_dispatch_to_agent', new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = None
            response = await orchestrator.coordinate(request)

        mock_dependencies["task_type_loader"].load.assert_called_with("meeting_prep")

    @pytest.mark.asyncio
    async def test_coordinate_dispatches_enabled_agents(self, mock_dependencies, sample_task_type):
        """Coordinate dispatches only enabled agents."""
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator
        from pa_routing.models.requests import CoordinateRequest

        mock_dependencies["task_type_loader"].load.return_value = sample_task_type
        mock_dependencies["coordination_handler"].start_coordinated_task.return_value = "task-123"
        mock_dependencies["coordination_handler"].get_gathered_findings.return_value = {
            "calendar": "[Calendar] Board Meeting found"
        }
        mock_dependencies["coordination_handler"].is_task_complete.return_value = True
        mock_dependencies["coordination_handler"].get_task_status.return_value = {"calendar": "done"}

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={"meeting_identifier": "Board Meeting"}
        )

        with patch.object(orchestrator, '_dispatch_to_agent', new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = None
            response = await orchestrator.coordinate(request)

        # Should dispatch to calendar agent
        mock_dispatch.assert_called()
        call_args = mock_dispatch.call_args_list[0]
        assert call_args[0][0] == "calendar"  # agent name

    @pytest.mark.asyncio
    async def test_coordinate_logs_events(self, mock_dependencies, sample_task_type):
        """Coordinate logs start and complete events."""
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator
        from pa_routing.models.requests import CoordinateRequest

        mock_dependencies["task_type_loader"].load.return_value = sample_task_type
        mock_dependencies["coordination_handler"].start_coordinated_task.return_value = "task-123"
        mock_dependencies["coordination_handler"].get_gathered_findings.return_value = {}
        mock_dependencies["coordination_handler"].is_task_complete.return_value = True
        mock_dependencies["coordination_handler"].get_task_status.return_value = {"calendar": "done"}

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={}
        )

        with patch.object(orchestrator, '_dispatch_to_agent', new_callable=AsyncMock):
            await orchestrator.coordinate(request)

        # Should log start event
        start_calls = [
            c for c in mock_dependencies["coordination_logger"].log_event.call_args_list
            if c[1].get("event_type") == "start"
        ]
        assert len(start_calls) >= 1

        # Should log complete event
        complete_calls = [
            c for c in mock_dependencies["coordination_logger"].log_event.call_args_list
            if c[1].get("event_type") == "complete"
        ]
        assert len(complete_calls) >= 1
```

**Step 2: Run tests to verify they fail**

```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_orchestrator.py -v
```

Expected: FAIL (module doesn't exist)

**Step 3: Implement CoordinationOrchestrator**

Create `pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py`:
```python
"""Coordination orchestrator - executes multi-agent coordination tasks.

This is the core orchestration engine that:
1. Loads task type configuration
2. Dispatches to specialist agents in parallel
3. Collects findings
4. Synthesizes response
5. Logs everything for refinement
"""

import asyncio
import time
from typing import Any, Dict, List, Optional
import structlog

from pa_routing.models.requests import CoordinateRequest
from pa_routing.models.responses import CoordinateResponse
from pa_routing.services.task_type_loader import TaskTypeLoader, TaskType, TaskTypeNotFoundError
from pa_routing.services.coordination_handler import CoordinationBlockHandler
from pa_routing.services.coordination_logger import CoordinationLogger

logger = structlog.get_logger()

# Agent ID mapping (from Letta)
AGENT_IDS = {
    "calendar": "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218",
    "task": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "email": "agent-b4928949-8012-4436-a3c7-a9e510785147",
    "pulse": "agent-6eb765bf-7268-4f6d-a380-c527c9c53000",
    "main": "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",
}


class CoordinationOrchestrator:
    """Orchestrates multi-agent coordination tasks."""

    def __init__(
        self,
        task_type_loader: TaskTypeLoader,
        coordination_handler: CoordinationBlockHandler,
        coordination_logger: CoordinationLogger,
        letta_client: Any
    ):
        """Initialize orchestrator with dependencies.

        Args:
            task_type_loader: Loader for task type definitions
            coordination_handler: Handler for coordination blocks
            coordination_logger: Logger for execution events
            letta_client: Letta API client
        """
        self._loader = task_type_loader
        self._handler = coordination_handler
        self._logger = coordination_logger
        self._letta = letta_client

    async def coordinate(self, request: CoordinateRequest) -> CoordinateResponse:
        """Execute a coordination task.

        Args:
            request: Coordination request with task type and context

        Returns:
            CoordinateResponse with synthesis and findings
        """
        start_time = time.time()

        # Load task type
        try:
            task_type = self._loader.load(request.task_type)
        except TaskTypeNotFoundError as e:
            return CoordinateResponse(
                status="error",
                task_id="",
                error_message=f"Task type not found: {request.task_type}"
            )

        if not task_type.is_executable():
            return CoordinateResponse(
                status="error",
                task_id="",
                error_message=f"Task type '{request.task_type}' is in draft stage"
            )

        # Initialize coordination
        enabled_agents = task_type.get_enabled_agents()
        task_id = self._handler.start_coordinated_task(
            identity_id=request.identity_id,
            task_type=request.task_type,
            context=request.context,
            required_agents=list(enabled_agents.keys())
        )

        # Log start
        self._logger.log_event(
            event_type="start",
            task_id=task_id,
            identity_id=request.identity_id,
            task_type=request.task_type,
            task_version=task_type.version,
            data={
                "context": request.context,
                "questions_asked": request.questions_asked,
                "agents": list(enabled_agents.keys())
            }
        )

        # Dispatch agents in parallel
        dispatch_results = await self._dispatch_all_agents(
            task_id=task_id,
            identity_id=request.identity_id,
            task_type=task_type,
            context=request.context
        )

        # Wait for contributions (with timeout)
        await self._wait_for_contributions(
            identity_id=request.identity_id,
            task_type=task_type,
            task_id=task_id
        )

        # Get status and findings
        status = self._handler.get_task_status(request.identity_id)
        findings = self._handler.get_gathered_findings(request.identity_id)

        # Determine completion status
        agents_completed = [a for a, s in status.items() if s == "done" and a != "task_id"]
        agents_failed = [a for a, s in status.items() if s in ("error", "timeout") and a != "task_id"]
        agents_skipped = [a for a in enabled_agents if a not in agents_completed and a not in agents_failed]

        # Synthesize response
        synthesis = await self._synthesize(
            task_type=task_type,
            findings=findings,
            context=request.context
        )

        # Complete task and archive
        self._handler.complete_task(request.identity_id)

        # Calculate elapsed time
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Log completion
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
                "synthesis_length": len(synthesis) if synthesis else 0
            }
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
            coordination_time_ms=elapsed_ms
        )

    async def _dispatch_all_agents(
        self,
        task_id: str,
        identity_id: str,
        task_type: TaskType,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch all enabled agents in parallel."""
        enabled_agents = task_type.get_enabled_agents()

        tasks = []
        for agent_name, agent_config in enabled_agents.items():
            # Build prompt from template
            prompt = self._build_agent_prompt(agent_config, context)

            tasks.append(
                self._dispatch_to_agent(
                    agent_name=agent_name,
                    prompt=prompt,
                    identity_id=identity_id,
                    task_id=task_id,
                    task_type=task_type.name,
                    timeout=agent_config.timeout_seconds
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        return dict(zip(enabled_agents.keys(), results))

    def _build_agent_prompt(
        self,
        agent_config: Any,
        context: Dict[str, Any]
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
        timeout: int
    ) -> Optional[str]:
        """Dispatch a single agent and wait for response."""
        agent_id = AGENT_IDS.get(agent_name)
        if not agent_id:
            logger.warning("agent_not_found", agent_name=agent_name)
            return None

        # Log dispatch
        self._logger.log_event(
            event_type="agent_dispatch",
            task_id=task_id,
            identity_id=identity_id,
            task_type=task_type,
            data={"agent": agent_name, "prompt": prompt[:200]}
        )

        try:
            # Send message to agent via Letta
            response = await asyncio.wait_for(
                self._send_to_letta(agent_id, prompt, identity_id),
                timeout=timeout
            )

            # Log contribution
            self._logger.log_event(
                event_type="agent_contributed",
                task_id=task_id,
                identity_id=identity_id,
                task_type=task_type,
                data={
                    "agent": agent_name,
                    "contribution_length": len(response) if response else 0
                }
            )

            return response

        except asyncio.TimeoutError:
            self._logger.log_event(
                event_type="agent_timeout",
                task_id=task_id,
                identity_id=identity_id,
                task_type=task_type,
                data={"agent": agent_name, "timeout_seconds": timeout}
            )
            return None

        except Exception as e:
            self._logger.log_event(
                event_type="agent_error",
                task_id=task_id,
                identity_id=identity_id,
                task_type=task_type,
                data={"agent": agent_name, "error": str(e)}
            )
            return None

    async def _send_to_letta(
        self,
        agent_id: str,
        message: str,
        identity_id: str
    ) -> Optional[str]:
        """Send message to Letta agent."""
        # This will be implemented to call the Letta API
        # For now, return None - will be filled in during integration
        try:
            response = self._letta.send_message(
                agent_id=agent_id,
                message=message,
                role="user"
            )
            # Extract assistant response
            for msg in response.messages:
                if hasattr(msg, 'assistant_message') and msg.assistant_message:
                    return msg.assistant_message
            return None
        except Exception as e:
            logger.error("letta_send_failed", agent_id=agent_id, error=str(e))
            return None

    async def _wait_for_contributions(
        self,
        identity_id: str,
        task_type: TaskType,
        task_id: str
    ) -> None:
        """Wait for agent contributions with polling."""
        enabled_agents = task_type.get_enabled_agents()
        max_timeout = max(a.timeout_seconds for a in enabled_agents.values())
        deadline = time.time() + max_timeout + 5  # Extra buffer

        while time.time() < deadline:
            if self._handler.is_task_complete(identity_id):
                break

            # Check for contributions
            for agent_name in enabled_agents:
                self._handler.check_agent_contribution(identity_id, agent_name)

            await asyncio.sleep(0.5)

    async def _synthesize(
        self,
        task_type: TaskType,
        findings: Dict[str, str],
        context: Dict[str, Any]
    ) -> str:
        """Synthesize response from findings."""
        synthesis_config = task_type.synthesis

        if synthesis_config.mode == "template_only":
            return self._apply_template(synthesis_config.template, findings, context)

        elif synthesis_config.mode == "template_with_enhancement":
            template_output = self._apply_template(synthesis_config.template, findings, context)
            # Enhancement via Main Agent would go here
            # For MVP, just return template output
            return template_output

        elif synthesis_config.mode == "main_agent_only":
            # Full synthesis via Main Agent would go here
            # For MVP, concatenate findings
            return "\n\n".join(findings.values())

        return ""

    def _apply_template(
        self,
        template: Optional[str],
        findings: Dict[str, str],
        context: Dict[str, Any]
    ) -> str:
        """Apply template with findings and context."""
        if not template:
            return "\n\n".join(findings.values())

        result = template

        # Replace context placeholders
        for key, value in context.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))

        # Replace findings placeholders
        result = result.replace("{findings}", "\n".join(findings.values()))

        for agent_name, finding in findings.items():
            placeholder = "{" + agent_name + "_findings}"
            if placeholder in result:
                result = result.replace(placeholder, finding)

        return result
```

**Step 4: Run tests to verify they pass**

```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/services/test_coordination_orchestrator.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_orchestrator.py
git add pa-routing-handler/tests/services/test_coordination_orchestrator.py
git commit -m "feat: add CoordinationOrchestrator for multi-agent task execution"
```

---

### Task 2.4: Create /v1/coordinate Endpoint

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/routers/routing.py`
- Test: `pa-routing-handler/tests/routers/test_coordinate_endpoint.py`

**Step 1: Write failing test**

Create `pa-routing-handler/tests/routers/test_coordinate_endpoint.py`:
```python
"""Tests for /v1/coordinate endpoint."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, AsyncMock


class TestCoordinateEndpoint:
    """Tests for coordinate endpoint."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator."""
        from pa_routing.models.responses import CoordinateResponse

        orchestrator = MagicMock()
        orchestrator.coordinate = AsyncMock(return_value=CoordinateResponse(
            status="complete",
            task_id="task-123",
            synthesis="Test synthesis",
            findings={"calendar": "[Calendar] Test"},
            agents_completed=["calendar"],
            agents_failed=[],
            coordination_time_ms=1000
        ))
        return orchestrator

    def test_coordinate_endpoint_success(self, mock_orchestrator):
        """Coordinate endpoint returns successful response."""
        from pa_routing.main import app
        from pa_routing.routers import routing

        with patch.object(routing, '_orchestrator', mock_orchestrator):
            client = TestClient(app)
            response = client.post("/v1/coordinate", json={
                "identity_id": "identity-123",
                "task_type": "meeting_prep",
                "context": {"meeting_identifier": "Board Meeting"}
            })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "complete"
        assert data["task_id"] == "task-123"

    def test_coordinate_endpoint_validates_request(self):
        """Coordinate endpoint validates required fields."""
        from pa_routing.main import app

        client = TestClient(app)
        response = client.post("/v1/coordinate", json={
            "identity_id": "identity-123"
            # Missing task_type and context
        })

        assert response.status_code == 422  # Validation error
```

**Step 2: Run tests to verify they fail**

```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/routers/test_coordinate_endpoint.py -v
```

Expected: FAIL (endpoint doesn't exist)

**Step 3: Add coordinate endpoint to routing.py**

Add to `pa-routing-handler/src/pa_routing/routers/routing.py`:

```python
# Near top with other imports
from pa_routing.models.requests import CoordinateRequest
from pa_routing.models.responses import CoordinateResponse
from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator
from pa_routing.services.task_type_loader import TaskTypeLoader
from pa_routing.services.coordination_logger import CoordinationLogger

# Initialize orchestrator (after other initializations)
_task_type_loader = None
_coordination_logger = None
_orchestrator = None

def init_coordination_orchestrator(supabase_client, letta_client, coordination_handler):
    """Initialize coordination orchestrator with dependencies."""
    global _task_type_loader, _coordination_logger, _orchestrator

    _task_type_loader = TaskTypeLoader("docs/task-types")
    _coordination_logger = CoordinationLogger(supabase_client)
    _orchestrator = CoordinationOrchestrator(
        task_type_loader=_task_type_loader,
        coordination_handler=coordination_handler,
        coordination_logger=_coordination_logger,
        letta_client=letta_client
    )

# Add endpoint
@router.post("/coordinate", response_model=CoordinateResponse)
async def coordinate(request: CoordinateRequest) -> CoordinateResponse:
    """Execute multi-agent coordination task.

    This endpoint orchestrates multiple specialist agents to gather
    information and synthesize a response for complex tasks.
    """
    if _orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="Coordination orchestrator not initialized"
        )

    return await _orchestrator.coordinate(request)
```

**Step 4: Update main.py to initialize orchestrator**

Add to startup in `pa-routing-handler/src/pa_routing/main.py`:
```python
from pa_routing.routers.routing import init_coordination_orchestrator

@app.on_event("startup")
async def startup():
    # ... existing startup code ...

    # Initialize coordination orchestrator
    if supabase and _letta_client and coordination_handler:
        init_coordination_orchestrator(
            supabase_client=supabase,
            letta_client=_letta_client,
            coordination_handler=coordination_handler
        )
        logger.info("coordination_orchestrator_initialized")
```

**Step 5: Run tests to verify they pass**

```bash
cd /Volumes/main-drive/ai-PA/pa-routing-handler && python -m pytest tests/routers/test_coordinate_endpoint.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add pa-routing-handler/src/pa_routing/routers/routing.py
git add pa-routing-handler/src/pa_routing/main.py
git add pa-routing-handler/tests/routers/test_coordinate_endpoint.py
git commit -m "feat: add /v1/coordinate endpoint for multi-agent orchestration"
```

---

## Phase 3: Main Agent Integration

### Task 3.1: Create coordinate_task Letta Tool

**Files:**
- Create: `letta/tools/coordinate_task.py`
- Create: `letta/register_coordinate_task_tool.py`

**Step 1: Create tool implementation**

Create `letta/tools/coordinate_task.py`:
```python
"""
Coordination task tool for Main Agent.

Allows Main Agent to trigger multi-agent coordination
after gathering context conversationally.
"""

from typing import Dict, Any, Optional


def coordinate_task(
    task_type: str,
    context: str,
    questions_asked: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute multi-agent coordination for a defined task type.

    Call this after gathering sufficient context through conversation.
    Available task types can be found in docs/task-types/.

    Args:
        task_type: Name of the task type (e.g., "meeting_prep", "project_status")
        context: JSON string with task-specific context gathered from conversation.
                 Example: {"meeting_identifier": "Board Meeting tomorrow 2pm",
                          "focus_areas": ["participants", "documents"]}
        questions_asked: Optional JSON array of question IDs asked before execution.
                        Example: ["which_meeting", "focus_areas"]

    Returns:
        Dictionary with:
        - status: "complete", "partial", or "error"
        - synthesis: Synthesized response text
        - findings: Dict of agent name to contribution
        - agents_completed: List of agents that contributed
        - agents_failed: List of agents that failed/timed out
        - coordination_time_ms: Total coordination time
    """
    import json
    import requests
    import traceback
    import os

    try:
        # Parse context JSON
        context_dict = json.loads(context) if isinstance(context, str) else context

        # Parse questions if provided
        questions = []
        if questions_asked:
            questions = json.loads(questions_asked) if isinstance(questions_asked, str) else questions_asked

        # Get routing handler URL
        routing_handler_url = os.getenv(
            "PA_ROUTING_HANDLER_URL",
            "http://pa-routing-handler:5201"
        )

        # Get identity ID from environment or use default
        identity_id = os.getenv("CURRENT_IDENTITY_ID", "identity-default")

        # Call coordination endpoint
        response = requests.post(
            f"{routing_handler_url}/v1/coordinate",
            json={
                "identity_id": identity_id,
                "task_type": task_type,
                "context": context_dict,
                "questions_asked": questions
            },
            timeout=120  # 2 minute timeout for full coordination
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Coordination failed: {response.status_code} - {response.text[:500]}"
            }

        result = response.json()

        return {
            "status": result.get("status", "unknown"),
            "synthesis": result.get("synthesis", ""),
            "findings": result.get("findings", {}),
            "agents_completed": result.get("agents_completed", []),
            "agents_failed": result.get("agents_failed", []),
            "coordination_time_ms": result.get("coordination_time_ms")
        }

    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "error_message": f"Invalid JSON in context: {str(e)}"
        }
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "error_message": "Coordination timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}"
        }
```

**Step 2: Create registration script**

Create `letta/register_coordinate_task_tool.py`:
```python
#!/usr/bin/env python3
"""Register coordinate_task tool with Letta."""

import os
import inspect
from letta import create_client

# Import the tool function
from tools.coordinate_task import coordinate_task

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")


def main():
    print("=" * 60)
    print("Register coordinate_task Tool")
    print("=" * 60)

    client = create_client(base_url=LETTA_BASE)

    # Get function source
    source = inspect.getsource(coordinate_task)

    # Check if tool already exists
    existing_tools = client.list_tools()
    existing_names = [t.name for t in existing_tools]

    if "coordinate_task" in existing_names:
        print("Tool 'coordinate_task' already exists")
        # Find and update
        for tool in existing_tools:
            if tool.name == "coordinate_task":
                client.update_tool(
                    tool_id=tool.id,
                    source_code=source
                )
                print(f"Updated tool: {tool.id}")
                break
    else:
        # Create new tool
        tool = client.create_tool(
            func=coordinate_task,
            name="coordinate_task"
        )
        print(f"Created tool: {tool.id}")

    print("Done!")


if __name__ == "__main__":
    main()
```

**Step 3: Test tool registration**

```bash
cd /Volumes/main-drive/ai-PA/letta && python register_coordinate_task_tool.py
```

**Step 4: Commit**

```bash
git add letta/tools/coordinate_task.py
git add letta/register_coordinate_task_tool.py
git commit -m "feat: add coordinate_task tool for Main Agent"
```

---

### Task 3.2: Attach Tool to Main Agent

**Files:**
- Create: `letta/attach_coordinate_task_to_main_agent.py`

**Step 1: Create attachment script**

Create `letta/attach_coordinate_task_to_main_agent.py`:
```python
#!/usr/bin/env python3
"""Attach coordinate_task tool to Main Agent."""

import os
from letta import create_client

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"


def main():
    print("=" * 60)
    print("Attach coordinate_task to Main Agent")
    print("=" * 60)

    client = create_client(base_url=LETTA_BASE)

    # Find the tool
    tools = client.list_tools()
    coordinate_tool = None
    for tool in tools:
        if tool.name == "coordinate_task":
            coordinate_tool = tool
            break

    if not coordinate_tool:
        print("ERROR: coordinate_task tool not found. Run register script first.")
        return 1

    print(f"Found tool: {coordinate_tool.id}")

    # Get Main Agent
    agent = client.get_agent(MAIN_AGENT_ID)
    print(f"Main Agent: {agent.name}")

    # Check if already attached
    agent_tools = [t.name for t in agent.tools]
    if "coordinate_task" in agent_tools:
        print("Tool already attached to Main Agent")
        return 0

    # Attach tool
    client.add_tool_to_agent(
        agent_id=MAIN_AGENT_ID,
        tool_id=coordinate_tool.id
    )

    print("Successfully attached coordinate_task to Main Agent")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
```

**Step 2: Run attachment script**

```bash
cd /Volumes/main-drive/ai-PA/letta && python attach_coordinate_task_to_main_agent.py
```

**Step 3: Commit**

```bash
git add letta/attach_coordinate_task_to_main_agent.py
git commit -m "feat: attach coordinate_task tool to Main Agent"
```

---

### Task 3.3: Update Main Agent Persona with Task Development Skill

**Files:**
- Create: `letta/update_main_agent_task_development_skill.py`

**Step 1: Create persona update script**

Create `letta/update_main_agent_task_development_skill.py`:
```python
#!/usr/bin/env python3
"""Update Main Agent persona with task development skill."""

import os
import json
import urllib.request
import urllib.error

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"

TASK_DEVELOPMENT_SKILL = '''

## Multi-Agent Task Development

You can develop, execute, and refine multi-agent coordination tasks through a structured lifecycle.

### Available Task Types

Check docs/task-types/ for available task types. Each defines which agents to coordinate and how to synthesize results.

### Executing Coordination

For tasks matching an active task type:
1. Recognize the task type from user request
2. Gather scenario-specific context conversationally:
   - Ask clarifying questions one at a time
   - Confirm understanding before proceeding
3. Call coordinate_task() with gathered context:
   - task_type: Name of the task type
   - context: JSON with gathered details
4. Deliver the synthesized result

Example:
User: "Prep me for my meeting tomorrow"
You: "Which meeting? I see Board Meeting at 2pm and 1:1 with Sarah at 4pm."
User: "Board meeting"
You: "Any specific focus, or should I gather everything?"
User: "Focus on participants and recent context"
You: *calls coordinate_task("meeting_prep", {"meeting_identifier": "Board Meeting tomorrow 2pm", "focus_areas": ["participants", "recent_context"]})*
You: *delivers synthesized response*

### Developing New Task Types

When user wants to create a new coordination task:
1. **Brainstorm**: Survey available agents, ask questions to understand goal
2. **Design**: Create prompts, templates, success criteria
3. **Create**: Write YAML file to docs/task-types/
4. **Execute**: Test with real scenarios
5. **Refine**: Analyze patterns, propose improvements

Ask one question at a time. Propose transitions at phase boundaries.
'''


def http_get(url):
    """Make HTTP GET request."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"GET Error: {e}")
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
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')[:200]}")
        return None


def main():
    print("=" * 60)
    print("Update Main Agent with Task Development Skill")
    print("=" * 60)

    # Get agent's memory blocks
    blocks = http_get(f"{LETTA_BASE}/v1/agents/{MAIN_AGENT_ID}/core-memory/blocks")
    if not blocks:
        print("Could not get blocks")
        return 1

    # Find persona block
    persona_block = None
    for block in blocks:
        if block.get("label") == "persona":
            persona_block = block
            break

    if not persona_block:
        print("No persona block found")
        return 1

    current_persona = persona_block.get("value", "")
    block_id = persona_block.get("id")

    # Check if already has skill
    if "Multi-Agent Task Development" in current_persona:
        print("Already has task development skill")
        return 0

    # Add skill
    new_persona = current_persona + TASK_DEVELOPMENT_SKILL

    # Check length
    if len(new_persona) > 8500:
        print(f"ERROR: New persona exceeds 8500 chars ({len(new_persona)})")
        return 1

    print(f"Length: {len(current_persona)} -> {len(new_persona)} chars")

    # Update
    result = http_patch(
        f"{LETTA_BASE}/v1/blocks/{block_id}",
        {"value": new_persona}
    )

    if result:
        print("Updated Main Agent persona with task development skill")
        return 0
    else:
        print("Failed to update")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
```

**Step 2: Run persona update**

```bash
cd /Volumes/main-drive/ai-PA/letta && python update_main_agent_task_development_skill.py
```

**Step 3: Commit**

```bash
git add letta/update_main_agent_task_development_skill.py
git commit -m "feat: add task development skill to Main Agent persona"
```

---

## Phase 4: Observability

### Task 4.1: Add Refinement Analysis Helpers

**Files:**
- Modify: `pa-routing-handler/src/pa_routing/services/coordination_logger.py`

**Step 1: Add refinement analysis methods**

Add to `CoordinationLogger` class:
```python
def get_execution_summary(
    self,
    task_type: str,
    limit: int = 10
) -> Dict[str, Any]:
    """Get execution summary for refinement review.

    Args:
        task_type: Task type to analyze
        limit: Number of recent executions to analyze

    Returns:
        Summary dict with statistics and patterns
    """
    try:
        # Get complete events
        completions = (
            self._supabase.table("coordination_logs")
            .select("*")
            .eq("task_type", task_type)
            .eq("event_type", "complete")
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )

        if not completions.data:
            return {"executions": 0, "message": "No executions found"}

        # Calculate statistics
        times = [r.get("elapsed_ms", 0) for r in completions.data if r.get("elapsed_ms")]
        avg_time = sum(times) / len(times) if times else 0

        # Get agent stats
        agent_stats = self.get_agent_contribution_stats(task_type)

        # Get question patterns
        starts = (
            self._supabase.table("coordination_logs")
            .select("data")
            .eq("task_type", task_type)
            .eq("event_type", "start")
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )

        question_counts: Dict[str, int] = {}
        for start in starts.data or []:
            questions = start.get("data", {}).get("questions_asked", [])
            for q in questions:
                question_counts[q] = question_counts.get(q, 0) + 1

        return {
            "executions": len(completions.data),
            "avg_time_ms": int(avg_time),
            "agent_stats": agent_stats,
            "question_patterns": question_counts,
            "recent_task_ids": [r.get("task_id") for r in completions.data[:5]]
        }

    except Exception as e:
        logger.warning("execution_summary_failed", error=str(e))
        return {"error": str(e)}
```

**Step 2: Commit**

```bash
git add pa-routing-handler/src/pa_routing/services/coordination_logger.py
git commit -m "feat: add refinement analysis helpers to CoordinationLogger"
```

---

### Task 4.2: Create Refinement Analysis Tool for Main Agent

**Files:**
- Create: `letta/tools/analyze_task_executions.py`
- Create: `letta/register_analyze_task_tool.py`

**Step 1: Create analysis tool**

Create `letta/tools/analyze_task_executions.py`:
```python
"""
Task execution analysis tool for Main Agent.

Enables guided refinement by analyzing execution patterns.
"""

from typing import Dict, Any


def analyze_task_executions(
    task_type: str,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Analyze recent executions of a task type for refinement.

    Use this to review how a task type is performing and identify
    opportunities for improvement.

    Args:
        task_type: Name of the task type to analyze (e.g., "meeting_prep")
        limit: Optional number of recent executions to analyze (default: 10)

    Returns:
        Dictionary with:
        - executions: Number of executions analyzed
        - avg_time_ms: Average coordination time
        - agent_stats: Per-agent contribution statistics
        - question_patterns: Which questions were asked most often
        - recommendations: Suggested improvements based on patterns
    """
    import json
    import requests
    import traceback
    import os

    try:
        # Get routing handler URL
        routing_handler_url = os.getenv(
            "PA_ROUTING_HANDLER_URL",
            "http://pa-routing-handler:5201"
        )

        # Call analysis endpoint
        params = {"task_type": task_type}
        if limit:
            params["limit"] = limit

        response = requests.get(
            f"{routing_handler_url}/v1/coordinate/analysis",
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Analysis failed: {response.status_code}"
            }

        data = response.json()

        # Generate recommendations based on patterns
        recommendations = []

        agent_stats = data.get("agent_stats", {})
        for agent, stats in agent_stats.items():
            contribution_rate = (
                stats.get("contributions", 0) /
                max(stats.get("dispatches", 1), 1) * 100
            )
            if contribution_rate < 50:
                recommendations.append(
                    f"Consider disabling '{agent}' - only {contribution_rate:.0f}% contribution rate"
                )

        question_patterns = data.get("question_patterns", {})
        executions = data.get("executions", 0)
        for question, count in question_patterns.items():
            if count == executions and executions >= 3:
                recommendations.append(
                    f"Question '{question}' asked every time - consider making it required or auto-detecting"
                )

        return {
            "status": "ok",
            "executions": data.get("executions", 0),
            "avg_time_ms": data.get("avg_time_ms", 0),
            "agent_stats": agent_stats,
            "question_patterns": question_patterns,
            "recommendations": recommendations
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}"
        }
```

**Step 2: Create and run registration script**

Create `letta/register_analyze_task_tool.py` (similar pattern to coordinate_task).

**Step 3: Commit**

```bash
git add letta/tools/analyze_task_executions.py
git add letta/register_analyze_task_tool.py
git commit -m "feat: add analyze_task_executions tool for guided refinement"
```

---

## Phase 5: First Task Type

### Task 5.1: Create meeting_prep Task Type

**Files:**
- Create: `docs/task-types/meeting_prep.yaml`

**Step 1: Create task type definition**

Create `docs/task-types/meeting_prep.yaml`:
```yaml
# Meeting Prep Task Type
# Gathers context from multiple agents to prepare for meetings

name: meeting_prep
version: 1.0.0
lifecycle_stage: active
created: 2026-01-29

goal: "Gather relevant context before meetings including participants, documents, and recent communications"

trigger: "User asks to prep for a specific meeting"

success_criteria:
  - "User proceeds to meeting without follow-up questions"
  - "Participants and their context are accurate"
  - "Relevant documents are surfaced"
  - "Recent communications provide useful context"

agents:
  calendar:
    prompt_template: |
      Find the meeting matching '{meeting_identifier}'.

      Return:
      - Meeting title, date, time, and location
      - All participants with their response status (accepted/tentative/declined)
      - Any scheduling conflicts in the 30 minutes before or after
      - Link to the calendar event if available

      Format your response as a brief summary starting with [Calendar HH:MM].
    timeout_seconds: 15
    expected_contribution: "Event details, participant list, conflicts"

  document:
    prompt_template: |
      Search for documents related to '{meeting_title}' or shared by/with
      these participants: {participants}.

      Look for:
      - Meeting agendas or prep materials
      - Recent shared documents
      - Action items from previous related meetings

      Format your response as a brief summary starting with [Document HH:MM].
    timeout_seconds: 20
    expected_contribution: "Relevant docs, agendas, action items"

  email:
    prompt_template: |
      Find email threads from the last {lookback_days} days involving
      these participants: {participants}.

      Focus on:
      - Threads mentioning '{meeting_title}' or related topics
      - Recent communications that provide context
      - Any concerns, questions, or action items raised

      Format your response as a brief summary starting with [Email HH:MM].
    timeout_seconds: 20
    expected_contribution: "Recent communications, concerns raised"
    default_lookback_days: 7

  pulse:
    enabled: true
    prompt_template: |
      Check availability and status for these participants: {participants}.

      Look for:
      - Who is OOO or has limited availability
      - Any status updates relevant to the meeting
      - Working hours or timezone considerations

      Format your response as a brief summary starting with [Pulse HH:MM].
    timeout_seconds: 10
    expected_contribution: "Availability, OOO status"

synthesis:
  mode: template_with_enhancement
  template: |
    **{meeting_title}** - {meeting_time}

    **Participants:**
    {calendar_findings}

    **Prep Materials:**
    {document_findings}

    **Recent Context:**
    {email_findings}

    **Availability Notes:**
    {pulse_findings}
  enhancement_prompt: |
    Review these meeting prep findings and add:
    - Any concerns or blockers that should be addressed
    - Suggested preparation priorities
    - Questions to consider raising in the meeting

    Keep additions brief and actionable.

metrics:
  - agent_contribution_rate
  - follow_up_questions_needed
  - time_to_completion
  - synthesis_length

refinement_log: []
```

**Step 2: Commit**

```bash
git add docs/task-types/meeting_prep.yaml
git commit -m "feat: add meeting_prep task type definition"
```

---

### Task 5.2: Integration Test

**Files:**
- Manual testing steps

**Step 1: Start services**

```bash
docker-compose up -d pa-routing-handler letta
```

**Step 2: Verify task type loads**

```bash
curl http://localhost:5201/v1/coordinate/task-types
```

Expected: List includes "meeting_prep"

**Step 3: Test coordination manually**

```bash
curl -X POST http://localhost:5201/v1/coordinate \
  -H "Content-Type: application/json" \
  -d '{
    "identity_id": "identity-test",
    "task_type": "meeting_prep",
    "context": {
      "meeting_identifier": "Team Standup tomorrow",
      "meeting_title": "Team Standup",
      "participants": ["alice@example.com", "bob@example.com"],
      "lookback_days": 7
    },
    "questions_asked": ["which_meeting", "focus"]
  }'
```

Expected: Response with synthesis and findings from agents.

**Step 4: Verify logs**

```bash
docker exec supabase-db psql -U postgres -d postgres -c \
  "SELECT event_type, task_type, elapsed_ms FROM pa_web.coordination_logs ORDER BY timestamp DESC LIMIT 10"
```

Expected: Events logged for start, agent_dispatch, agent_contributed, complete.

**Step 5: Test via Main Agent (optional)**

Talk to Main Agent: "Prep me for my meeting tomorrow"

Expected: Main Agent asks clarifying questions, then calls coordinate_task tool.

---

## Success Criteria

| Criterion | Verification |
|-----------|--------------|
| Task types directory exists | `ls docs/task-types/` shows files |
| Logging table created | `\d pa_web.coordination_logs` shows schema |
| Endpoint accessible | `curl /v1/coordinate` returns response |
| Task type loads from YAML | meeting_prep loads without error |
| Coordination executes | Agents dispatched, findings gathered |
| Events logged | Query logs shows all event types |
| Main Agent can coordinate | Tool call works end-to-end |

---

## Execution Notes

- Phase 1 tasks can run in parallel (infrastructure setup)
- Phase 2 tasks are sequential (build on each other)
- Phase 3 depends on Phase 2 completion
- Phase 4 can run in parallel with Phase 5
- Phase 5 is the integration verification
