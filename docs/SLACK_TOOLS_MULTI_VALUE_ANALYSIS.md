# Slack Tools: Multi-Value Parameter Analysis

## Question

Should tools accept multiple values for certain parameters (e.g., `get_slack_messages` with multiple channels) to reduce tool calls and improve efficiency?

## Analysis Framework

For each potential multi-value parameter, evaluate:
1. **Use Case Frequency**: How often is this pattern needed?
2. **API Support**: Does Slack API support this efficiently?
3. **Response Complexity**: How does it affect response structure?
4. **LLM Clarity**: Does it make the tool more or less intuitive?
5. **Efficiency Gain**: Actual reduction in tool calls?

---

## Candidate Parameters for Multi-Value Support

### 1. `get_slack_messages` - Multiple Channels

**Proposal**: Accept `channels` as array/list in addition to single `channel`

**Use Cases**:
- "Get messages from #general and #random on Dec 19"
- "What's happening in the engineering channels?"
- "Get all messages from project channels"

**API Reality**:
- Slack `conversations.history` works **one channel at a time**
- Requires multiple API calls regardless
- No bulk API endpoint

**Implementation Options**:

**Option A: Accept Array, Return Grouped**
```python
{
  "channels": [
    {
      "channel_id": "C123",
      "channel_name": "general",
      "messages": [...]
    },
    {
      "channel_id": "C456", 
      "channel_name": "random",
      "messages": [...]
    }
  ]
}
```

**Option B: Accept Array, Return Flat**
```python
{
  "messages": [
    {
      "channel_id": "C123",
      "channel_name": "general",
      "message": {...}
    },
    {
      "channel_id": "C456",
      "channel_name": "random", 
      "message": {...}
    }
  ]
}
```

**Evaluation**:
- ✅ **Use Case**: Common pattern (monitoring multiple channels)
- ✅ **Efficiency**: Reduces tool calls (1 call vs N calls)
- ⚠️ **API**: Requires N API calls anyway (but batched internally)
- ✅ **Response**: Grouped by channel is clearer (Option A)
- ✅ **LLM Clarity**: Still clear - "get messages from these channels"
- ✅ **Backward Compat**: Single channel still works

**Recommendation**: **YES** - Support array of channels, return grouped by channel

---

### 2. `get_slack_users` - Multiple Users

**Proposal**: Accept `users` as array in addition to single `user`

**Use Cases**:
- "Get info for Sue, Dan, and Danielle"
- Batch user lookup from message user IDs
- Get multiple user profiles at once

**API Reality**:
- Slack `users.info` works **one user at a time**
- `users.list` gets all users (but can't filter to specific set)
- Requires multiple API calls

**Response Structure**:
```python
{
  "users": [
    {
      "id": "U123",
      "username": "sue",
      "profile": {...}
    },
    {
      "id": "U456",
      "username": "dan",
      "profile": {...}
    }
  ]
}
```

**Evaluation**:
- ✅ **Use Case**: Common pattern (batch lookups)
- ✅ **Efficiency**: Reduces tool calls
- ⚠️ **API**: Requires N API calls (but batched)
- ✅ **Response**: Array is clear
- ✅ **LLM Clarity**: Clear - "get info for these users"
- ✅ **Backward Compat**: Single user still works

**Recommendation**: **YES** - Support array of users

---

### 3. `get_slack_channels` - Multiple Channels

**Proposal**: Accept `channels` as array for getting multiple channel details

**Use Cases**:
- "Get details for #general, #random, and #engineering"
- Batch channel lookup

**API Reality**:
- Slack `conversations.info` works **one channel at a time**
- `conversations.list` gets all channels (but can't filter to specific set)
- Requires multiple API calls

**Evaluation**:
- ⚠️ **Use Case**: Less common (usually want one channel or all channels)
- ✅ **Efficiency**: Reduces tool calls when needed
- ⚠️ **API**: Requires N API calls
- ✅ **Response**: Array is clear
- ✅ **Backward Compat**: Single channel or list all still works

**Recommendation**: **MAYBE** - Lower priority, but useful for consistency

---

### 4. `search_slack_messages` - Multiple Users

**Proposal**: Accept `users` as array to search messages from multiple users

**Use Cases**:
- "What did Sue, Dan, and Danielle say about X?"
- Search across multiple user's messages

**API Reality**:
- Slack `search.messages` supports **single user filter** (`from:username`)
- To search multiple users, need multiple API calls or post-filter
- Could search without user filter, then filter results

**Implementation Options**:

**Option A: Multiple Searches**
- Make N API calls (one per user), combine results

**Option B: Single Search + Filter**
- Single search without user filter, filter results by user IDs

**Option C: Query Syntax**
- Use Slack query syntax like `from:sue OR from:dan OR from:danielle`

**Evaluation**:
- ✅ **Use Case**: Common pattern (team discussions)
- ⚠️ **API**: Slack search supports OR syntax in query
- ⚠️ **Efficiency**: Option C (query syntax) is most efficient
- ✅ **LLM Clarity**: Clear intent - "search these users"
- ⚠️ **Complexity**: Option C requires building query string

**Recommendation**: **YES** - Support array, use Slack query syntax (`from:user1 OR from:user2`) for efficiency

---

### 5. `search_slack_messages` - Multiple Channels

**Proposal**: Accept `channels` as array to limit search to multiple channels

**Use Cases**:
- "Search for 'bug' in #engineering and #bugs"
- Limit search scope to specific channels

**API Reality**:
- Slack `search.messages` supports **single channel filter** (`in:channelname`)
- Supports OR syntax: `in:channel1 OR in:channel2`

**Evaluation**:
- ✅ **Use Case**: Common pattern (searching project channels)
- ✅ **API**: Slack supports OR syntax
- ✅ **Efficiency**: Single API call with OR syntax
- ✅ **LLM Clarity**: Clear intent
- ✅ **Backward Compat**: Single channel still works

**Recommendation**: **YES** - Support array, use Slack query syntax

---

### 6. `get_slack_messages` - Multiple Message Timestamps

**Proposal**: Accept `message_ts` as array to get multiple specific messages

**Use Cases**:
- Get multiple specific messages by timestamp
- Less common - usually want single message or date range

**Evaluation**:
- ❌ **Use Case**: Rare pattern (usually single message or date range)
- ⚠️ **Efficiency**: Would require N API calls anyway
- ❌ **Complexity**: Adds complexity for rare case

**Recommendation**: **NO** - Not worth the complexity

---

## Summary Recommendations

### High Priority (Clear Benefits)

1. **`get_slack_messages.channels`** (array)
   - Common use case (multiple channels)
   - Clear response structure (grouped by channel)
   - Significant tool call reduction

2. **`get_slack_users.users`** (array)
   - Common use case (batch lookups)
   - Clear response structure
   - Significant tool call reduction

3. **`search_slack_messages.users`** (array)
   - Common use case (team discussions)
   - Efficient with Slack query syntax
   - Significant tool call reduction

4. **`search_slack_messages.channels`** (array)
   - Common use case (project channels)
   - Efficient with Slack query syntax
   - Significant tool call reduction

### Medium Priority (Useful but Less Critical)

5. **`get_slack_channels.channels`** (array)
   - Less common, but useful for consistency
   - Easy to implement

### Low Priority (Not Recommended)

6. **`get_slack_messages.message_ts`** (array)
   - Rare use case
   - Not worth complexity

---

## Implementation Pattern

For tools supporting both single and multiple values:

**Parameter Design**:
```python
# Accept both formats
channel: Optional[str | List[str]] = None  # Single channel or list
channels: Optional[List[str]] = None        # Explicit list parameter

# Prefer explicit parameter if both provided
# But also allow single value in list parameter for consistency
```

**Response Design** (for grouped data like channels):
```python
# Single channel: return channel object
if single_channel:
    return {
        "status": "ok",
        "data": {
            "channel": {...},
            "messages": [...]
        }
    }

# Multiple channels: return grouped array
if multiple_channels:
    return {
        "status": "ok",
        "data": {
            "channels": [
                {
                    "channel_id": "C123",
                    "channel_name": "general",
                    "messages": [...]
                },
                {
                    "channel_id": "C456",
                    "channel_name": "random",
                    "messages": [...]
                }
            ]
        }
    }
```

**Response Design** (for flat data like users):
```python
# Single user: return user object
if single_user:
    return {
        "status": "ok",
        "data": {
            "user": {...}
        }
    }

# Multiple users: return array
if multiple_users:
    return {
        "status": "ok",
        "data": {
            "users": [{...}, {...}]
        }
    }
```

---

## Tool Call Reduction Examples

### Before (Multiple Calls)
```
User: "Get messages from #general and #random on Dec 19"
LLM: 
  1. get_slack_messages(channel="#general", start_date="2024-12-19")
  2. get_slack_messages(channel="#random", start_date="2024-12-19")
Total: 2 tool calls
```

### After (Single Call)
```
User: "Get messages from #general and #random on Dec 19"
LLM:
  1. get_slack_messages(channels=["#general", "#random"], start_date="2024-12-19")
Total: 1 tool call
```

### Before (Multiple Calls)
```
User: "What did Sue, Dan, and Danielle say about the proposal?"
LLM:
  1. search_slack_messages(user="Sue", query="proposal")
  2. search_slack_messages(user="Dan", query="proposal")
  3. search_slack_messages(user="Danielle", query="proposal")
Total: 3 tool calls
```

### After (Single Call)
```
User: "What did Sue, Dan, and Danielle say about the proposal?"
LLM:
  1. search_slack_messages(users=["Sue", "Dan", "Danielle"], query="proposal")
Total: 1 tool call
```

---

## Questions for Further Consideration

1. **Parameter Naming**: Should we use:
   - Single parameter that accepts both types: `channel: str | List[str]`?
   - Separate parameters: `channel: str` OR `channels: List[str]`?
   - Recommendation: Single parameter for simplicity (`channel` accepts str or list)

2. **Response Consistency**: Should single vs multiple always return different structures, or normalize?
   - Option A: Different structures (single = object, multiple = array)
   - Option B: Always array (single = array with one item)
   - Recommendation: Option A - clearer semantics

3. **Backward Compatibility**: How to handle existing single-value usage?
   - Recommendation: Continue supporting single values, add array support

4. **Limit Handling**: For multiple channels/users, how to handle per-item limits vs total limits?
   - Recommendation: Per-item limit (each channel gets limit messages), plus optional total limit

---

## Final Recommendation

**Support multi-value parameters for**:
1. `get_slack_messages.channels` - Array of channels
2. `get_slack_users.users` - Array of users  
3. `search_slack_messages.users` - Array of users (use OR query syntax)
4. `search_slack_messages.channels` - Array of channels (use OR query syntax)
5. `get_slack_channels.channels` - Array of channels (lower priority)

**Implementation approach**:
- Accept both single value and array/list
- For grouped data (channels), return grouped structure
- For flat data (users), return array
- Use Slack query syntax where available for efficiency
- Maintain backward compatibility with single values

This optimization significantly reduces tool calls for common patterns while maintaining clarity and simplicity.
