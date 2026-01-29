"""Tests for coordination orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCoordinationOrchestrator:
    """Tests for CoordinationOrchestrator."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        return {
            "task_type_loader": MagicMock(),
            "coordination_handler": MagicMock(),
            "coordination_logger": MagicMock(),
            "letta_base_url": "http://localhost:8283"
        }

    @pytest.fixture
    def sample_task_type(self):
        """Create sample task type."""
        from pa_routing.services.task_type_loader import AgentConfig, SynthesisConfig, TaskType

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

    @pytest.fixture
    def multi_agent_task_type(self):
        """Create task type with multiple agents."""
        from pa_routing.services.task_type_loader import AgentConfig, SynthesisConfig, TaskType

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
                ),
                "email": AgentConfig(
                    name="email",
                    prompt_template="Find emails about {meeting_title}",
                    timeout_seconds=15
                )
            },
            synthesis=SynthesisConfig(
                mode="template_only",
                template="**{meeting_title}**\n{findings}"
            )
        )

    @pytest.fixture
    def draft_task_type(self):
        """Create draft (non-executable) task type."""
        from pa_routing.services.task_type_loader import SynthesisConfig, TaskType

        return TaskType(
            name="draft_task",
            version="0.1.0",
            lifecycle_stage="draft",
            goal="Work in progress",
            agents={},
            synthesis=SynthesisConfig(mode="template_only")
        )

    @pytest.mark.asyncio
    async def test_coordinate_loads_task_type(
        self, mock_dependencies, sample_task_type
    ):
        """Coordinate loads task type from loader."""
        from pa_routing.models.requests import CoordinateRequest
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        mock_dependencies["task_type_loader"].load.return_value = sample_task_type
        handler = mock_dependencies["coordination_handler"]
        handler.start_coordinated_task = AsyncMock(return_value="task-123")
        handler.get_gathered_findings = AsyncMock(return_value={})
        handler.is_task_complete = AsyncMock(return_value=True)
        handler.get_task_status = AsyncMock(return_value={"calendar": "done"})
        handler.complete_task = AsyncMock(return_value=True)

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={"meeting_identifier": "Board Meeting"}
        )

        with patch.object(
            orchestrator, '_dispatch_to_agent', new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = None
            await orchestrator.coordinate(request)

        mock_dependencies["task_type_loader"].load.assert_called_with("meeting_prep")

    @pytest.mark.asyncio
    async def test_coordinate_logs_events(self, mock_dependencies, sample_task_type):
        """Coordinate logs start and complete events."""
        from pa_routing.models.requests import CoordinateRequest
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        mock_dependencies["task_type_loader"].load.return_value = sample_task_type
        handler = mock_dependencies["coordination_handler"]
        handler.start_coordinated_task = AsyncMock(return_value="task-123")
        handler.get_gathered_findings = AsyncMock(return_value={})
        handler.is_task_complete = AsyncMock(return_value=True)
        handler.get_task_status = AsyncMock(return_value={"calendar": "done"})
        handler.complete_task = AsyncMock(return_value=True)

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={}
        )

        with patch.object(orchestrator, '_dispatch_to_agent', new_callable=AsyncMock):
            await orchestrator.coordinate(request)

        # Should log start event
        log_calls = mock_dependencies["coordination_logger"].log_event.call_args_list
        start_calls = [c for c in log_calls if c[1].get("event_type") == "start"]
        assert len(start_calls) >= 1

        # Should log complete event
        complete_calls = [c for c in log_calls if c[1].get("event_type") == "complete"]
        assert len(complete_calls) >= 1

    @pytest.mark.asyncio
    async def test_coordinate_returns_error_for_missing_task_type(
        self, mock_dependencies
    ):
        """Returns error response when task type not found."""
        from pa_routing.models.requests import CoordinateRequest
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator
        from pa_routing.services.task_type_loader import TaskTypeNotFoundError

        mock_dependencies["task_type_loader"].load.side_effect = TaskTypeNotFoundError(
            "not found"
        )

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="nonexistent",
            context={}
        )

        response = await orchestrator.coordinate(request)

        assert response.status == "error"
        assert "not found" in response.error_message.lower()

    @pytest.mark.asyncio
    async def test_coordinate_returns_error_for_draft_task_type(
        self, mock_dependencies, draft_task_type
    ):
        """Returns error when task type is in draft stage."""
        from pa_routing.models.requests import CoordinateRequest
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        mock_dependencies["task_type_loader"].load.return_value = draft_task_type

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="draft_task",
            context={}
        )

        response = await orchestrator.coordinate(request)

        assert response.status == "error"
        assert "draft" in response.error_message.lower()

    @pytest.mark.asyncio
    async def test_coordinate_dispatches_all_enabled_agents(
        self, mock_dependencies, multi_agent_task_type
    ):
        """Dispatches to all enabled agents in task type."""
        from pa_routing.models.requests import CoordinateRequest
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        mock_dependencies["task_type_loader"].load.return_value = multi_agent_task_type
        handler = mock_dependencies["coordination_handler"]
        handler.start_coordinated_task = AsyncMock(return_value="task-123")
        handler.get_gathered_findings = AsyncMock(return_value={
            "calendar": "Meeting at 2pm",
            "email": "Related thread found"
        })
        handler.is_task_complete = AsyncMock(return_value=True)
        handler.get_task_status = AsyncMock(return_value={
            "calendar": "done",
            "email": "done"
        })
        handler.complete_task = AsyncMock(return_value=True)

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={"meeting_identifier": "Board Meeting", "meeting_title": "Q4"}
        )

        dispatched_agents = []

        async def track_dispatch(agent_name, **kwargs):
            dispatched_agents.append(agent_name)
            return {"status": "success", "response": f"Finding for {agent_name}"}

        with patch.object(orchestrator, '_dispatch_to_agent', side_effect=track_dispatch):
            await orchestrator.coordinate(request)

        assert "calendar" in dispatched_agents
        assert "email" in dispatched_agents

    @pytest.mark.asyncio
    async def test_coordinate_returns_complete_status_when_all_succeed(
        self, mock_dependencies, sample_task_type
    ):
        """Returns complete status when all agents succeed."""
        from pa_routing.models.requests import CoordinateRequest
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        mock_dependencies["task_type_loader"].load.return_value = sample_task_type
        handler = mock_dependencies["coordination_handler"]
        handler.start_coordinated_task = AsyncMock(return_value="task-123")
        handler.get_gathered_findings = AsyncMock(return_value={
            "calendar": "Meeting at 2pm"
        })
        handler.is_task_complete = AsyncMock(return_value=True)
        handler.get_task_status = AsyncMock(return_value={
            "calendar": "done",
            "task_id": "task-123"
        })
        handler.complete_task = AsyncMock(return_value=True)

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={}
        )

        with patch.object(
            orchestrator, '_dispatch_to_agent', new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = {"status": "success", "response": "Agent response"}
            response = await orchestrator.coordinate(request)

        assert response.status == "complete"
        assert "calendar" in response.agents_completed

    @pytest.mark.asyncio
    async def test_coordinate_returns_partial_status_when_some_fail(
        self, mock_dependencies, multi_agent_task_type
    ):
        """Returns partial status when some agents fail."""
        from pa_routing.models.requests import CoordinateRequest
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        mock_dependencies["task_type_loader"].load.return_value = multi_agent_task_type
        handler = mock_dependencies["coordination_handler"]
        handler.start_coordinated_task = AsyncMock(return_value="task-123")
        handler.get_gathered_findings = AsyncMock(return_value={
            "calendar": "Meeting at 2pm"
        })
        handler.is_task_complete = AsyncMock(return_value=True)
        handler.get_task_status = AsyncMock(return_value={
            "calendar": "done",
            "email": "error",
            "task_id": "task-123"
        })
        handler.complete_task = AsyncMock(return_value=True)

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={}
        )

        async def mock_dispatch(agent_name, **kwargs):
            if agent_name == "calendar":
                return {"status": "success", "response": "Meeting at 2pm"}
            else:
                return {"status": "timeout"}

        with patch.object(orchestrator, '_dispatch_to_agent', side_effect=mock_dispatch):
            response = await orchestrator.coordinate(request)

        assert response.status == "partial"
        assert "calendar" in response.agents_completed
        assert "email" in response.agents_failed

    @pytest.mark.asyncio
    async def test_coordinate_synthesizes_findings(
        self, mock_dependencies, sample_task_type
    ):
        """Synthesizes findings into response."""
        from pa_routing.models.requests import CoordinateRequest
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        mock_dependencies["task_type_loader"].load.return_value = sample_task_type
        handler = mock_dependencies["coordination_handler"]
        handler.start_coordinated_task = AsyncMock(return_value="task-123")
        handler.get_gathered_findings = AsyncMock(return_value={
            "calendar": "Board Meeting scheduled for 2pm in Conference Room A"
        })
        handler.is_task_complete = AsyncMock(return_value=True)
        handler.get_task_status = AsyncMock(return_value={
            "calendar": "done",
            "task_id": "task-123"
        })
        handler.complete_task = AsyncMock(return_value=True)

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={"meeting_title": "Q4 Review"}
        )

        with patch.object(orchestrator, '_dispatch_to_agent', new_callable=AsyncMock):
            response = await orchestrator.coordinate(request)

        assert response.synthesis is not None
        # Template should apply meeting_title
        assert "Q4 Review" in response.synthesis

    @pytest.mark.asyncio
    async def test_coordinate_records_timing(
        self, mock_dependencies, sample_task_type
    ):
        """Records coordination timing in response."""
        from pa_routing.models.requests import CoordinateRequest
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        mock_dependencies["task_type_loader"].load.return_value = sample_task_type
        handler = mock_dependencies["coordination_handler"]
        handler.start_coordinated_task = AsyncMock(return_value="task-123")
        handler.get_gathered_findings = AsyncMock(return_value={})
        handler.is_task_complete = AsyncMock(return_value=True)
        handler.get_task_status = AsyncMock(return_value={"calendar": "done"})
        handler.complete_task = AsyncMock(return_value=True)

        orchestrator = CoordinationOrchestrator(**mock_dependencies)

        request = CoordinateRequest(
            identity_id="identity-123",
            task_type="meeting_prep",
            context={}
        )

        with patch.object(orchestrator, '_dispatch_to_agent', new_callable=AsyncMock):
            response = await orchestrator.coordinate(request)

        assert response.coordination_time_ms is not None
        assert response.coordination_time_ms >= 0


class TestAgentPromptBuilding:
    """Tests for agent prompt template substitution."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with minimal mocks."""
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        return CoordinationOrchestrator(
            task_type_loader=MagicMock(),
            coordination_handler=MagicMock(),
            coordination_logger=MagicMock(),
            letta_base_url="http://localhost:8283"
        )

    def test_build_agent_prompt_substitutes_placeholders(self, orchestrator):
        """Build agent prompt substitutes context placeholders."""
        from pa_routing.services.task_type_loader import AgentConfig

        agent_config = AgentConfig(
            name="calendar",
            prompt_template="Find meeting {meeting_identifier} for {participant_name}"
        )
        context = {
            "meeting_identifier": "Board Meeting",
            "participant_name": "Alice"
        }

        prompt = orchestrator._build_agent_prompt(agent_config, context)

        assert "Board Meeting" in prompt
        assert "Alice" in prompt
        assert "{meeting_identifier}" not in prompt
        assert "{participant_name}" not in prompt

    def test_build_agent_prompt_preserves_unmatched_placeholders(self, orchestrator):
        """Unmatched placeholders are preserved in output."""
        from pa_routing.services.task_type_loader import AgentConfig

        agent_config = AgentConfig(
            name="calendar",
            prompt_template="Find {event} for {unknown_field}"
        )
        context = {"event": "Meeting"}

        prompt = orchestrator._build_agent_prompt(agent_config, context)

        assert "Meeting" in prompt
        assert "{unknown_field}" in prompt


class TestSynthesis:
    """Tests for response synthesis."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with minimal mocks."""
        from pa_routing.services.coordination_orchestrator import CoordinationOrchestrator

        return CoordinationOrchestrator(
            task_type_loader=MagicMock(),
            coordination_handler=MagicMock(),
            coordination_logger=MagicMock(),
            letta_base_url="http://localhost:8283"
        )

    @pytest.mark.asyncio
    async def test_template_only_synthesis(self, orchestrator):
        """Template-only synthesis applies template with context and findings."""
        from pa_routing.services.task_type_loader import SynthesisConfig, TaskType

        task_type = TaskType(
            name="test",
            version="1.0.0",
            lifecycle_stage="active",
            goal="Test",
            agents={},
            synthesis=SynthesisConfig(
                mode="template_only",
                template="Meeting: {meeting_title}\n\nFindings:\n{findings}"
            )
        )
        findings = {"calendar": "Event at 2pm", "email": "Thread found"}
        context = {"meeting_title": "Q4 Review"}

        result = await orchestrator._synthesize(task_type, findings, context)

        assert "Q4 Review" in result
        assert "Event at 2pm" in result

    @pytest.mark.asyncio
    async def test_main_agent_only_synthesis(self, orchestrator):
        """Main-agent-only synthesis joins findings."""
        from pa_routing.services.task_type_loader import SynthesisConfig, TaskType

        task_type = TaskType(
            name="test",
            version="1.0.0",
            lifecycle_stage="active",
            goal="Test",
            agents={},
            synthesis=SynthesisConfig(mode="main_agent_only")
        )
        findings = {"calendar": "Event at 2pm", "email": "Thread found"}
        context = {}

        result = await orchestrator._synthesize(task_type, findings, context)

        assert "Event at 2pm" in result
        assert "Thread found" in result

    @pytest.mark.asyncio
    async def test_synthesis_with_agent_specific_placeholders(self, orchestrator):
        """Synthesis substitutes agent-specific placeholders."""
        from pa_routing.services.task_type_loader import SynthesisConfig, TaskType

        task_type = TaskType(
            name="test",
            version="1.0.0",
            lifecycle_stage="active",
            goal="Test",
            agents={},
            synthesis=SynthesisConfig(
                mode="template_only",
                template="Calendar: {calendar_findings}\nEmail: {email_findings}"
            )
        )
        findings = {"calendar": "Meeting at 2pm", "email": "5 related threads"}
        context = {}

        result = await orchestrator._synthesize(task_type, findings, context)

        assert "Meeting at 2pm" in result
        assert "5 related threads" in result
