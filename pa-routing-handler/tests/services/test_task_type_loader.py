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


class TestTaskTypePhaseConfig:
    """Tests for phased execution fields: resolve_agent, evaluation/synthesis prompts."""

    def test_parse_resolve_agent(self, tmp_path):
        """YAML with resolve_agent parses correctly."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        yaml_file = tmp_path / "phased_task.yaml"
        yaml_file.write_text("""
name: phased_task
version: 2.0.0
lifecycle_stage: active
goal: "Phased execution test"
resolve_agent: calendar

agents:
  calendar:
    prompt_template: "Resolve meeting details"
    timeout_seconds: 10
  email:
    prompt_template: "Gather email context"
    timeout_seconds: 15

synthesis:
  mode: template_with_enhancement
  template: "Results: {findings}"
""")

        loader = TaskTypeLoader(str(tmp_path))
        task_type = loader.load("phased_task")

        assert task_type.resolve_agent == "calendar"

    def test_get_gather_agents_excludes_resolve(self, tmp_path):
        """get_gather_agents() returns enabled agents minus the resolve agent."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        yaml_file = tmp_path / "phased_task.yaml"
        yaml_file.write_text("""
name: phased_task
version: 2.0.0
lifecycle_stage: active
goal: "Phased execution test"
resolve_agent: calendar

agents:
  calendar:
    prompt_template: "Resolve meeting details"
    timeout_seconds: 10
  email:
    prompt_template: "Gather email context"
    timeout_seconds: 15
  slack:
    prompt_template: "Search slack messages"
    timeout_seconds: 12

synthesis:
  mode: template_with_enhancement
  template: "Results: {findings}"
""")

        loader = TaskTypeLoader(str(tmp_path))
        task_type = loader.load("phased_task")

        gather_agents = task_type.get_gather_agents()

        # resolve agent should be excluded
        assert "calendar" not in gather_agents
        # other enabled agents should be present
        assert "email" in gather_agents
        assert "slack" in gather_agents

    def test_parse_evaluation_and_synthesis_prompts(self, tmp_path):
        """evaluation_prompt and synthesis_prompt parse from YAML synthesis section."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        yaml_file = tmp_path / "prompted_task.yaml"
        yaml_file.write_text("""
name: prompted_task
version: 2.0.0
lifecycle_stage: active
goal: "Prompt parsing test"

agents:
  calendar:
    prompt_template: "Find meetings"
    timeout_seconds: 10

synthesis:
  mode: template_with_enhancement
  template: "Results: {findings}"
  evaluation_prompt: "Evaluate whether the gathered information is sufficient."
  synthesis_prompt: "Synthesize all agent responses into a coherent briefing."
""")

        loader = TaskTypeLoader(str(tmp_path))
        task_type = loader.load("prompted_task")

        assert task_type.synthesis.evaluation_prompt == "Evaluate whether the gathered information is sufficient."
        assert task_type.synthesis.synthesis_prompt == "Synthesize all agent responses into a coherent briefing."

    def test_resolve_agent_defaults_to_none(self, tmp_path):
        """v1 YAML without resolve_agent still works, defaults to None."""
        from pa_routing.services.task_type_loader import TaskTypeLoader

        yaml_file = tmp_path / "v1_task.yaml"
        yaml_file.write_text("""
name: v1_task
version: 1.0.0
lifecycle_stage: active
goal: "Legacy v1 task"

agents:
  calendar:
    prompt_template: "Find meetings"
    timeout_seconds: 10
  email:
    prompt_template: "Find emails"
    timeout_seconds: 15

synthesis:
  mode: template_only
  template: "Results: {findings}"
""")

        loader = TaskTypeLoader(str(tmp_path))
        task_type = loader.load("v1_task")

        assert task_type.resolve_agent is None
        assert task_type.synthesis.evaluation_prompt is None
        assert task_type.synthesis.synthesis_prompt is None

        # get_gather_agents should fall back to get_enabled_agents
        gather_agents = task_type.get_gather_agents()
        assert "calendar" in gather_agents
        assert "email" in gather_agents
