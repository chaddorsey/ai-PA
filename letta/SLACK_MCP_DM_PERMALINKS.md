# Handling DM Permalinks from MCP Server Data

## Problem

When the Slack MCP server returns message data, it sometimes provides channel information in the format `#U09C3N5LZ` (a user ID with `#` prefix) instead of the actual DM channel ID like `D09C3JMB9`. This makes it impossible to construct permalinks directly.

## Solution

The `get_slack_message_permalink` tool now **automatically handles this case**. When it receives a channel ID that looks like a user ID (starts with `#U` or `U`), it:

1. Extracts the user ID (removes `#` prefix if present)
2. Calls Slack's `conversations.open` API to resolve the user ID to the actual DM channel ID
3. Uses the resolved channel ID to generate the permalink

## Usage

### Direct Usage (Automatic Resolution)

Simply call the tool with the channel value from the MCP server:

```python
# MCP server returns: Channel="#U09C3N5LZ", MsgID="1765568505.525349"
get_slack_message_permalink(
    channel_id="#U09C3N5LZ",  # or "U09C3N5LZ" (both work)
    message_ts="1765568505.525349"
)
```

The tool will:
1. Detect that `#U09C3N5LZ` is a user ID
2. Call `conversations.open(users=["U09C3N5LZ"])` to get channel ID `D09C3JMB9`
3. Generate permalink: `https://concord-consortium.slack.com/archives/D09C3JMB9/p1765568505525349`

### Manual Resolution (Optional)

If you need the channel ID separately, you can use the `resolve_dm_channel_id` tool:

```python
# Step 1: Resolve user ID to channel ID
resolve_dm_channel_id(user_id="U09C3N5LZ")
# Returns: {"channel_id": "D09C3JMB9", "user_id": "U09C3N5LZ"}

# Step 2: Use the resolved channel ID
get_slack_message_permalink(
    channel_id="D09C3JMB9",
    message_ts="1765568505.525349"
)
```

## Example: Processing MCP Server CSV Data

When processing CSV data from the MCP server:

```python
# CSV row from MCP server:
# Channel="#U09C3N5LZ", MsgID="1765568505.525349"

channel = "#U09C3N5LZ"  # From CSV "Channel" column
msg_id = "1765568505.525349"  # From CSV "MsgID" column

# The tool automatically handles the user ID resolution
permalink_result = get_slack_message_permalink(
    channel_id=channel,
    message_ts=msg_id
)

# Result:
# {
#   "success": true,
#   "permalink": "https://concord-consortium.slack.com/archives/D09C3JMB9/p1765568505525349",
#   "channel_id": "D09C3JMB9",  # Resolved from U09C3N5LZ
#   "message_ts": "1765568505.525349",
#   "message": "Permalink generated successfully via API"
# }
```

## Channel ID Formats

The tool accepts and handles:

1. **Regular channels**: `"C1234567890"` → Works directly
2. **DM channels (direct)**: `"D09C3JMB9"` → Works directly
3. **MPDM channels**: `"mpdm-cmcintyre--lstephens--cdorsey-1"` → Works directly
4. **User IDs (from MCP)**: `"#U09C3N5LZ"` or `"U09C3N5LZ"` → **Automatically resolved to DM channel ID**

## How It Works

1. **Detection**: The tool checks if `channel_id` starts with `#U` or `U` (but not `D`)
2. **Resolution**: Calls `conversations.open(users=[user_id])` to get the DM channel ID
3. **Fallback**: If resolution fails, returns an error message explaining the issue
4. **Permalink Generation**: Uses the resolved channel ID to generate the permalink

## Error Handling

If user ID resolution fails, the tool returns:

```json
{
  "error": "Failed to resolve user ID to DM channel: [error details]",
  "user_id": "U09C3N5LZ",
  "message_ts": "1765568505.525349",
  "message": "Could not convert user ID to DM channel ID. Make sure the user ID is correct and the bot has access to DM with this user."
}
```

Common causes:
- Invalid user ID format
- Bot doesn't have permission to DM with the user
- User ID doesn't exist
- Network/API errors

## Notes

- The `#` prefix is optional - both `"#U09C3N5LZ"` and `"U09C3N5LZ"` work
- Resolution happens automatically - no need to call `resolve_dm_channel_id` separately unless you need the channel ID for other purposes
- The resolved channel ID is cached by Slack's API, so subsequent calls are fast
- This only works for DMs (1-on-1 conversations), not group DMs (MPDMs)

