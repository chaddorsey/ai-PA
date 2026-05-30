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
