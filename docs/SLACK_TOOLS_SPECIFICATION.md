# Slack Custom Tools: Tool Specifications

## Overview

This document specifies the tools we'll build for Slack monitoring and information extraction. All tools return well-structured raw data that enables the LLM to perform analysis, summarization, and intelligent operations.

## Letta Tool Compliance

**CRITICAL**: All tools follow Letta tool registration requirements (see `docs/SLACK_TOOLS_LETTA_COMPLIANCE.md`):

- **Return Type**: All tools return `Dict[str, Any]`, NOT JSON strings
- **Standard Format**: `{"status": "ok"|"error", "data": {...}, "error_message": "..."}`
- **Structure**: Imports inside function, try-except wrapper, no nested `def` statements
- **See**: `context/coding_custom_letta_tools.md` for full requirements

All return examples below show the `data` portion - the actual return includes `status` and wraps data in `data` key.

## Tool Categories

1. **Channel Discovery** - Find and get information about channels
2. **Message Retrieval** - Get messages from channels with various filters
3. **Search** - Search for messages across workspace
4. **File & Link Extraction** - Extract files and links from messages
5. **User Information** - Get user details and lists
6. **Thread Discovery** - Find and get thread parent messages
7. **Utilities** - Helper functions (permalinks, ID resolution)

---

## 1. Channel Discovery Tools

### 1.1 `list_slack_channels`

**Purpose**: List all channels in the workspace (public, private, DMs, MPDMs)

**Parameters**:
- `types` (optional, string): Channel types to include. Comma-separated: "public_channel,private_channel,mpim,im". Default: all types
- `exclude_archived` (optional, boolean): Exclude archived channels. Default: true
- `limit` (optional, int): Maximum number to return. Default: 500

**Returns**: Dict[str, Any] with structure:
```python
{
  "status": "ok",
  "data": {
    "channels": [
    {
      "id": "C1234567890",
      "name": "random",
      "is_channel": true,
      "is_private": false,
      "is_archived": false,
      "is_member": true,
      "topic": {"value": "Non-work banter", "creator": "U123", "last_set": 1234567890},
      "purpose": {"value": "A place for non-work-related conversation", "creator": "U123", "last_set": 1234567890},
      "members": ["U123", "U456"],
      "num_members": 150,
      "created": 1234567890
    }
    ],
    "total_count": 150
  }
}
```

**Error Response**:
```python
{
  "status": "error",
  "error_message": "Error description here"
}
```

**Use Cases**: 
- Channel discovery for searching
- Understanding workspace structure
- Finding channels by name/purpose

---

### 1.2 `get_slack_channel_info`

**Purpose**: Get detailed information about a specific channel

**Parameters**:
- `channel` (required, string): Channel ID or channel name (e.g., "C1234567890" or "#random")
- `include_members` (optional, boolean): Include full member list. Default: false (just count)

**Returns**: JSON with channel details
```json
{
  "id": "C1234567890",
  "name": "random",
  "is_channel": true,
  "is_private": false,
  "is_archived": false,
  "is_member": true,
  "topic": {"value": "Non-work banter", "creator": "U123", "last_set": 1234567890},
  "purpose": {"value": "A place for non-work-related conversation", "creator": "U123", "last_set": 1234567890},
  "members": ["U123", "U456", ...],  // if include_members=true
  "num_members": 150,
  "created": 1234567890,
  "creator": "U123"
}
```

**Use Cases**:
- Get channel metadata before querying messages
- Understand channel purpose/context
- Get member list

---

### 1.3 `resolve_slack_channel_name`

**Purpose**: Convert channel name to channel ID (helper utility)

**Parameters**:
- `channel_name` (required, string): Channel name without # (e.g., "random")

**Returns**: JSON with channel ID
```json
{
  "channel_name": "random",
  "channel_id": "C1234567890",
  "is_private": false,
  "is_member": true
}
```

**Use Cases**:
- Convert user-provided channel names to IDs for API calls
- Validate channel existence

---

## 2. Message Retrieval Tools

### 2.1 `get_slack_messages`

**Purpose**: Get messages from a specific channel with optional filters

**Parameters**:
- `channel` (required, string): Channel ID or name (e.g., "C1234567890" or "#random")
- `start_date` (optional, string): Start date in YYYY-MM-DD format or ISO 8601 datetime
- `end_date` (optional, string): End date in YYYY-MM-DD format or ISO 8601 datetime
- `limit` (optional, int): Maximum messages to return. Default: 100, max: 1000
- `include_thread_replies` (optional, boolean): Fetch all thread replies. Default: true
- `oldest` (optional, string): Unix timestamp for oldest message (alternative to start_date)
- `latest` (optional, string): Unix timestamp for latest message (alternative to end_date)
- `sort_by` (optional, string): Sort order: "timestamp" (default), "reactions", "reply_count", "user"
- `sort_order` (optional, string): "asc" or "desc" (default: "desc" for timestamp, "desc" for reactions/reply_count)
- `min_reactions` (optional, int): Filter messages with at least N reactions
- `min_reply_count` (optional, int): Filter messages with at least N replies (thread parents only)
- `only_thread_parents` (optional, boolean): Return only messages that have replies. Default: false
- `has_reactions` (optional, boolean): Return only messages with reactions. Default: false

**Returns**: JSON with messages and complete context
```json
{
  "channel_id": "C1234567890",
  "channel_name": "random",
  "messages": [
    {
      "ts": "1703001234.567890",
      "text": "Full message text here...",
      "user": "U1234567890",
      "username": "sue",
      "real_name": "Sue Smith",
      "datetime": "2024-12-19T14:30:34Z",
      "permalink": "https://workspace.slack.com/archives/C1234567890/p1703001234567890",
      "thread_ts": null,
      "is_thread_parent": false,
      "reply_count": 0,
      "reply_users_count": 0,
      "reactions": [
        {"name": "thumbsup", "count": 3, "users": ["U111", "U222", "U333"]}
      ],
      "files": [
        {
          "id": "F123456",
          "name": "document.pdf",
          "title": "Important Document",
          "mimetype": "application/pdf",
          "filetype": "pdf",
          "size": 1048576,
          "url_private_download": "https://files.slack.com/files-pri/...",
          "created": 1703001000
        }
      ],
      "links": [
        {"url": "https://example.com/doc", "display_text": "shared document", "type": "link"}
      ],
      "thread_replies": []  // Empty if not a thread parent
    }
  ],
  "has_more": false,
  "total_returned": 1,
  "date_range": {
    "start": "2024-12-19T00:00:00Z",
    "end": "2024-12-19T23:59:59Z"
  }
}
```

**Use Cases**:
- Get all messages from #random on Dec 19
- Get recent activity in a channel
- Get messages with complete context (threads, files, links)

---

### 2.2 `get_slack_message`

**Purpose**: Get a specific message by timestamp and channel

**Parameters**:
- `channel` (required, string): Channel ID or name
- `message_ts` (required, string): Message timestamp (e.g., "1703001234.567890")
- `include_thread_replies` (optional, boolean): Include all thread replies. Default: true
- `include_context` (optional, boolean): Include surrounding messages (before/after). Default: false
- `context_count` (optional, int): Number of messages before/after to include. Default: 5

**Returns**: JSON with single message and context
```json
{
  "message": {
    "ts": "1703001234.567890",
    "text": "Full message text...",
    "user": "U1234567890",
    "username": "dan",
    "real_name": "Dan Johnson",
    "datetime": "2024-12-19T14:30:34Z",
    "permalink": "https://workspace.slack.com/archives/C1234567890/p1703001234567890",
    "channel_id": "C1234567890",
    "channel_name": "random",
    "thread_ts": null,
    "reactions": [],
    "files": [],
    "links": [],
    "thread_replies": []
  },
  "context": {
    "before": [...],  // if include_context=true
    "after": [...]
  }
}
```

**Use Cases**:
- Retrieve specific message mentioned by user
- Get message with surrounding context
- Get exact post with all details

---

### 2.3 `get_slack_thread_replies`

**Purpose**: Get all replies in a thread

**Parameters**:
- `channel` (required, string): Channel ID or name
- `thread_ts` (required, string): Thread timestamp (parent message ts)
- `limit` (optional, int): Maximum replies. Default: 1000

**Returns**: JSON with parent message and all replies
```json
{
  "channel_id": "C1234567890",
  "channel_name": "random",
  "thread_ts": "1703001234.567890",
  "parent_message": {
    "ts": "1703001234.567890",
    "text": "Parent message text...",
    "user": "U123",
    "datetime": "2024-12-19T14:30:34Z",
    "permalink": "..."
  },
  "replies": [
    {
      "ts": "1703001250.123456",
      "text": "Reply text...",
      "user": "U456",
      "datetime": "2024-12-19T14:31:10Z",
      "permalink": "..."
    }
  ],
  "reply_count": 1
}
```

**Use Cases**:
- Get complete thread discussion
- Analyze thread conversations
- Extract all responses to a message

---

## 3. Search Tools

### 3.1 `search_slack_messages`

**Purpose**: Search for messages across workspace with flexible filters

**Parameters**:
- `query` (required, string): Search query/keywords
- `channel` (optional, string): Limit search to specific channel (ID or name)
- `user` (optional, string): Filter by user ID or username
- `start_date` (optional, string): Start date (YYYY-MM-DD or ISO 8601)
- `end_date` (optional, string): End date (YYYY-MM-DD or ISO 8601)
- `sort` (optional, string): Sort order: "score" (relevance) or "timestamp" (newest first). Default: "score"
- `count` (optional, int): Number of results. Default: 20, max: 100
- `include_files` (optional, boolean): Include file results. Default: false
- `highlight` (optional, boolean): Include highlight markers. Default: true
- `sort_by` (optional, string): Additional sort after search: "timestamp", "reactions", "reply_count" (applied after search results)
- `min_reactions` (optional, int): Filter search results by minimum reaction count
- `min_reply_count` (optional, int): Filter search results by minimum reply count
- `only_thread_parents` (optional, boolean): Return only messages that are thread parents
- `has_reactions` (optional, boolean): Return only messages with reactions

**Returns**: JSON with search results
```json
{
  "query": "new candidate",
  "total_results": 15,
  "messages": [
    {
      "ts": "1703001234.567890",
      "text": "I think the new candidate looks great...",
      "user": "U1234567890",
      "username": "sue",
      "real_name": "Sue Smith",
      "datetime": "2024-12-19T14:30:34Z",
      "permalink": "https://workspace.slack.com/archives/C1234567890/p1703001234567890",
      "channel_id": "C1234567890",
      "channel_name": "hiring",
      "highlight": {
        "text": "...<b>new candidate</b> looks great...",
        "matches": ["new candidate"]
      },
      "thread_ts": null,
      "reactions": [],
      "files": [],
      "links": []
    }
  ],
  "pagination": {
    "total": 15,
    "page": 1,
    "pages": 1
  }
}
```

**Use Cases**:
- "What did Sue say about the new candidate?"
- "What are people posting about AI lately?"
- Cross-channel topic searches

---

### 3.2 `search_slack_messages_by_user`

**Purpose**: Get messages from a specific user, optionally filtered by topic/keyword

**Parameters**:
- `user` (required, string): User ID or username (e.g., "U1234567890" or "sue")
- `keyword` (optional, string): Keyword/topic to filter messages
- `channel` (optional, string): Limit to specific channel
- `start_date` (optional, string): Start date
- `end_date` (optional, string): End date
- `limit` (optional, int): Maximum results. Default: 100

**Returns**: JSON with user's messages
```json
{
  "user_id": "U1234567890",
  "username": "sue",
  "real_name": "Sue Smith",
  "keyword": "new candidate",
  "messages": [
    {
      "ts": "1703001234.567890",
      "text": "I think the new candidate looks great...",
      "datetime": "2024-12-19T14:30:34Z",
      "permalink": "...",
      "channel_id": "C1234567890",
      "channel_name": "hiring",
      "thread_ts": null,
      "files": [],
      "links": []
    }
  ],
  "total_count": 5
}
```

**Use Cases**:
- "What did Sue say about X?"
- User-specific message history
- Track user's contributions on a topic

---

## 4. File & Link Extraction Tools

### 4.1 `extract_slack_files_from_messages`

**Purpose**: Extract file attachments from messages (from search results or channel)

**Parameters**:
- `messages` (optional, array): Array of message objects (if extracting from existing results)
- `channel` (optional, string): Channel to extract files from (alternative to messages)
- `start_date` (optional, string): Start date for channel extraction
- `end_date` (optional, string): End date for channel extraction
- `file_types` (optional, string): Comma-separated file types (e.g., "pdf,doc,docx"). Default: all
- `limit` (optional, int): Maximum files. Default: 100

**Returns**: JSON with files extracted
```json
{
  "files": [
    {
      "id": "F1234567890",
      "name": "MoDa_Proposal.pdf",
      "title": "MoDa Proposal Document",
      "mimetype": "application/pdf",
      "filetype": "pdf",
      "size": 2097152,
      "url_private_download": "https://files.slack.com/files-pri/.../download/Moda_Proposal.pdf",
      "url_private": "https://files.slack.com/files-pri/...",
      "created": 1703001000,
      "created_datetime": "2024-12-19T14:23:20Z",
      "user": "U1234567890",
      "username": "danielle",
      "real_name": "Danielle Chen",
      "message_ts": "1703001234.567890",
      "message_text": "Here's the doc for this meeting",
      "channel_id": "C1234567890",
      "channel_name": "proposals",
      "permalink": "https://workspace.slack.com/archives/C1234567890/p1703001234567890",
      "is_external": false,
      "is_public": false,
      "initial_comment": "Here's the doc for this meeting"
    }
  ],
  "total_count": 1
}
```

**Use Cases**:
- "Give me the doc Danielle shared for this meeting"
- Extract files from search results
- List files shared in a channel/timeframe

---

### 4.2 `extract_slack_links_from_messages`

**Purpose**: Extract URLs/links from messages

**Parameters**:
- `messages` (optional, array): Array of message objects (if extracting from existing results)
- `channel` (optional, string): Channel to extract links from
- `start_date` (optional, string): Start date
- `end_date` (optional, string): End date
- `link_types` (optional, string): Filter by type: "google_docs", "google_drive", "external", "all". Default: "all"
- `limit` (optional, int): Maximum links. Default: 100

**Returns**: JSON with links extracted
```json
{
  "links": [
    {
      "url": "https://docs.google.com/document/d/abc123/edit",
      "display_text": "MoDa Proposal",
      "type": "google_docs",
      "domain": "docs.google.com",
      "message_ts": "1703001234.567890",
      "message_text": "Here's the doc: https://docs.google.com/document/d/abc123/edit",
      "user": "U1234567890",
      "username": "danielle",
      "real_name": "Danielle Chen",
      "datetime": "2024-12-19T14:30:34Z",
      "channel_id": "C1234567890",
      "channel_name": "proposals",
      "permalink": "https://workspace.slack.com/archives/C1234567890/p1703001234567890"
    }
  ],
  "total_count": 1
}
```

**Use Cases**:
- "What links did people share today?"
- Extract Google Docs/Drive links
- Track shared resources

---

### 4.3 `list_slack_files`

**Purpose**: List files in workspace (alternative to extracting from messages)

**Parameters**:
- `types` (optional, string): File types (e.g., "pdf,images"). Default: all
- `user` (optional, string): Filter by user ID
- `start_date` (optional, string): Files created after this date
- `end_date` (optional, string): Files created before this date
- `channel` (optional, string): Filter by channel (requires searching messages)
- `count` (optional, int): Number of results. Default: 100, max: 1000

**Returns**: JSON with file list
```json
{
  "files": [
    {
      "id": "F1234567890",
      "name": "document.pdf",
      "title": "Document Title",
      "mimetype": "application/pdf",
      "filetype": "pdf",
      "size": 1048576,
      "url_private_download": "https://files.slack.com/...",
      "created": 1703001000,
      "created_datetime": "2024-12-19T14:23:20Z",
      "user": "U1234567890",
      "username": "danielle",
      "real_name": "Danielle Chen"
    }
  ],
  "total_count": 50
}
```

**Use Cases**:
- "What files did people share this week?"
- List recent file uploads
- Find files by type

---

## 5. User Information Tools

### 5.1 `list_slack_users`

**Purpose**: List all users in workspace

**Parameters**:
- `include_deleted` (optional, boolean): Include deleted users. Default: false
- `limit` (optional, int): Maximum users. Default: 1000

**Returns**: JSON with user list
```json
{
  "users": [
    {
      "id": "U1234567890",
      "name": "sue",
      "real_name": "Sue Smith",
      "display_name": "Sue",
      "email": "sue@example.com",
      "image_24": "https://avatars.slack-edge.com/...",
      "image_32": "https://avatars.slack-edge.com/...",
      "image_72": "https://avatars.slack-edge.com/...",
      "is_admin": false,
      "is_owner": false,
      "is_bot": false,
      "is_deleted": false,
      "tz": "America/New_York",
      "tz_label": "Eastern Standard Time",
      "presence": "active"
    }
  ],
  "total_count": 150
}
```

**Use Cases**:
- User discovery
- Get user IDs for filtering
- User directory

---

### 5.2 `get_slack_user_info`

**Purpose**: Get detailed information about a specific user

**Parameters**:
- `user` (required, string): User ID or username

**Returns**: JSON with user details
```json
{
  "id": "U1234567890",
  "name": "sue",
  "real_name": "Sue Smith",
  "display_name": "Sue",
  "email": "sue@example.com",
  "image_24": "https://avatars.slack-edge.com/...",
  "image_32": "https://avatars.slack-edge.com/...",
  "image_72": "https://avatars.slack-edge.com/...",
  "image_192": "https://avatars.slack-edge.com/...",
  "image_512": "https://avatars.slack-edge.com/...",
  "is_admin": false,
  "is_owner": false,
  "is_bot": false,
  "is_deleted": false,
  "tz": "America/New_York",
  "tz_label": "Eastern Standard Time",
  "presence": "active",
  "status_text": "",
  "status_emoji": ""
}
```

**Use Cases**:
- Get user details for context
- Resolve usernames to IDs
- User profile information

---

## 6. Thread Discovery Tools

### 6.1 `get_slack_threads_in_channel`

**Purpose**: Get all thread parent messages in a channel (messages that have replies)

**Parameters**:
- `channel` (required, string): Channel ID or name
- `start_date` (optional, string): Start date (YYYY-MM-DD or ISO 8601)
- `end_date` (optional, string): End date (YYYY-MM-DD or ISO 8601)
- `min_reply_count` (optional, int): Minimum replies to include. Default: 1
- `sort_by` (optional, string): Sort order: "timestamp" (default), "reply_count", "reactions"
- `sort_order` (optional, string): "asc" or "desc". Default: "desc"
- `limit` (optional, int): Maximum threads. Default: 100
- `include_thread_replies` (optional, boolean): Include full thread replies. Default: true

**Returns**: Dict[str, Any] with structure:
```python
{
  "status": "ok",
  "data": {
    "channel_id": "C1234567890",
    "channel_name": "random",
    "threads": [
      {
        "ts": "1703001234.567890",
        "text": "Parent message text...",
        "user": "U1234567890",
        "username": "sue",
        "datetime": "2024-12-19T14:30:34Z",
        "permalink": "...",
        "reply_count": 5,
        "reply_users_count": 3,
        "reactions": [...],
        "thread_replies": [...]  // if include_thread_replies=true
      }
    ],
    "total_count": 10,
    "date_range": {...}
  }
}
```

**Use Cases**:
- Find all threads started in a time period
- Get popular discussions (sorted by reply_count)
- Monitor thread activity

---

## 7. Utility Tools

### 7.1 `get_slack_message_permalink`

**Purpose**: Generate permanent link to a message

**Parameters**:
- `channel` (required, string): Channel ID or name
- `message_ts` (required, string): Message timestamp

**Returns**: JSON with permalink
```json
{
  "channel_id": "C1234567890",
  "channel_name": "random",
  "message_ts": "1703001234.567890",
  "permalink": "https://concord-consortium.slack.com/archives/C1234567890/p1703001234567890",
  "success": true
}
```

**Use Cases**:
- Generate shareable links
- Reference messages in responses
- Deep linking to Slack

---

### 7.2 `resolve_slack_user_name`

**Purpose**: Convert username to user ID (helper utility)

**Parameters**:
- `username` (required, string): Username (e.g., "sue")

**Returns**: JSON with user ID
```json
{
  "username": "sue",
  "user_id": "U1234567890",
  "real_name": "Sue Smith",
  "found": true
}
```

**Use Cases**:
- Convert user-provided names to IDs
- Validate user existence

---

## Letta Tool Implementation Requirements

### Critical Requirements (from coding_custom_letta_tools.md)

1. **Return Type**: All tools must return `Dict[str, Any]` (NOT JSON strings)
   - Use consistent structure: `{"status": "ok"|"error", "data": {...}, "error_message": "..."}`

2. **Function Structure**:
   ```python
   from typing import Dict, Any, Optional
   
   def tool_name(param1: Optional[str] = None) -> Dict[str, Any]:
       """Tool description."""
       # 1. IMPORTS FIRST (inside function, at very beginning)
       import os
       import traceback
       import json
       import urllib.request
       import urllib.parse
       from datetime import datetime
       
       # 2. TRY-EXCEPT WRAPPER (wrap all logic)
       try:
           # 3. DEFAULTS
           if param1 is None:
               param1 = "default"
           
           # 4. MAIN LOGIC (inline everything, NO nested def statements)
           # All helper logic must be inlined
           
           return {
               "status": "ok",
               "data": {...},
               "metadata": {...}
           }
       
       except Exception as e:
           return {
               "status": "error",
               "error_message": str(e),
               "traceback": traceback.format_exc()
           }
   ```

3. **NO Nested Functions**: 
   - ❌ DO NOT use `def` statements inside tools
   - ✅ Inline all helper logic
   - ✅ Use lambdas only for simple sorting/filtering

4. **Imports**:
   - Module-level: Only `from typing import Dict, Any, Optional`
   - Function-level: All other imports at the very beginning of function

5. **Docstrings**:
   - Must include `Args:` section for all parameters
   - Must include `Returns:` section describing return dictionary structure

### Common Patterns

1. **Channel Name Resolution**: All tools that accept `channel` parameter should handle both channel IDs and names (with # or without) - inline the resolution logic

2. **User Name Resolution**: All tools that accept `user` parameter should handle both user IDs and usernames - inline the resolution logic

3. **Date Handling**: 
   - Accept YYYY-MM-DD format (interpreted as start/end of day in workspace timezone)
   - Accept ISO 8601 datetime strings
   - Accept Unix timestamps
   - Convert to Slack API timestamp format internally - inline conversion logic

4. **Pagination**: 
   - Tools should handle pagination automatically when possible - inline pagination loop
   - Return `has_more` indicator when more data available
   - Support `limit` parameter to control result size

5. **Thread Replies**:
   - When `include_thread_replies=true`, fetch all replies automatically - inline the fetch loop
   - Include replies in `thread_replies` array within parent message
   - One API call per thread (efficient batching where possible)

6. **Error Handling**:
   - Always wrap in try-except
   - Return structured error: `{"status": "error", "error_message": "...", "traceback": "..."}`
   - Include helpful context (channel not found, user not found, etc.)

7. **Rate Limiting**:
   - Implement rate limit awareness
   - Return appropriate errors when rate limited
   - Consider batching multiple API calls where possible

### Return Data Structure Principles

**Standard Return Format**:
```python
{
    "status": "ok" | "error",
    "data": {
        # Actual result data here
    },
    "metadata": {
        # Optional metadata (counts, date ranges, etc.)
    },
    "error_message": "..."  # Only present if status == "error"
}
```

**Data Structure Principles**:
- **Complete Context**: Always include channel, user, timestamp, IDs
- **Human-Readable**: Include names (channel_name, username, real_name) alongside IDs
- **Permalinks**: Include permalinks for all messages
- **Grouped Data**: Thread replies within parent messages, files/links within messages
- **Metadata**: Include query metadata (date ranges, filters applied, counts)
- **Extensible**: Structure allows adding fields without breaking changes

### Example Tool Template

```python
from typing import Dict, Any, Optional

def get_slack_messages(
    channel: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get messages from a Slack channel with optional date filtering.
    
    Args:
        channel: Channel ID or name (e.g., "C1234567890" or "#random")
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
        limit: Maximum messages to return (optional, default: 100)
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - data: Dictionary with "messages" array and metadata
        - error_message: Error message if status is "error"
    """
    # IMPORTS FIRST
    import os
    import traceback
    import json
    import urllib.request
    import urllib.parse
    from datetime import datetime
    
    # TRY-EXCEPT WRAPPER
    try:
        # DEFAULTS (inline)
        if limit is None:
            limit = 100
        
        # Channel resolution (inline, no helper function)
        channel_id = channel
        if channel.startswith("#"):
            channel_name = channel[1:]
            # Inline channel lookup logic here...
            # (would need to call conversations.list and find matching channel)
        
        # Date conversion (inline)
        oldest_ts = None
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                oldest_ts = str(int(start_dt.timestamp()))
            except:
                pass
        
        # API call (inline)
        url = "https://slack.com/api/conversations.history"
        params = {"channel": channel_id, "limit": limit}
        if oldest_ts:
            params["oldest"] = oldest_ts
        
        query_string = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{url}?{query_string}",
            headers={"Authorization": f"Bearer {os.getenv('SLACK_MCP_XOXP_TOKEN', '')}"}
        )
        
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode('utf-8'))
        
        if not data.get("ok"):
            return {
                "status": "error",
                "error_message": data.get("error", "Unknown Slack API error")
            }
        
        messages = data.get("messages", [])
        
        # Process messages (inline, no helper functions)
        processed_messages = []
        for msg in messages:
            processed_messages.append({
                "ts": msg.get("ts"),
                "text": msg.get("text", ""),
                "user": msg.get("user"),
                # ... more fields inline
            })
        
        return {
            "status": "ok",
            "data": {
                "messages": processed_messages,
                "channel_id": channel_id,
                "total_count": len(processed_messages)
            },
            "metadata": {
                "date_range": {
                    "start": start_date,
                    "end": end_date
                }
            }
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "traceback": traceback.format_exc()
        }
```
