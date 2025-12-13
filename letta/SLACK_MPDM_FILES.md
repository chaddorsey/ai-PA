# Retrieving Files from MPDM (Multi-Person Direct Message) Channels

## Overview

Yes, it is possible to retrieve files posted to MPDM channels in Slack. However, the approach differs from listing workspace-wide files.

## Two Approaches

### Approach 1: Workspace-Wide File List (Existing)

The `files.list` API method lists all files the bot has access to across the workspace, but **cannot filter by specific channel**. This is what the existing `list_recent_slack_files` tool uses.

**Limitations:**
- Cannot filter by channel ID
- Shows all files the bot can access (workspace-wide)
- Files from MPDMs will be included if the bot has access, but you can't filter specifically for an MPDM

### Approach 2: Channel-Specific File Retrieval (Recommended for MPDMs)

To get files from a specific MPDM channel, you need to:

1. **Get messages from the channel** using `conversations.history`
2. **Extract files from message objects** (each message can have a `files` array)
3. **Use file metadata** to access/download files

## Required Permissions/Scopes

Your Slack bot/app needs these OAuth scopes:

1. **`mpim:history`** - To read message history from MPDM channels
2. **`files:read`** - To read file information and access file metadata
3. **`mpim:read`** - To read MPDM channel information (optional, but recommended)

## Process

### Step 1: Identify MPDM Channel ID

You need the MPDM channel ID. It typically starts with `G` (Group DM) or can be in format like `mpdm-user1--user2--user3-1`.

If you don't have it:
- Use `conversations.open` with participant user IDs to get/create the MPDM channel ID
- Or extract it from message data you already have

### Step 2: Retrieve Messages with Files

Call `conversations.history` for the MPDM channel:

```python
response = client.conversations_history(
    channel="mpdm-user1--user2--user3-1",
    limit=200  # Adjust as needed
)
messages = response["messages"]
```

### Step 3: Extract Files from Messages

Each message object may contain a `files` array:

```python
files_from_channel = []
for message in messages:
    if "files" in message:
        for file in message["files"]:
            files_from_channel.append({
                "file_id": file.get("id"),
                "name": file.get("name"),
                "title": file.get("title"),
                "mimetype": file.get("mimetype"),
                "filetype": file.get("filetype"),
                "size": file.get("size"),
                "url_private_download": file.get("url_private_download"),
                "created": file.get("created"),
                "user": file.get("user"),
                "message_ts": message.get("ts"),  # Link to original message
            })
```

### Step 4: Access/Download Files

Each file object includes:
- **`id`**: File ID (e.g., `F1234567890`)
- **`url_private_download`**: Private download URL (requires auth token)
- **`name`**, **`title`**: File name/title
- **`size`**: File size in bytes
- **`mimetype`**, **`filetype`**: File type information

To download, use the `url_private_download` with your auth token:

```python
response = requests.get(
    file["url_private_download"],
    headers={"Authorization": f"Bearer {SLACK_TOKEN}"}
)
# Save file content
```

## File Object Structure

Files in messages have this structure:

```json
{
  "id": "F1234567890",
  "created": 1234567890,
  "timestamp": 1234567890,
  "name": "document.pdf",
  "title": "Document Title",
  "mimetype": "application/pdf",
  "filetype": "pdf",
  "pretty_type": "PDF",
  "user": "U1234567890",
  "size": 12345,
  "url_private": "https://files.slack.com/files-pri/...",
  "url_private_download": "https://files.slack.com/files-pri/...",
  "is_external": false,
  "is_public": false,
  "public_url_shared": false,
  "channels": ["mpdm-user1--user2--user3-1"],
  "groups": [],
  "ims": [],
  "initial_comment": {},
  "num_stars": 0,
  "is_starred": false
}
```

## Important Considerations

### Permissions
- The bot must be a member of the MPDM to access its messages
- The bot needs `mpim:history` scope to read message history
- The bot needs `files:read` scope to access file metadata

### Rate Limits
- `conversations.history`: Tier 2 (50+ per minute per workspace)
- `files.info`: Tier 3 (20+ per minute per workspace)
- Be mindful when processing many messages

### Data Privacy
- Files in MPDMs are private to participants
- Ensure your bot has appropriate permissions
- Handle file data according to your privacy policy

### Channel Access
- The bot must have been added to the MPDM
- If the bot wasn't added, you'll get `channel_not_found` or `not_in_channel` errors

## Alternative: Using `files.info` with File ID

If you already have a file ID from elsewhere (e.g., from `files.list`), you can get file details:

```python
response = client.files_info(file="F1234567890")
file_info = response["file"]
```

This will include channel information showing which channels the file is shared in:

```json
{
  "file": {
    "channels": ["C1234567890"],
    "groups": [],
    "ims": ["D1234567890"],
    "mpims": ["G1234567890"]  // MPDM channels
  }
}
```

However, this requires you to already know the file ID, so it's less useful for discovering files in a specific MPDM.

## Recommended Approach for MPDM Files

For discovering and retrieving files from a specific MPDM:

1. **Use `conversations.history`** to get messages from the MPDM
2. **Extract files from message objects** 
3. **Filter/process files as needed**
4. **Download using `url_private_download`** with auth token

This is the most reliable way to get files from a specific MPDM channel.

