"""Task type loader - loads coordination task definitions from YAML files.

Task types define how multi-agent coordination works for specific use cases.
They are stored as YAML files in docs/task-types/ and loaded at runtime.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
import yaml

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
    evaluation_prompt: Optional[str] = None
    synthesis_prompt: Optional[str] = None


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
    resolve_agent: Optional[str] = None

    def get_enabled_agents(self) -> Dict[str, AgentConfig]:
        """Get only enabled agents."""
        return {name: config for name, config in self.agents.items() if config.enabled}

    def get_gather_agents(self) -> Dict[str, AgentConfig]:
        """Get enabled agents excluding the resolve agent."""
        return {
            name: config
            for name, config in self.agents.items()
            if config.enabled and name != self.resolve_agent
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
                    expected_contribution=agent_data.get("expected_contribution"),
                )

        # Parse synthesis
        synthesis_data = data.get("synthesis", {})
        synthesis = SynthesisConfig(
            mode=synthesis_data.get("mode", "template_only"),
            template=synthesis_data.get("template"),
            enhancement_prompt=synthesis_data.get("enhancement_prompt"),
            evaluation_prompt=synthesis_data.get("evaluation_prompt"),
            synthesis_prompt=synthesis_data.get("synthesis_prompt"),
        )

        return TaskType(
            name=data.get("name", name),
            version=data.get("version", "0.0.0"),
            lifecycle_stage=data.get("lifecycle_stage", "draft"),
            goal=data.get("goal", ""),
            agents=agents,
            synthesis=synthesis,
            success_criteria=data.get("success_criteria", []),
            metrics=data.get("metrics", []),
            resolve_agent=data.get("resolve_agent"),
        )

    def list_all(self) -> List[str]:
        """List all available task type names."""
        if not self._dir.exists():
            return []

        return [f.stem for f in self._dir.glob("*.yaml") if not f.name.startswith(".")]

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
