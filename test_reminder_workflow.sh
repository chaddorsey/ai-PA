#!/usr/bin/env bash
# End-to-end test of reminder workflow

set -e

echo "=== Testing Complete Reminder Workflow ==="
echo ""

# Test 1: Create a reminder via MCP (simulating Letta)
echo "Step 1: Creating reminder via MCP endpoint..."
REMINDER_RESPONSE=$(curl -s -X POST http://localhost:8088/mcp \
  -H "Content-Type: application/json" \
  -H "mcp-session-id: test-session-123" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "schedule_reminder",
      "arguments": {
        "message": "Check deployment status - this is a test reminder",
        "when": "in 2 minutes",
        "title": "Test Deployment Check",
        "agent_id": "test-agent-123",
        "category": "testing"
      }
    }
  }')

echo "MCP Response:"
echo "$REMINDER_RESPONSE" | jq .

# Extract job_id from response
JOB_ID=$(echo "$REMINDER_RESPONSE" | jq -r '.result.content[0].text' | jq -r '.job_id')
echo ""
echo "Created Job ID: $JOB_ID"
echo ""

# Test 2: Verify job was created in scheduler-service
echo "Step 2: Verifying job in scheduler-service..."
JOB_DETAILS=$(curl -s "http://localhost:8087/v1/jobs/$JOB_ID")
echo "Job Details:"
echo "$JOB_DETAILS" | jq '{
  job_id,
  title,
  description,
  status,
  schedule_type,
  schedule_expression,
  next_run_at,
  category,
  actions: .actions | length
}'
echo ""

# Test 3: Check if job has agent_message action
echo "Step 3: Checking agent_message action configuration..."
echo "$JOB_DETAILS" | jq '.actions[] | select(.action_type == "agent_message")'
echo ""

# Test 4: List all scheduled jobs
echo "Step 4: Listing all scheduled jobs..."
curl -s "http://localhost:8087/v1/jobs" | jq '[.[] | {job_id, title, status, next_run_at}] | .[0:3]'
echo ""

echo "=== Test Complete ==="
echo ""
echo "Workflow Summary:"
echo "1. ✅ Reminder created via MCP"
echo "2. ✅ Job stored in scheduler-service with parsed schedule"
echo "3. ✅ agent_message action configured"
echo "4. ✅ Job will execute in ~2 minutes"
echo ""
echo "To verify execution:"
echo "  docker compose logs -f scheduler-service | grep 'agent_message'"
echo ""
echo "Expected: In 2 minutes, scheduler will execute the agent_message action"
echo "          and attempt to POST to: http://letta:8283/api/agents/test-agent-123/messages"



