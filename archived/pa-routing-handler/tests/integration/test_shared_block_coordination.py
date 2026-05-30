"""Integration tests for shared block coordination.

These tests require a running Letta instance and are marked with @pytest.mark.live.
Run with: pytest -m live tests/integration/test_shared_block_coordination.py
"""

import asyncio

import pytest


@pytest.mark.live
class TestSharedBlockCoordination:
    """Integration tests for shared block coordination with real Letta."""

    @pytest.fixture
    def handler(self):
        """Create handler connected to real Letta."""
        from pa_routing.services.coordination_handler import CoordinationBlockHandler

        return CoordinationBlockHandler("http://localhost:8283")

    @pytest.mark.asyncio
    async def test_create_and_attach_blocks_to_agent(self, handler):
        """Can create blocks and attach them to a real agent."""
        # Use calendar agent for testing
        agent_id = "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d"
        identity_id = "test-integration"

        # Create task block
        task_block_id = await handler.get_or_create_block(
            label=f"test_task_{identity_id}",
            initial_value="Integration test task",
            description="Test task block for integration testing",
        )
        assert task_block_id is not None, "Failed to create task block"

        # Attach to agent
        attached = await handler.attach_block_to_agent(task_block_id, agent_id)
        assert attached, "Failed to attach block to agent"

        # Cleanup: detach block
        detached = await handler.detach_block_from_agent(task_block_id, agent_id)
        assert detached, "Failed to detach block from agent"

    @pytest.mark.asyncio
    async def test_start_coordinated_task_with_real_agents(self, handler):
        """Can start a coordinated task and attach blocks to agents."""
        identity_id = "test-coord-integration"
        agent_ids = {
            "calendar": "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
        }

        # Start coordinated task
        task_id = await handler.start_coordinated_task(
            identity_id=identity_id,
            task_type="test_meeting_prep",
            title="Integration Test Meeting",
            required_agents=["calendar"],
            agent_ids=agent_ids,
        )
        assert task_id is not None, "Failed to start coordinated task"

        # Verify blocks were created
        task_block = await handler.get_block_by_label(f"coordination_task_{identity_id}")
        assert task_block is not None, "Task block not created"
        assert "Integration Test Meeting" in task_block.get("value", "")

        gathered_block = await handler.get_block_by_label(
            f"coordination_gathered_{identity_id}"
        )
        assert gathered_block is not None, "Gathered block not created"

        # Complete task (this will detach and reset blocks)
        await handler.complete_task(
            identity_id=identity_id,
            main_agent_id="agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",
            agent_ids=agent_ids,
        )

    @pytest.mark.asyncio
    async def test_gathered_findings_parsing(self, handler):
        """Can parse gathered findings from block with agent entries."""
        identity_id = "test-parsing"

        # Create gathered block with test content
        gathered_block_id = await handler.get_or_create_block(
            label=f"coordination_gathered_{identity_id}",
            initial_value="",
            description="Test gathered block",
        )
        assert gathered_block_id is not None

        # Write test entries
        test_content = """[Calendar 10:30] Board Meeting, 2pm Jan 30, Conference Room A
[Email 10:31] 3 threads found: budget discussion, venue confirmation, agenda draft
[Pulse 10:32] Bob OOO tomorrow, Alice working remote Wednesday"""

        updated = await handler.update_block(gathered_block_id, test_content)
        assert updated, "Failed to update gathered block"

        # Parse findings
        findings = await handler.get_gathered_findings(identity_id)

        assert "calendar" in findings, "Calendar findings not parsed"
        assert "email" in findings, "Email findings not parsed"
        assert "pulse" in findings, "Pulse findings not parsed"

        assert "Board Meeting" in findings["calendar"]
        assert "3 threads" in findings["email"]
        assert "Bob OOO" in findings["pulse"]

        # Cleanup
        await handler.update_block(gathered_block_id, "")


@pytest.mark.live
class TestCoordinationProtocol:
    """Test that agents have coordination protocol in their persona."""

    @pytest.mark.asyncio
    async def test_calendar_agent_has_coordination_protocol(self):
        """Calendar agent should have coordination protocol in persona."""
        import httpx

        agent_id = "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"http://localhost:8283/v1/agents/{agent_id}/core-memory/blocks"
            )
            assert response.status_code == 200

            blocks = response.json()
            persona_block = next(
                (b for b in blocks if b.get("label") == "persona"), None
            )

            assert persona_block is not None, "Persona block not found"

            persona_value = persona_block.get("value", "")
            assert (
                "<coordination_protocol>" in persona_value
            ), "Coordination protocol not found in persona"
            assert (
                "memory_insert" in persona_value
            ), "memory_insert instruction not found in persona"
