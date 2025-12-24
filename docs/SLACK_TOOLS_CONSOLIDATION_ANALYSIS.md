# Slack Tools: Consolidation Analysis

## Current State: 14 Tools

### Tool Inventory

**Channel Discovery** (3):
- `list_slack_channels`
- `get_slack_channel_info`
- `resolve_slack_channel_name`

**Message Retrieval** (3):
- `get_slack_messages`
- `get_slack_message` (single message)
- `get_slack_thread_replies`

**Search** (2):
- `search_slack_messages`
- `search_slack_messages_by_user`

**File & Link** (3):
- `extract_slack_files_from_messages`
- `extract_slack_links_from_messages`
- `list_slack_files`

**User Information** (2):
- `list_slack_users`
- `get_slack_user_info`

**Thread Discovery** (1):
- `get_slack_threads_in_channel`

**Utilities** (2):
- `get_slack_message_permalink`
- `resolve_slack_user_name`

---

## Consolidation Strategy

### Principles
1. **Self-Evident Names**: Tool name should clearly indicate what it does
2. **Non-Overlapping**: Each tool handles a distinct, clear domain
3. **LLM-Friendly**: LLM should know which tool to use for any query
4. **Minimal Tool Calls**: Support use cases with 1-2 tool calls
5. **Auto-Include**: Files/links included in message retrieval (not separate)

### Analysis: What Can Be Combined?

#### Group 1: Channel Operations
**Current**: `list_slack_channels`, `get_slack_channel_info`, `resolve_slack_channel_name`
**Rationale**: All are about channel discovery/metadata
**Combined**: Single tool that handles all channel operations

#### Group 2: Message Retrieval vs Search
**Current**: `get_slack_messages`, `search_slack_messages`, `search_slack_messages_by_user`
**Rationale**: 
- `get_slack_messages` = channel-specific retrieval
- `search_slack_messages` = workspace-wide search
- `search_slack_messages_by_user` = just search with user filter (redundant)
**Decision**: Keep channel retrieval separate from workspace search (different use cases)

#### Group 3: Single Message vs Batch
**Current**: `get_slack_message`, `get_slack_messages`, `get_slack_thread_replies`
**Rationale**:
- `get_slack_message` = special case of `get_slack_messages` (limit=1, specific ts)
- `get_slack_thread_replies` = special case (only_thread_parents filter)
**Decision**: Consolidate into `get_slack_messages` with parameters

#### Group 4: File & Link Extraction
**Current**: 3 separate tools
**Rationale**: User preference - auto-include in messages
**Decision**: Always include in message data, no separate tools

#### Group 5: User Operations
**Current**: `list_slack_users`, `get_slack_user_info`, `resolve_slack_user_name`
**Rationale**: All are about user discovery/metadata
**Combined**: Single tool that handles all user operations

#### Group 6: Utilities
**Current**: `get_slack_message_permalink`, `resolve_slack_user_name`
**Rationale**: 
- Permalinks should be in message data (always included)
- Name resolution can be built into tools that need it
**Decision**: Build into tools, not separate

---

## Proposed Consolidated Toolset: 4 Tools

### Tool 1: `get_slack_channels`

**Purpose**: Get channel information - list all channels, get specific channel details, or resolve channel names

**Key Insight**: All channel operations are variations of "get channel info"

**Parameters**:
- `channel` (optional, string): Channel ID or name (e.g., "#random" or "C1234567890"). If provided, returns single channel. If omitted, returns list
- `types` (optional, string): For listing, filter by types. Default: all
- `exclude_archived` (optional, boolean): Default: true
- `include_members` (optional, boolean): Include member list for single channel. Default: false
- `limit` (optional, int): For listing. Default: 500

**Consolidates**:
- `list_slack_channels`
- `get_slack_channel_info`
- `resolve_slack_channel_name`

**LLM Understanding**: "I need channel info" → use this tool

---

### Tool 2: `get_slack_messages`

**Purpose**: Get messages from a specific channel with complete context

**Key Insight**: All message retrieval from channels is the same operation with different filters

**Parameters**:
- `channel` (required, string): Channel ID or name
- `start_date` (optional, string): Start date (YYYY-MM-DD or ISO 8601)
- `end_date` (optional, string): End date
- `message_ts` (optional, string): Specific message timestamp (if provided, returns just that message with context)
- `limit` (optional, int): Max messages. Default: 100
- `include_thread_replies` (optional, boolean): Default: true
- `include_context` (optional, boolean): If message_ts provided, include surrounding messages. Default: false
- `context_count` (optional, int): Messages before/after. Default: 5
- `only_thread_parents` (optional, boolean): Only messages with replies. Default: false
- `min_reply_count` (optional, int): Filter by thread length
- `sort_by` (optional, string): "timestamp", "reactions", "reply_count", "user"
- `sort_order` (optional, string): "asc" or "desc"
- `min_reactions` (optional, int): Filter by reactions
- `has_reactions` (optional, boolean): Filter for messages with reactions

**Consolidates**:
- `get_slack_messages`
- `get_slack_message` (via message_ts parameter)
- `get_slack_thread_replies` (via only_thread_parents + include_thread_replies)
- `get_slack_threads_in_channel` (via only_thread_parents)
- File/link extraction (auto-included in response)

**LLM Understanding**: "I need messages from a channel" → use this tool

---

### Tool 3: `search_slack_messages`

**Purpose**: Search for messages across the entire workspace

**Key Insight**: Workspace-wide search is fundamentally different from channel-specific retrieval

**Parameters**:
- `query` (required, string): Search query/keywords
- `user` (optional, string): Filter by user ID or username
- `channel` (optional, string): Limit to specific channel
- `start_date` (optional, string): Start date
- `end_date` (optional, string): End date
- `count` (optional, int): Number of results. Default: 20, max: 100
- `sort_by` (optional, string): Post-search sort: "timestamp", "reactions", "reply_count"
- `min_reactions` (optional, int): Filter by reactions
- `min_reply_count` (optional, int): Filter by thread length
- `only_thread_parents` (optional, boolean): Only thread parents
- `has_reactions` (optional, boolean): Only messages with reactions

**Consolidates**:
- `search_slack_messages`
- `search_slack_messages_by_user` (via user parameter)
- File/link extraction (auto-included in response)

**LLM Understanding**: "I need to search across Slack" → use this tool

---

### Tool 4: `get_slack_users`

**Purpose**: Get user information - list all users, get specific user details, or resolve usernames

**Key Insight**: All user operations are variations of "get user info"

**Parameters**:
- `user` (optional, string): User ID or username (e.g., "sue" or "U1234567890"). If provided, returns single user. If omitted, returns list
- `include_deleted` (optional, boolean): For listing. Default: false
- `limit` (optional, int): For listing. Default: 1000

**Consolidates**:
- `list_slack_users`
- `get_slack_user_info`
- `resolve_slack_user_name`

**LLM Understanding**: "I need user info" → use this tool

---

### Built-In Utilities (Not Separate Tools)

**Permalinks**: Always included in message data
**Name Resolution**: Built into tools that accept names/IDs
**File/Link Extraction**: Always included in message data

---

## Use Case Coverage with 4 Tools

### Use Case 1: "What's going on in Slack right now?"
- Tool: `get_slack_messages` (recent date range, multiple channels)
- Or: `search_slack_messages` (no query, recent date)

### Use Case 2: "What did Sue say about the new candidate?"
- Tool: `search_slack_messages` (user="Sue", query="new candidate")

### Use Case 3: "Give me the doc Danielle shared for this meeting"
- Tool 1: `search_slack_messages` (user="Danielle", query="meeting") → find messages
- Files/links auto-included in response → LLM extracts relevant file

### Use Case 4: "What other pictures of lace work has Hee-Sun shared?"
- Tool: `search_slack_messages` (user="Hee-Sun", query="lace work", long date range)
- Files auto-included → LLM filters for images

### Use Case 5: "Dan said he mentioned Sina's report on Slack last week"
- Tool: `search_slack_messages` (user="Dan", query="Sina's report", date range="last week")

### Use Case 6: "What's happening in Slack with the MoDa proposal?"
- Tool: `search_slack_messages` (query="MoDa proposal")
- Files/links auto-included

### Use Case 7: "What are people posting about AI lately?"
- Tool: `search_slack_messages` (query="AI", recent date range)

### Use Case 8: "What are people most concerned about in Slack?"
- Tool: `get_slack_messages` or `search_slack_messages` (recent messages)
- LLM analyzes sentiment

### Use Case 9: "What links did people share today?"
- Tool: `search_slack_messages` (query="", date="today") or `get_slack_messages` (multiple channels)
- Links auto-included → LLM extracts and formats

### Use Case 10: "What files did people share this week?"
- Tool: `search_slack_messages` (query="", date="this week")
- Files auto-included → LLM extracts and formats

---

## Tool Count: 4 Tools

1. `get_slack_channels` - Channel discovery and info
2. `get_slack_messages` - Messages from channels
3. `search_slack_messages` - Workspace-wide search
4. `get_slack_users` - User discovery and info

---

## Questions for Refinement

1. **Thread Handling**: Should `get_slack_messages` always include thread replies by default, or make it explicit? (Proposed: default true, can disable)

2. **File/Link Inclusion**: Files and links are auto-included. Should there be a parameter to exclude them for performance, or always include? (Proposed: always include - completeness is valuable)

3. **Channel vs Search Boundary**: Is the distinction between channel-specific (`get_slack_messages`) and workspace-wide (`search_slack_messages`) clear enough? (Proposed: Yes - channel-specific is explicit, search is exploratory)

4. **Single vs Multiple Operations**: Tools like `get_slack_channels` do both "list" and "get one" based on whether `channel` parameter is provided. Is this intuitive enough? (Proposed: Yes - common pattern)

5. **Message Permalinks**: Permalinks are always included. Should we also have a parameter to generate permalinks for message timestamps provided as input? (Proposed: No - permalinks are output, not input operation)
