# Slack Permalink Tool Usage Guide

## Tool: `get_slack_message_permalink`

### Purpose
Generate permanent links to specific Slack messages that can be shared or referenced.

### Parameters

1. **`channel_id`** (required, string)
   - The Slack channel ID where the message exists
   - Examples:
     - Regular channel: `"C1234567890"`
     - Direct message (DM): `"D1234567890"`
     - Multi-person DM (MPDM): `"mpdm-cmcintyre--lstephens--cdorsey-1"`

2. **`message_ts`** (required, string)
   - The message timestamp in Slack format
   - Format: `"1234567890.123456"` (Unix timestamp with microseconds)
   - Can also accept: `"1234567890123456"` (will be normalized automatically)

### How to Get These Values

#### From Slack Events (When Agent Receives Messages)

When your agent receives a Slack message event, it contains:

```python
event = {
    "channel": "C1234567890",      # ← Use this for channel_id
    "ts": "1765475225.944079",      # ← Use this for message_ts
    "user": "U1234567890",
    "text": "Hello!",
    ...
}
```

**Usage:**
```python
get_slack_message_permalink(
    channel_id=event.get("channel"),
    message_ts=event.get("ts")
)
```

#### From Slack API Responses (When Agent Posts Messages)

When you post a message using `chat.postMessage`, the response includes:

```python
response = {
    "ok": True,
    "channel": "C1234567890",       # ← Use this for channel_id
    "ts": "1765475225.944079",      # ← Use this for message_ts
    "message": {...}
}
```

**Usage:**
```python
get_slack_message_permalink(
    channel_id=response.get("channel"),
    message_ts=response.get("ts")
)
```

#### From Conversation History (When Retrieving Messages)

When you retrieve messages using `conversations.history` or `conversations.replies`:

```python
messages = [
    {
        "ts": "1765475225.944079",  # ← Use this for message_ts
        "user": "U1234567890",
        "text": "Previous message",
        ...
    },
    ...
]
```

**Usage:**
```python
# channel_id comes from the API call parameter
# message_ts comes from each message object
get_slack_message_permalink(
    channel_id=channel_id,  # From conversations.history(channel=channel_id)
    message_ts=message.get("ts")
)
```

### Return Value

The tool returns a JSON string with:

```json
{
  "success": true,
  "permalink": "https://concord-consortium.slack.com/archives/C1234567890/p1765475225944079",
  "channel_id": "C1234567890",
  "message_ts": "1765475225.944079",
  "message": "Permalink generated successfully via API"
}
```

For DM/MPDM channels, you may see:
```json
{
  "success": true,
  "permalink": "https://concord-consortium.slack.com/archives/mpdm-cmcintyre--lstephens--cdorsey-1/p1765475225944079",
  "channel_id": "mpdm-cmcintyre--lstephens--cdorsey-1",
  "message_ts": "1765475225.944079",
  "message": "Permalink constructed manually for DM/MPDM channel",
  "note": "DM/MPDM channels don't support chat.getPermalink API, so permalink was constructed using standard format"
}
```

### Common Use Cases

1. **Generate permalink for a message the user just sent:**
   ```python
   # In event handler
   channel_id = event.get("channel")
   message_ts = event.get("ts")
   permalink_result = get_slack_message_permalink(channel_id, message_ts)
   ```

2. **Generate permalink for a message the agent just posted:**
   ```python
   # After posting message
   response = client.chat_postMessage(channel=channel_id, text="Hello!")
   if response.get("ok"):
       permalink_result = get_slack_message_permalink(
           channel_id=response.get("channel"),
           message_ts=response.get("ts")
       )
   ```

3. **Generate permalink for a message from conversation history:**
   ```python
   # When referencing a previous message
   history = client.conversations_history(channel=channel_id, limit=10)
   for message in history.get("messages", []):
       if message.get("text") == "target message":
           permalink_result = get_slack_message_permalink(
               channel_id=channel_id,
               message_ts=message.get("ts")
           )
           break
   ```

### Error Handling

If the tool returns an error, check:
- `channel_id` is valid and accessible
- `message_ts` is in correct format
- The message exists in that channel
- The bot has access to the channel

### Notes

- **DM/MPDM Support**: The tool automatically handles DM and MPDM channels by constructing permalinks manually when the API doesn't support them.
- **Timestamp Format**: The tool accepts timestamps with or without decimal points and normalizes them automatically.
- **Workspace**: Permalinks are generated for the `concord-consortium.slack.com` workspace.

