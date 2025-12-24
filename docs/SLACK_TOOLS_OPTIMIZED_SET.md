# Slack Tools: Optimized Toolset (4-5 Tools)

## Goal

Reduce from 14 tools to 4-5 tools while maintaining:
- Clear, self-evident purposes
- Non-overlapping functionality
- Support for all use cases with minimal tool calls
- LLM-friendly naming and structure

---

## Proposed Optimized Toolset: 4 Tools

### Tool 1: `get_slack_channels`

**Purpose**: Get information about Slack channels

**Operations**:
- List all channels (when `channel` not provided)
- Get specific channel details (when `channel` provided)
- Resolve channel names to IDs (built-in when channel name provided)

**Parameters**:
- `channel` (optional, string): Channel ID or name. If provided, returns single channel; if omitted, returns list
- `types` (optional, string): Filter by channel types when listing. Default: all
- `exclude_archived` (optional, boolean): Default: true
- `include_members` (optional, boolean): Include member list for single channel. Default: false
- `limit` (optional, int): For listing. Default: 500

**LLM Decision**: "I need channel information" → this tool
**Intuitive**: Yes - channel operations are all about channels

**Consolidates** (3 → 1):
- `list_slack_channels`
- `get_slack_channel_info`
- `resolve_slack_channel_name`

---

### Tool 2: `get_slack_messages`

**Purpose**: Get messages from a specific channel with complete context

**Operations**:
- Get messages from channel with filters
- Get specific message (when `message_ts` provided)
- Get threads (via `only_thread_parents` filter)
- Includes files, links, reactions, thread replies automatically

**Parameters**:
- `channel` (required, string): Channel ID or name
- `start_date` (optional, string): Start date (YYYY-MM-DD or ISO 8601)
- `end_date` (optional, string): End date
- `message_ts` (optional, string): Specific message timestamp (returns single message)
- `limit` (optional, int): Max messages. Default: 100
- `include_thread_replies` (optional, boolean): Default: true
- `include_context` (optional, boolean): If message_ts, include surrounding. Default: false
- `context_count` (optional, int): Messages before/after. Default: 5
- `only_thread_parents` (optional, boolean): Only messages with replies. Default: false
- `min_reply_count` (optional, int): Filter by thread length
- `sort_by` (optional, string): "timestamp", "reactions", "reply_count", "user"
- `sort_order` (optional, string): "asc" or "desc"
- `min_reactions` (optional, int): Filter by reactions
- `has_reactions` (optional, boolean): Only messages with reactions

**LLM Decision**: "I need messages from a channel" → this tool
**Intuitive**: Yes - channel-specific message retrieval

**Consolidates** (5 → 1):
- `get_slack_messages`
- `get_slack_message` (via message_ts parameter)
- `get_slack_thread_replies` (via only_thread_parents)
- `get_slack_threads_in_channel` (via only_thread_parents)
- File/link extraction (auto-included)

**Note**: Files and links are always included in message responses - no separate extraction needed

---

### Tool 3: `search_slack_messages`

**Purpose**: Search for messages across the entire Slack workspace

**Operations**:
- Workspace-wide keyword search
- Search with user filter (replaces `search_slack_messages_by_user`)
- Search with channel filter
- Search with date, engagement, thread filters
- Includes files, links, reactions automatically

**Parameters**:
- `query` (optional, string): Search query/keywords. If omitted, returns recent messages across workspace
- `user` (optional, string): Filter by user ID or username
- `channel` (optional, string): Limit to specific channel (ID or name)
- `start_date` (optional, string): Start date
- `end_date` (optional, string): End date
- `count` (optional, int): Number of results. Default: 20, max: 100
- `sort` (optional, string): Slack's sort: "score" (relevance) or "timestamp". Default: "score"
- `sort_by` (optional, string): Post-search sort: "timestamp", "reactions", "reply_count"
- `min_reactions` (optional, int): Filter by reactions
- `min_reply_count` (optional, int): Filter by thread length
- `only_thread_parents` (optional, boolean): Only thread parents
- `has_reactions` (optional, boolean): Only messages with reactions

**LLM Decision**: "I need to search/find messages across Slack" → this tool
**Intuitive**: Yes - workspace-wide search is distinct from channel retrieval

**Consolidates** (4 → 1):
- `search_slack_messages`
- `search_slack_messages_by_user` (via user parameter)
- File/link extraction (auto-included)
- Workspace-wide file listing (when query="", can search for files)

**Key Insight**: When `query` is omitted or empty, returns recent messages across workspace (useful for "what's happening now")

---

### Tool 4: `get_slack_users`

**Purpose**: Get information about Slack users

**Operations**:
- List all users (when `user` not provided)
- Get specific user details (when `user` provided)
- Resolve usernames to IDs (built-in when username provided)

**Parameters**:
- `user` (optional, string): User ID or username. If provided, returns single user; if omitted, returns list
- `include_deleted` (optional, boolean): For listing. Default: false
- `limit` (optional, int): For listing. Default: 1000

**LLM Decision**: "I need user information" → this tool
**Intuitive**: Yes - user operations are all about users

**Consolidates** (3 → 1):
- `list_slack_users`
- `get_slack_user_info`
- `resolve_slack_user_name`

---

## Total: 4 Tools

1. `get_slack_channels` - Channel information
2. `get_slack_messages` - Messages from channels
3. `search_slack_messages` - Workspace-wide search
4. `get_slack_users` - User information

---

## Use Case Coverage

### "What's going on in Slack right now?"
- Tool: `search_slack_messages` (query="", recent date range)
- Result: Returns recent messages across workspace
- Tool Calls: 1

### "What did Sue say about the new candidate?"
- Tool: `search_slack_messages` (user="sue", query="new candidate")
- Result: Returns Sue's messages matching "new candidate"
- Tool Calls: 1

### "Give me the doc Danielle shared for this meeting"
- Tool: `search_slack_messages` (user="Danielle", query="meeting")
- Result: Returns messages with files/links auto-included
- LLM: Extracts relevant file from message data
- Tool Calls: 1

### "What other pictures of lace work has Hee-Sun shared?"
- Tool: `search_slack_messages` (user="Hee-Sun", query="lace work", long date range)
- Result: Returns messages with files auto-included
- LLM: Filters for images from files array
- Tool Calls: 1

### "Dan said he mentioned Sina's report on Slack last week"
- Tool: `search_slack_messages` (user="Dan", query="Sina's report", date="last week")
- Result: Returns matching messages
- Tool Calls: 1

### "What's happening in Slack with the MoDa proposal?"
- Tool: `search_slack_messages` (query="MoDa proposal")
- Result: Returns messages with files/links auto-included
- Tool Calls: 1

### "What are people posting about AI lately?"
- Tool: `search_slack_messages` (query="AI", recent date range)
- Result: Returns AI-related messages
- Tool Calls: 1

### "What links did people share today?"
- Tool: `search_slack_messages` (query="", date="today")
- Result: Returns messages with links auto-included
- LLM: Extracts and formats links
- Tool Calls: 1

### "What files did people share this week?"
- Tool: `search_slack_messages` (query="", date="this week")
- Result: Returns messages with files auto-included
- LLM: Extracts and formats files
- Tool Calls: 1

### "Get all messages from #random on Dec 19"
- Tool: `get_slack_messages` (channel="#random", start_date="2024-12-19", end_date="2024-12-19")
- Result: Returns all messages with threads, files, links
- Tool Calls: 1

### "Get all threads in #general from last week"
- Tool: `get_slack_messages` (channel="#general", start_date="...", only_thread_parents=true)
- Result: Returns thread parent messages
- Tool Calls: 1

### "Who are the most active users in #engineering?"
- Tool 1: `get_slack_messages` (channel="#engineering", date range)
- LLM: Aggregates by user, counts messages
- Tool Calls: 1

---

## Key Design Decisions

### 1. Channel vs Workspace Boundary
**Decision**: Separate tools for channel-specific vs workspace-wide operations
**Rationale**: 
- Clear mental model: "get from channel" vs "search workspace"
- Different API methods (conversations.history vs search.messages)
- Different use cases

### 2. File/Link Inclusion
**Decision**: Always include files and links in message data
**Rationale**:
- Completeness - LLM has all context
- Reduces tool calls - one call gets everything
- User preference

### 3. Single vs Multiple Operations
**Decision**: Tools handle both "get one" and "get many" based on parameters
**Rationale**:
- Common pattern (REST APIs do this)
- Reduces tool count
- Still clear: provide ID/name = get one, omit = get list

### 4. Thread Handling
**Decision**: Threads included by default, can filter for thread parents only
**Rationale**:
- Complete context by default
- Filter when needed
- Simpler than separate thread tool

### 5. Permalinks and Resolution
**Decision**: Built into tools, not separate
**Rationale**:
- Permalinks always in message data
- Name resolution happens automatically when names provided
- Utilities don't need to be separate tools

---

## Remaining Questions

1. **Empty Query Behavior**: Should `search_slack_messages` with empty query return recent messages workspace-wide? (Proposed: Yes - enables "what's happening now")

2. **Tool Name Clarity**: Are `get_slack_messages` vs `search_slack_messages` clear enough? Alternative: `get_slack_channel_messages` and `search_slack_messages` (Proposed: Current names are clear - "get" implies channel, "search" implies workspace)

3. **Parameter Count**: `get_slack_messages` has ~13 parameters. Is this too many? Should we group some? (Proposed: Acceptable - most are optional, common pattern)

4. **Thread vs Message Distinction**: Is `only_thread_parents` filter intuitive enough, or should we have separate parameter like `message_type` with options? (Proposed: `only_thread_parents` is clear and self-explanatory)

---

## Alternative: 5-Tool Variant

If 4 tools feels too consolidated, consider splitting:

**Option A (Current - 4 tools)**:
- `get_slack_channels`
- `get_slack_messages`
- `search_slack_messages`
- `get_slack_users`

**Option B (5 tools - Split Search)**:
- `get_slack_channels`
- `get_slack_messages`
- `search_slack_messages` (keyword/topic search)
- `get_slack_user_messages` (user-specific retrieval - different from search)
- `get_slack_users`

**Rationale for Option B**: User-specific message retrieval might be common enough to warrant separate tool. However, `search_slack_messages` with `user` parameter handles this well.

**Recommendation**: Stick with 4 tools - clear boundaries, non-overlapping, covers all use cases

---

## Evaluation

### Clarity: ✅
- Each tool has distinct purpose
- Names are self-evident
- Non-overlapping functionality

### Completeness: ✅
- All use cases supported
- All functionality retained
- Files/links auto-included

### Efficiency: ✅
- Most use cases: 1 tool call
- Complex queries: 1-2 tool calls
- Minimal context bloat (4 tools vs 14)

### LLM-Friendly: ✅
- Clear decision tree: need channel info? channels tool. need messages from channel? get_messages. need to search? search tool. need user info? users tool.
- Intuitive parameter usage
- Complete data returned

---

## Final Recommendation: 4 Tools

The 4-tool set provides:
- Maximum consolidation (14 → 4, 71% reduction)
- Clear, non-overlapping purposes
- Complete functionality retention
- Efficient use cases (mostly 1 tool call)
- LLM-friendly structure

This is the optimal balance between consolidation and clarity.
