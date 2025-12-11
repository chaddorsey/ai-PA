# Agent-to-Agent Messaging Tool Setup Guide

This guide explains how to set up and use the custom agent-to-agent messaging tool for Letta v1 architecture.

## Overview

The built-in `send_message_to_agent_async` tool has known issues on both Cloud and self-hosted deployments. This implementation provides a working alternative based on the community workaround from the Letta forum:

**Reference**: https://forum.letta.com/t/custom-agent-to-agent-messaging-tool-for-v1-architecture/127

## Architecture

The tool implements agent-to-agent communication by:
1. Sending a POST request to the Letta API `/v1/agents/{recipient_id}/messages`
2. Including a system message with instructions for the recipient agent
3. Extracting assistant messages from the response (replies from the recipient)

## Prerequisites

1. **LETTA_API_KEY** must be set in the environment
2. **LETTA_BASE_URL** (defaults to `http://localhost:8283` for self-hosted)
3. Both agents must have an `agent_info` memory block containing their agent_id

## Setup Steps

### Step 1: Register the Tool

Register the tool with your Letta instance:

```bash
cd letta
python3 register_a2a_tool.py
```

This will:
- Create the `send_message_to_agent` tool in Letta
- Make it available for attachment to agents

### Step 2: Setup agent_info Memory Blocks

Ensure both agents have the required `agent_info` memory block:

```bash
python3 setup_agent_info_blocks.py
```

This script will:
- Check if each agent has an `agent_info` memory block
- Create the block if it doesn't exist
- Set the value to `agent_id: <agent-id>`
- Attach the block to each agent

**Agents configured:**
- Main Orchestration Agent: `agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a`
- Scheduling Agent: `agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218`

### Step 3: Attach Tool to Agents

Attach the tool to both agents:

```bash
python3 attach_a2a_tool_to_agents.py
```

This will:
- Find the `send_message_to_agent` tool
- Attach it to both the main orchestration agent and scheduling agent

### Step 4: Validate the Setup

Test the agent-to-agent communication:

```bash
python3 test_a2a_tool.py
```

This will:
- Send a test message from the main orchestration agent to the scheduling agent
- Display any replies received

## Tool Usage

Once set up, agents can use the tool in conversations:

**Tool Name**: `send_message_to_agent`

**Parameters**:
- `sender_agent_id` (string): The ID of the sending agent
- `recipient_agent_id` (string): The ID of the recipient agent
- `message` (string): The message content to send

**Returns**: JSON string with:
- `status`: "ok" or "error"
- `replies`: List of reply strings from the recipient agent
- `error`: Error message (if status is "error")

## How It Works

1. **Sender agent** calls `send_message_to_agent` with recipient ID and message
2. **Tool** makes POST request to `/v1/agents/{recipient_id}/messages`
3. **System message** includes sender ID and instructions for recipient
4. **Recipient agent** generates assistant message (no tool call needed)
5. **Tool** extracts assistant messages from response
6. **Replies** returned to sender agent

## Important Notes

### For Recipient Agents

The recipient agent needs to be configured to respond to incoming messages. The system message includes instructions, but you may want to add explicit instructions to your agent's system prompt:

```
You have been migrated to v1 architecture. The send_message tool is deprecated.
To communicate with other agents, use send_message_to_agent.
To respond to incoming agent messages, use assistant messages directly.
```

### Agent Info Memory Block

The `agent_info` memory block should be:
- **Label**: `agent_info`
- **Value**: `agent_id: <agent-id>`
- **Description**: "Read-only block containing this agent's ID for agent-to-agent communication"
- **Read-only**: Recommended (to prevent accidental modification)

### Environment Variables

The tool requires `LETTA_API_KEY` to be set in the environment where tools execute. For self-hosted Letta, this may need to be set in the Docker container or environment where the Letta service runs.

## Troubleshooting

### Tool Not Found
- Ensure you've run `register_a2a_tool.py` first
- Check that the tool appears in Letta ADE (Agent Development Environment)

### Agent Info Block Missing
- Run `setup_agent_info_blocks.py` to create/verify the blocks
- Check that blocks are attached to agents in Letta ADE

### No Replies Received
- Verify the recipient agent is configured to respond to messages
- Check that the recipient agent has appropriate instructions
- Ensure `LETTA_API_KEY` is set correctly
- Check Letta logs for errors

### API Key Issues
- Verify `LETTA_API_KEY` is set in the environment
- For self-hosted, ensure the key is available in the Docker container
- Check that the API key has appropriate permissions

## Files Created

- `a2a_tool.py` - Tool implementation
- `register_a2a_tool.py` - Tool registration script
- `attach_a2a_tool_to_agents.py` - Tool attachment script
- `setup_agent_info_blocks.py` - Memory block setup script
- `test_a2a_tool.py` - Validation/test script
- `A2A_TOOL_SETUP.md` - This documentation

## Next Steps

After setup:
1. Test basic communication between agents
2. Integrate agent-to-agent messaging into workflows
3. Monitor for any issues or errors
4. Consider adding more sophisticated error handling if needed

## References

- [Letta Forum: Custom Agent-to-Agent Messaging Tool](https://forum.letta.com/t/custom-agent-to-agent-messaging-tool-for-v1-architecture/127)
- [Letta Documentation](https://docs.letta.com)


