# Letta Tool Registration Guide

## Prerequisites

1. **Letta Server Running**: The Letta server must be accessible
2. **Environment Variables**: Set `LETTA_BASE_URL` and optionally `LETTA_AGENT_ID`

## Registration Steps

### Step 1: Verify Letta Connection

Check if Letta server is accessible:

```bash
# Default URL is http://localhost:8283 or http://letta:8283
curl http://localhost:8283/health  # or your Letta URL
```

If using Docker, the service name might be `letta:8283`.

### Step 2: Set Environment Variables

```bash
# In your shell or .env file
export LETTA_BASE_URL="http://localhost:8283"  # or your Letta URL
export LETTA_AGENT_ID="your-agent-id"  # Optional for registration, required for attachment
```

### Step 3: Register the Tool

```bash
cd /Users/dorseyhomeserver/ai-PA
python3 letta/register_scheduling_tool.py
```

This will:
- Connect to Letta server
- Register the `orchestrate_scheduling` tool with updated dual-format schema
- Return the tool ID

**Expected Output:**
```
============================================================
Scheduling Orchestration Tool Registration
============================================================

Letta Base URL: http://localhost:8283

✓ Connected to Letta server

Registering tool: orchestrate_scheduling

  ✓ Registered: orchestrate_scheduling
    Tool ID: tool_abc123...
    Description: Scheduling orchestration tool using ASP optimization

============================================================
Registration Complete
============================================================
```

### Step 4: Attach Tool to Agent

```bash
python3 letta/attach_scheduling_tool_to_agent.py
```

This requires `LETTA_AGENT_ID` to be set.

**Expected Output:**
```
============================================================
Attach Scheduling Tool to Agent
============================================================

Letta Base URL: http://localhost:8283
Agent ID: your-agent-id

✓ Connected to Letta server

Looking for tool: orchestrate_scheduling...
  ✓ Found tool (ID: tool_abc123...)

Attaching tool to agent your-agent-id...
  ✓ Tool attached successfully

============================================================
✓ Attachment Complete
============================================================
```

## Troubleshooting

### Connection Error: "nodename nor servname provided"

**Cause**: Letta server not accessible at the configured URL.

**Solutions**:
1. Check if Letta server is running:
   ```bash
   docker ps | grep letta
   # or
   ps aux | grep letta
   ```

2. Verify the URL is correct:
   ```bash
   echo $LETTA_BASE_URL
   # Should be something like: http://localhost:8283 or http://letta:8283
   ```

3. If using Docker Compose, use the service name:
   ```bash
   export LETTA_BASE_URL="http://letta:8283"
   ```

4. If running locally:
   ```bash
   export LETTA_BASE_URL="http://localhost:8283"
   ```

### Tool Already Exists

If you see "Tool already exists", you can either:
1. Delete the existing tool via Letta ADE (Agent Development Environment)
2. The script will note it exists - you can still attach it to your agent

### Schema Update

The tool schema is automatically generated from the function signature and Pydantic models. The dual-format structure (user_display, agent_data, mapping) will be included automatically.

## Verifying Registration

After registration, you can verify the tool is available:

```python
from letta_client import Letta

client = Letta(base_url="http://localhost:8283")
tools = client.tools.list()

# Find the scheduling tool
for tool in tools:
    if tool.name == "orchestrate_scheduling":
        print(f"Found tool: {tool.name} (ID: {tool.id})")
        print(f"Description: {tool.description}")
        break
```

## Testing the Tool

Once attached to your agent, test with a simple query:

```
"Find 45 minutes for a meeting with Sue and Danielle next week"
```

The agent should call the orchestrator tool and return formatted results.

