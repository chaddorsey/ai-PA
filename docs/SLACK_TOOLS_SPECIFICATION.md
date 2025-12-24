# Slack Custom Tools: Tool Specifications (Optimized 4-Tool Set)

## Overview

This document specifies the **4 optimized tools** for Slack monitoring and information extraction. All tools return well-structured raw data that enables the LLM to perform analysis, summarization, and intelligent operations.

### Efficiency Recommendations

For optimal performance, prefer using **names** over **IDs** when available:
- **Channel names** (e.g., `"#channel-name"`) vs channel IDs (e.g., `"C1234567890"`): Names avoid resolution API calls
- **Usernames** (e.g., `"username"`) vs user IDs (e.g., `"U1234567890"`): Usernames avoid resolution API calls
- **Email addresses**: Supported in `get_slack_users` but require user list lookup (works fine but slightly slower)

All tools accept both names and IDs for flexibility, but using names directly improves efficiency by reducing API calls.

## Letta Tool Compliance

**CRITICAL**: All tools follow Letta tool registration requirements (see `docs/SLACK_TOOLS_LETTA_COMPLIANCE.md`):

- **Return Type**: All tools return `Dict[str, Any]`, NOT JSON strings
- **Standard Format**: `{"status": "ok"|"error", "data": {...}, "error_message": "..."}`
- **Structure**: Imports inside function, try-except wrapper, no nested `def` statements
- **See**: `context/coding_custom_letta_tools.md` for full requirements

All return examples below show the `data` portion - the actual return includes `status` and wraps data in `data` key.

## Design Principles

1. **Self-Evident Names**: Tool names clearly indicate purpose
2. **Non-Overlapping**: Each tool handles a distinct domain
3. **LLM-Friendly**: Clear decision tree for which tool to use
4. **Minimal Tool Calls**: Most use cases require 1 tool call
5. **Auto-Inclusion**: Files/links always included in message data
6. **Multi-Value Support**: Tools accept both single values and arrays for efficient batch operations

## Tool Summary

1. **`get_slack_channels`** - Channel discovery and information
2. **`get_slack_messages`** - Messages from channels with complete context
3. **`search_slack_messages`** - Workspace-wide message search
4. **`get_slack_users`** - User discovery and information

---

## 1. `get_slack_channels`

### Purpose

Get Slack channel information - list all channels, get specific channel details, or resolve channel names.

**When `channel` parameter is provided**: Returns single channel (or multiple if list provided)  
**When `channel` parameter is omitted**: Returns list of all channels

### Parameters

- `channel` (optional, `str | List[str]`): Channel ID(s) or name(s) (e.g., `"C1234567890"`, `"#random"`, or `["#general", "#random"]`). If omitted, returns list of all channels. **Note**: Both IDs and names work, but names are slightly more efficient as they don't require resolution.
- `types` (optional, `str`): Filter channel types when listing. Comma-separated: `"public_channel,private_channel,mpim,im"`. Default: all types.
- `exclude_archived` (optional, `bool`): Exclude archived channels when listing. Default: `True`.
- `include_members` (optional, `bool`): Include member list for single channel. Default: `False`.
- `limit` (optional, `int`): Maximum number of channels to return when listing. Default: `500`.

### Multi-Value Support

The `channel` parameter accepts both:
- Single value: `"#random"` or `"C1234567890"` → Returns single channel object
- Array: `["#general", "#random"]` → Returns array of channel objects

### Returns

**Single channel** (when single `channel` provided):
```python
{
    "status": "ok",
    "data": {
        "channel": {
            "id": "C1234567890",
            "name": "random",
            "is_channel": True,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
            "is_private": False,
            "is_archived": False,
            "created": 1234567890,
            "creator": "U1234567890",
            "topic": "Random chatter",
            "purpose": "A place for non-work conversations",
            "num_members": 150,
            "members": ["U111", "U222", ...]  # Only if include_members=True
        }
    }
}
```

**Multiple channels** (when `channel` is a list):
```python
{
    "status": "ok",
    "data": {
        "channels": [
            {
                "id": "C1234567890",
                "name": "general",
                ...
            },
            {
                "id": "C0987654321",
                "name": "random",
                ...
            }
        ]
    }
}
```

**List all channels** (when `channel` omitted):
```python
{
    "status": "ok",
    "data": {
        "channels": [
            {
                "id": "C1234567890",
                "name": "general",
                ...
            },
            ...
        ],
        "total": 25
    }
}
```

### Consolidates

- `list_slack_channels`
- `get_slack_channel_info`
- `resolve_slack_channel_name`

### Use Cases

- List all public channels
- Get details for a specific channel
- Get details for multiple channels at once
- Resolve channel name to ID

---

## 2. `get_slack_messages`

### Purpose

Get messages from Slack channel(s) with complete context including threads, files, links, and reactions.

Supports both single channel and multiple channels. When multiple channels provided, returns messages grouped by channel.

### Parameters

- `channel` (required, `str | List[str]`): Channel ID(s) or name(s) (e.g., `"C1234567890"`, `"#random"`, or `["#general", "#random"]`). **Recommendation**: Use channel names when available (e.g., `"#channel-name"`) for slightly better efficiency, though IDs work fine.
- `start_date` (optional, `str`): Start date in YYYY-MM-DD format or ISO 8601 datetime.
- `end_date` (optional, `str`): End date in YYYY-MM-DD format or ISO 8601 datetime.
- `message_ts` (optional, `str`): Specific message timestamp to retrieve (e.g., `"1703001234.567890"`). When provided, returns single message with optional context.
- `limit` (optional, `int`): Maximum messages to return per channel. Default: `100`, max: `1000`.
- `include_thread_replies` (optional, `bool`): Fetch all thread replies. Default: `True`.
- `include_context` (optional, `bool`): Include surrounding messages when `message_ts` provided. Default: `False`.
- `context_count` (optional, `int`): Number of messages before/after to include. Default: `5`.
- `only_thread_parents` (optional, `bool`): Return only messages that have replies. Default: `False`.
- `min_reply_count` (optional, `int`): Filter messages with at least N replies (thread parents only).
- `sort_by` (optional, `str`): Sort order: `"timestamp"` (default), `"reactions"`, `"reply_count"`, `"user"`.
- `sort_order` (optional, `str`): `"asc"` or `"desc"`. Default: `"desc"` for timestamp, `"desc"` for reactions/reply_count.
- `min_reactions` (optional, `int`): Filter messages with at least N reactions.
- `has_reactions` (optional, `bool`): Return only messages with reactions. Default: `False`.

### Multi-Value Support

The `channel` parameter accepts both:
- Single value: `"#random"` → Returns messages for that channel
- Array: `["#general", "#random"]` → Returns messages grouped by channel

### Returns

**Single channel** (when single `channel` provided):
```python
{
    "status": "ok",
    "data": {
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
                "channel_id": "C1234567890",
                "channel_name": "random",
                "thread_ts": None,
                "is_thread_parent": False,
                "reply_count": 0,
                "reply_users_count": 0,
                "reactions": [
                    {
                        "name": "thumbsup",
                        "count": 3,
                        "users": ["U111", "U222", "U333"]
                    }
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
                    {
                        "url": "https://example.com/doc",
                        "display_text": "https://example.com/doc",
                        "type": "link"
                    }
                ],
                "thread_replies": []  # Empty if not a thread parent
            }
        ],
        "has_more": False,
        "total_returned": 1,
        "date_range": {
            "start": "2024-12-19T00:00:00Z",
            "end": "2024-12-19T23:59:59Z"
        }
    }
}
```

**Multiple channels** (when `channel` is a list):
```python
{
    "status": "ok",
    "data": {
        "channels": [
            {
                "channel_id": "C1234567890",
                "channel_name": "general",
                "messages": [...],
                "has_more": False
            },
            {
                "channel_id": "C0987654321",
                "channel_name": "random",
                "messages": [...],
                "has_more": False
            }
        ],
        "total_channels": 2
    }
}
```

**Single message** (when `message_ts` provided):
```python
{
    "status": "ok",
    "data": {
        "message": {
            "ts": "1703001234.567890",
            "text": "Full message text...",
            ...
        },
        "context": {
            "before": [...],  # if include_context=True
            "after": [...]
        }
    }
}
```

### Consolidates

- `get_slack_messages` (channel messages)
- `get_slack_message` (single message via `message_ts` parameter)
- `get_slack_thread_replies` (via `include_thread_replies` parameter)
- `get_slack_threads_in_channel` (via `only_thread_parents` filter)
- File/link data (always included automatically)

### Use Cases

- Get all messages from #random on Dec 19
- Get recent activity in a channel
- Get messages with complete context (threads, files, links)
- Get all threads in a channel (using `only_thread_parents=True`)
- Get messages from multiple channels at once
- Get specific message by timestamp

---

## 3. `search_slack_messages`

### Purpose

Search for messages across the entire Slack workspace.

When `query` is omitted or empty, returns recent messages across workspace (enables "what's happening now" use case).

### Parameters

- `query` (optional, `str`): Search query/keywords. If omitted or empty, returns recent messages across workspace.
- `user` (optional, `str | List[str]`): Filter by user ID(s) or username(s). Can be single value or list. When list provided, uses Slack OR query syntax. **Recommendation**: Use usernames when available for better efficiency (avoids ID-to-username resolution).
- `channel` (optional, `str | List[str]`): Limit to specific channel(s) (ID or name). Can be single value or list. When list provided, uses Slack OR query syntax. **Recommendation**: Use channel names (e.g., `"#channel-name"`) when available for better efficiency, as Slack's search API requires channel names and IDs must be resolved first (adds API calls).
- `start_date` (optional, `str`): Start date (YYYY-MM-DD or ISO 8601).
- `end_date` (optional, `str`): End date (YYYY-MM-DD or ISO 8601).
- `count` (optional, `int`): Number of results. Default: `20`, max: `100`.
- `sort` (optional, `str`): Slack's sort: `"score"` (relevance) or `"timestamp"`. Default: `"score"`.
- `sort_by` (optional, `str`): Post-search sort: `"timestamp"`, `"reactions"`, `"reply_count"`.
- `min_reactions` (optional, `int`): Filter by minimum reaction count.
- `min_reply_count` (optional, `int`): Filter by minimum reply count.
- `only_thread_parents` (optional, `bool`): Return only thread parents. Default: `False`.
- `has_reactions` (optional, `bool`): Return only messages with reactions. Default: `False`.

### Multi-Value Support

**`user` parameter**:
- Single value: `"sue"` → Query: `from:sue` (usernames recommended for efficiency)
- Array: `["sue", "dan", "danielle"]` → Query: `(from:sue OR from:dan OR from:danielle)`
- **Note**: User IDs are supported but will be resolved to usernames (adds API calls). Using usernames directly is more efficient.

**`channel` parameter**:
- Single value: `"#general"` → Query: `in:general` (channel names recommended for efficiency)
- Array: `["#engineering", "#bugs"]` → Query: `(in:engineering OR in:bugs)`
- **Note**: Channel IDs are supported but will be resolved to names (adds API calls). Using channel names directly is more efficient.

Uses Slack's OR query syntax for efficient single API call when multiple values provided.

### Returns

```python
{
    "status": "ok",
    "data": {
        "query": "new candidate from:sue",
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
                "thread_ts": None,
                "is_thread_parent": False,
                "reply_count": 0,
                "reply_users_count": 0,
                "reactions": [],
                "files": [],
                "links": [],
                "highlight": {  # If highlight enabled
                    "text": "...<b>new candidate</b> looks great...",
                    "matches": ["new candidate"]
                }
            }
        ],
        "pagination": {
            "total": 15,
            "page": 1,
            "pages": 1
        }
    }
}
```

### Consolidates

- `search_slack_messages` (workspace search)
- `search_slack_messages_by_user` (via `user` parameter with multi-value support)
- File/link data (always included automatically)

### Use Cases

- "What did Sue say about the new candidate?" → `search_slack_messages(user="sue", query="new candidate")`
- "What's going on in Slack right now?" → `search_slack_messages(query="")`
- "What did Sue, Dan, and Danielle say?" → `search_slack_messages(users=["sue", "dan", "danielle"])`
- "Search for 'bug' in #engineering and #bugs" → `search_slack_messages(query="bug", channels=["#engineering", "#bugs"])`

---

## 4. `get_slack_users`

### Purpose

Get Slack user information - list all users, get specific user details, or resolve usernames.

**When `user` parameter is provided**: Returns single user (or multiple if list provided)  
**When `user` parameter is omitted**: Returns list of all users

### Parameters

- `user` (optional, `str | List[str]`): User ID(s) or username(s) (e.g., `"U1234567890"`, `"sue"`, or `["sue", "dan"]`). If omitted, returns list of all users.
- `include_deleted` (optional, `bool`): Include deleted users when listing. Default: `False`.
- `limit` (optional, `int`): Maximum number of users to return when listing. Default: `1000`.

### Multi-Value Support

The `user` parameter accepts both:
- Single value: `"sue"` → Returns single user object
- Array: `["sue", "dan", "danielle"]` → Returns array of user objects

### Returns

**Single user** (when single `user` provided):
```python
{
    "status": "ok",
    "data": {
        "user": {
            "id": "U1234567890",
            "name": "sue",
            "username": "sue",
            "real_name": "Sue Smith",
            "display_name": "Sue",
            "email": "sue@example.com",
            "image_24": "https://...",
            "image_32": "https://...",
            "image_48": "https://...",
            "image_72": "https://...",
            "image_192": "https://...",
            "image_512": "https://...",
            "status_text": "Out of office",
            "status_emoji": ":palm_tree:",
            "is_admin": False,
            "is_owner": False,
            "is_bot": False,
            "deleted": False,
            "tz": "America/New_York",
            "tz_label": "Eastern Standard Time",
            "tz_offset": -18000
        }
    }
}
```

**Multiple users** (when `user` is a list):
```python
{
    "status": "ok",
    "data": {
        "users": [
            {
                "id": "U1234567890",
                "name": "sue",
                ...
            },
            {
                "id": "U0987654321",
                "name": "dan",
                ...
            }
        ]
    }
}
```

**List all users** (when `user` omitted):
```python
{
    "status": "ok",
    "data": {
        "users": [
            {
                "id": "U1234567890",
                "name": "sue",
                ...
            },
            ...
        ],
        "total": 150
    }
}
```

### Consolidates

- `list_slack_users`
- `get_slack_user_info`
- `resolve_slack_user_name`

### Use Cases

- List all users in workspace
- Get details for a specific user
- Get details for multiple users at once (batch lookup)
- Resolve username to user ID

---

## Implementation Notes

### Compliance Status

- ✅ **Return Type**: All tools return `Dict[str, Any]`
- ✅ **Standard Format**: All use `{"status": "ok"|"error", "data": {...}, "error_message": "..."}`
- ✅ **Imports**: All imports inside functions at the beginning
- ✅ **Try-Except**: All tools wrapped in try-except
- ✅ **Nested Def Statements**: All logic is fully inlined - no nested def statements (fully compliant)

### Multi-Value Parameter Implementation

For parameters that support multi-value (channels, users):
- Accept both `str` and `List[str]` types
- When array provided, return grouped structure (channels) or array (users)
- For search, use Slack's OR query syntax for efficiency (single API call)
- For channel messages, make multiple API calls but group results internally

### Name Resolution

All tools automatically handle name resolution:
- Channel names (e.g., `"#random"`) are resolved to IDs internally
- Usernames (e.g., `"sue"`) are resolved to user IDs internally
- Users can provide either names or IDs - both work

### File and Link Extraction

Files and links are **always included** in message responses:
- No separate extraction tools needed
- Reduces tool calls (one call gets everything)
- Complete context for LLM analysis

### Thread Handling

- Thread replies included by default (`include_thread_replies=True`)
- Can filter for thread parents only (`only_thread_parents=True`)
- Thread replies included in `thread_replies` array within parent message
- Complete thread context provided without separate API calls

---

## Use Case Coverage

All identified use cases are supported with 1 tool call each:

1. "What's going on in Slack right now?" → `search_slack_messages(query="")`
2. "What did Sue say about the new candidate?" → `search_slack_messages(user="sue", query="new candidate")`
3. "Get the doc Danielle shared for this meeting" → `search_slack_messages(user="Danielle", query="meeting")` (files auto-included)
4. "What other pictures of lace work has Hee-Sun shared?" → `search_slack_messages(user="Hee-Sun", query="lace work", long date range)` (files auto-included)
5. "Dan said he mentioned Sina's report on Slack last week" → `search_slack_messages(user="Dan", query="Sina's report", date="last week")`
6. "What's happening in Slack with the MoDa proposal?" → `search_slack_messages(query="MoDa proposal")` (files/links auto-included)
7. "What are people posting about AI lately?" → `search_slack_messages(query="AI", recent date range)`
8. "What are people most concerned about?" → `search_slack_messages(query="", recent)` → LLM analyzes sentiment
9. "What links did people share today?" → `search_slack_messages(query="", date="today")` → LLM extracts links
10. "Get all messages from #random on Dec 19" → `get_slack_messages(channel="#random", start_date="2024-12-19", end_date="2024-12-19")`
11. "Get all threads in #general from last week" → `get_slack_messages(channel="#general", start_date="...", only_thread_parents=True)`
12. "Get messages from #general and #random on Dec 19" → `get_slack_messages(channels=["#general", "#random"], start_date="2024-12-19")` (multi-value support)

---

## See Also

- `docs/SLACK_TOOLS_OPTIMIZED_SET.md` - Consolidation analysis and design decisions
- `docs/SLACK_TOOLS_MULTI_VALUE_ANALYSIS.md` - Multi-value parameter analysis
- `docs/SLACK_TOOLS_LETTA_COMPLIANCE.md` - Letta compliance requirements
- `context/coding_custom_letta_tools.md` - General Letta tool development guide
