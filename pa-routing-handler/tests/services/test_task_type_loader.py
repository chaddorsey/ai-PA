"""Tests for task type loader."""

import tempfile
from pathlib import Path

import pytest


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
        from pa_routing.services.task_type_loader import (
            TaskTypeLoader,
            TaskTypeNotFoundError,
        )

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
