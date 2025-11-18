# Google Drive Analytics Monitoring System Design

## Overview

A system to monitor and surface Google Drive activity analytics using Google APIs, scheduled scripts, and Letta agent memory for persistent storage and intelligent analysis.

## System Architecture

### Components

1. **Data Collection Scripts** (Scheduled via cron/scheduler-service)
   - Admin Reports API queries (workspace-wide activity)
   - Drive Activity API queries (per-file activity)
   - Drive API queries (file metadata, permissions, comments)
   - Comments API queries (comment tracking, mentions)

2. **Data Processing & Storage** (Letta agent memory)
   - JSON logs stored in agent memory files (up to 5000 chars each)
   - Running averages and historical data
   - Top lists and trend calculations

3. **Analytics Tools** (Custom tools for Letta agent)
   - Query stored analytics
   - Generate reports
   - Surface trends and insights

4. **Scheduled Jobs** (via scheduler-service)
   - Daily data collection
   - Periodic trend analysis
   - Alert generation

## API Capabilities Analysis

### ✅ Available Capabilities

#### Admin Reports API (v1)
- **Workspace-wide activity**: All Drive events across organization
- **Activity types**: edit, view, create, delete, share, download, etc.
- **Time range**: Up to 180 days
- **Filtering**: By user, event type, date range
- **Limitations**: No built-in aggregation, requires client-side processing

#### Drive Activity API (v2)
- **Per-file activity**: Detailed activity for specific files
- **Activity details**: Who, what, when for each file
- **Filtering**: By file, folder, action type, time range
- **Limitations**: Requires file IDs (need Drive API to get them first)

#### Drive API (v3)
- **File metadata**: Titles, owners, permissions, sharing status
- **File search**: Find files by owner, shared with me, etc.
- **File links**: Generate shareable links
- **Comments**: List comments, get comment details
- **Limitations**: Comments API doesn't directly filter by @mentions (need to parse)

### ⚠️ Partial Capabilities

#### Comments & Mentions
- **Available**: Drive API can list all comments on a file
- **Limitation**: No direct filter for @mentions - need to:
  1. Fetch all comments
  2. Parse comment text for @mentions
  3. Match against your email address
- **Workaround**: Fetch comments, filter client-side

#### Document Change Detection
- **Available**: Activity API shows edit events
- **Limitation**: Doesn't show *what* changed (content diff)
- **Workaround**: Can detect that changes occurred, but not the nature of changes

### ❌ Unavailable Capabilities

1. **Content Summaries**: No API provides document summaries
   - **Workaround**: Would need to fetch document content and use LLM summarization

2. **Document Content**: Drive API can export documents, but:
   - Requires additional processing
   - Large documents may exceed memory limits
   - Export format conversion needed

3. **Built-in Aggregations**: No API provides pre-aggregated statistics
   - **Workaround**: All aggregation must be done client-side

## System Design

### Data Collection Schedule

#### Daily Collection (6:00 AM ET, after previous day closes)
1. **Workspace Activity Snapshot**
   - Query Admin Reports API for previous day
   - Store: Total activities, activity by type, top documents, top users
   - File: `drive_analytics_daily_YYYY-MM-DD.json`

2. **Personal Activity Snapshot**
   - Query Drive API for files you own/have access to
   - Query Drive Activity API for activity on those files
   - Store: Your activity summary, documents you engaged with
   - File: `drive_analytics_personal_YYYY-MM-DD.json`

3. **Comments Check**
   - Query Drive API for files you have access to
   - Fetch comments from each file
   - Parse for @mentions of your email
   - Store: Comments mentioning you
   - File: `drive_analytics_mentions_YYYY-MM-DD.json`

#### Weekly Aggregation (Sunday 6:00 AM ET)
- Calculate 7-day, 10-day, 50-day running averages
- Update top lists
- File: `drive_analytics_weekly_YYYY-MM-DD.json`

### Memory Storage Structure

#### Daily Logs (5000 char limit each)
```
drive_analytics_daily_2025-11-16.json:
{
  "date": "2025-11-16",
  "is_workday": true,
  "summary": {
    "total_activities": 31385,
    "unique_users": 108,
    "unique_documents": 20861
  },
  "top_activity_types": [
    {"type": "change_user_access", "count": 21063},
    {"type": "edit", "count": 2867},
    ...
  ],
  "top_five": {
    "most_edited": [
      {"doc_id": "...", "title": "...", "edit_count": 290, "owner": "...", "link": "..."},
      ...
    ],
    "most_shared": [
      {"doc_id": "...", "title": "...", "share_count": 33, "owner": "...", "link": "..."},
      ...
    ],
    "most_commented": [
      {"doc_id": "...", "title": "...", "comment_count": 45, "owner": "...", "link": "..."},
      ...
    ],
    "most_viewed": [
      {"doc_id": "...", "title": "...", "view_count": 234, "owner": "...", "link": "..."},
      ...
    ],
    "most_active_users": [
      {"email": "...", "activity_count": 19386},
      ...
    ]
  }
}
```

#### Personal Activity Log
```
drive_analytics_personal_2025-11-16.json:
{
  "date": "2025-11-16",
  "is_workday": true,
  "my_activity": {
    "total_activities": 1091,
    "total_edits": 450,
    "total_views": 641,
    "documents_engaged": 45,
    "top_documents": [
      {
        "doc_id": "...",
        "title": "...",
        "link": "https://docs.google.com/...",
        "edit_count": 250,
        "view_count": 40,
        "total_engagement": 290,
        "owner": "...",
        "summary": null  // Stub for future implementation
      },
      ...
    ],
    "activity_patterns": {
      "viewed_then_stopped": [
        {"doc_id": "...", "title": "...", "last_view_date": "2025-11-10", "view_count_before_stop": 15}
      ],
      "began_editing_recently": [
        {"doc_id": "...", "title": "...", "first_edit_date": "2025-11-14", "edit_count": 5}
      ],
      "started_editing_then_stopped": [
        {"doc_id": "...", "title": "...", "last_edit_date": "2025-11-12", "edit_count_before_stop": 8}
      ],
      "view_most_regularly": [
        {"doc_id": "...", "title": "...", "days_with_views": 8, "total_views": 25}
      ],
      "multiple_views_per_day": [
        {"doc_id": "...", "title": "...", "date": "2025-11-16", "view_count": 5}
      ]
    }
  }
}
```

#### Mentions Log
```
drive_analytics_mentions_2025-11-16.json:
{
  "date": "2025-11-16",
  "mentions": [
    {
      "comment_id": "...",
      "file_id": "...",
      "file_title": "...",
      "file_link": "https://docs.google.com/...",
      "author": "...",
      "text": "...",
      "created_time": "2025-11-16T14:23:45.123Z",
      "modified_time": "2025-11-16T14:23:45.123Z",
      "detected_at": "2025-11-16T06:15:30.000Z",  // When script detected the mention
      "is_new": true  // Whether this is a new mention since last check
    },
    ...
  ]
}
```

#### Running Averages (Updated Weekly)
```
drive_analytics_averages.json:
{
  "last_updated": "2025-11-16",
  "workday_count": {
    "3_day": 3,
    "10_day": 10,
    "50_day": 50
  },
  "averages": {
    "3_day": {
      "total_activities": 28500,
      "by_type": {"edit": 2500, "view": 2000, "share": 1500, "comment": 300, ...},
      "top_five": {
        "most_edited": [...],
        "most_shared": [...],
        "most_commented": [...],
        "most_viewed": [...],
        "most_active_users": [...]
      }
    },
    "10_day": {
      "total_activities": 95000,
      "by_type": {...},
      "top_five": {...},
      "document_averages": {
        "doc_id_1": {
          "edit_avg": 12.5,
          "view_avg": 8.3,
          "share_avg": 2.1,
          "comment_avg": 1.5
        },
        ...
      }
    },
    "50_day": {...}
  }
}
```

### Custom Tools for Letta Agent

#### 1. `get_drive_analytics_summary`
- **Purpose**: Get overview of Drive activity
- **Parameters**: 
  - `period`: "today", "yesterday", "last_7_days", "last_10_days"
  - `scope`: "workspace", "personal"
- **Returns**: Summary statistics, top lists

#### 2. `get_drive_trends`
- **Purpose**: Compare current period with historical averages
- **Parameters**:
  - `metric`: "activity_type", "document", "user"
  - `comparison_period`: "3_day", "10_day", "50_day"
- **Returns**: Trends, upticks, downticks

#### 3. `get_my_drive_activity`
- **Purpose**: Get your personal Drive activity
- **Parameters**:
  - `days`: Number of days to look back
  - `include_links`: Boolean to include document links
- **Returns**: Your activity summary, top documents with links

#### 4. `get_drive_mentions`
- **Purpose**: Get comments that mention you
- **Parameters**:
  - `days`: Number of days to look back
  - `unread_only`: Boolean to filter unread mentions
- **Returns**: List of mentions with comment text and document links

#### 5. `get_document_activity`
- **Purpose**: Get activity for specific document(s)
- **Parameters**:
  - `doc_ids`: Array of document IDs
  - `days`: Number of days to analyze
- **Returns**: Activity summary for each document

### Scripts to Create

#### 1. `collect_daily_workspace_activity.js`
- **Schedule**: Daily 6:00 AM ET
- **Purpose**: Collect workspace-wide activity for previous day
- **Output**: Updates `drive_analytics_daily_YYYY-MM-DD.json` in agent memory

#### 2. `collect_daily_personal_activity.js`
- **Schedule**: Daily 6:00 AM ET
- **Purpose**: Collect your personal activity for previous day
- **Output**: Updates `drive_analytics_personal_YYYY-MM-DD.json` in agent memory

#### 3. `collect_daily_mentions.js`
- **Schedule**: Daily 6:00 AM ET (or more frequently)
- **Purpose**: Check for new comments mentioning you
- **Output**: Updates `drive_analytics_mentions_YYYY-MM-DD.json` in agent memory

#### 4. `calculate_running_averages.js`
- **Schedule**: Weekly Sunday 6:00 AM ET
- **Purpose**: Calculate and update running averages
- **Output**: Updates `drive_analytics_averages.json` in agent memory

#### 5. `generate_trend_report.js`
- **Schedule**: On-demand or daily
- **Purpose**: Generate trend analysis comparing recent activity to averages
- **Output**: Text report for agent to present

## Requirements & Clarifications

### 1. Workday Definition
- **Definition**: Monday-Friday only (exclude weekends and holidays)
- **Implementation**: Filter dates to exclude weekends when calculating "past ten workdays"

### 2. "Top Five" Categories
- **Definition**: Five separate top-five lists:
  - **a) Most Edited Documents**: Documents with highest edit count
  - **b) Most Shared Documents**: Documents with highest permission/access change count
  - **c) Most Commented Documents**: Documents with highest comment activity
  - **d) Most Viewed Documents**: Documents with highest view count
  - **e) Most Active Users**: Users with highest total activity count
- **Implementation**: Generate separate rankings for each category

### 3. Declining Documents
- **Definition**: Documents that have decreased the most in categories a-d compared to:
  - Running average for that document over past N days, OR
  - Previous period comparison
- **Goal**: Identify documents where activity has notably dropped off
- **Implementation**: Calculate percentage decrease vs. historical average, rank by magnitude

### 4. Personal Engagement Definition
- **Definition**: Includes both **edits** and **views** for your personal activity
- **Implementation**: Count both edit and view events when calculating your engagement

### 5. @Mention Detection
- **Definition**: Google-qualified @-mentions containing `cdorsey@concord.org`
- **Implementation**: 
  - Fetch all comments, parse for @mentions
  - Match against email address
  - May need to parse sample comments to understand Google's mention format
- **Note**: Will need to test with actual comment samples to confirm format

### 6. Document Summaries
- **Status**: TBD - Create stubs for now
- **Implementation**: 
  - Add `summary` field to document data structures (initially null)
  - Create placeholder function `generate_document_summary(doc_id)`
  - Discuss implementation approach as system develops

### 7. Personal Activity Change Detection
- **Definition**: Track specific patterns in your activity:
  - **Documents you viewed a lot then stopped**: High view count → zero views
  - **Documents you began editing recently**: New edit activity after period of no edits
  - **Documents you started editing then stopped**: Edit activity → no edits
  - **Documents you view most regularly**: Consistent daily view patterns
  - **Documents you view multiple times per day**: Multiple views within same day
- **Implementation**: 
  - Track activity patterns over time windows
  - Compare current period to previous periods
  - Identify transitions (start/stop patterns)

## Revised Suggestions Based on Requirements

### 1. Activity Type Filtering (ENHANCED)
- **Enhancement**: Filter out noise events (`sync_item_content`, `prefetch_item_content`) from top lists
- **Benefit**: Focus on meaningful user actions in top-five rankings
- **Implementation**: Apply filtering when generating top-five lists, but keep all data for trend analysis

### 2. Workday-Aware Aggregations (NEW)
- **Enhancement**: All "past N workdays" calculations should properly exclude weekends
- **Benefit**: Accurate workday-based comparisons
- **Implementation**: Date filtering function that skips weekends when counting workdays

### 3. Declining Documents Algorithm (ENHANCED)
- **Enhancement**: Calculate decline for each category (edited, shared, commented, viewed) separately
- **Benefit**: Identify documents declining in specific activity types
- **Implementation**: 
  - Compare current period activity to running average per document
  - Calculate percentage decrease for each category
  - Rank by magnitude of decrease
  - Surface top decliners per category

### 4. Personal Activity Pattern Detection (NEW)
- **Enhancement**: Implement the five specific patterns you identified:
  - Viewed a lot then stopped
  - Began editing recently
  - Started editing then stopped
  - View most regularly
  - Multiple views per day
- **Benefit**: Surface actionable insights about your work patterns
- **Implementation**: 
  - Track activity over rolling windows
  - Detect transitions (activity → no activity, no activity → activity)
  - Calculate consistency metrics for "regular" patterns

### 5. Comment Activity Tracking (ENHANCED)
- **Enhancement**: Track comment counts per document (not just mentions)
- **Benefit**: Enable "most commented" top-five list
- **Implementation**: 
  - Count `create_comment` events per document
  - Aggregate daily comment activity
  - Include in top-five calculations

### 6. Document Summary Stubs (NEW)
- **Enhancement**: Create placeholder infrastructure for future summarization
- **Benefit**: Easy to add summarization later without refactoring
- **Implementation**: 
  - Add `summary` field to document data structures (null initially)
  - Create `generate_document_summary(doc_id)` function stub
  - Document interface for future LLM integration

### 7. Multi-Period Comparison (ENHANCED)
- **Enhancement**: Compare current day's top-fives with 3-day, 10-day, and 50-day averages
- **Benefit**: Context-aware insights showing what's unusual
- **Implementation**: 
  - Calculate running averages for each top-five category
  - Compare current values to averages
  - Highlight significant deviations

### 8. Document Link Generation (ENHANCED)
- **Enhancement**: Always include shareable links for documents shared with you
- **Benefit**: Quick access to relevant documents
- **Implementation**: 
  - Use Drive API to generate shareable links
  - Include in all document data structures
  - Filter to only include links for documents you have access to

### 9. Activity Type Breakdown for Personal Activity (NEW)
- **Enhancement**: Separate edit and view counts for your personal activity
- **Benefit**: Understand your engagement patterns (reading vs. writing)
- **Implementation**: Track edit_count and view_count separately in personal activity logs

### 10. Historical Top Lists (NEW)
- **Enhancement**: Maintain running list of "top tens for past ten workdays"
- **Benefit**: See trends over time, not just current snapshot
- **Implementation**: 
  - Store top-ten lists for each workday
  - Aggregate over rolling 10-workday window
  - Update daily, maintain historical records

## Technical Considerations

### Memory Management
- **Challenge**: 5000 char limit per memory file
- **Solution**: 
  - Store only essential data (IDs, counts, summaries)
  - Use multiple files for different data types
  - Archive old data periodically

### API Rate Limits
- **Challenge**: Google APIs have rate limits
- **Solution**:
  - Batch requests efficiently
  - Use pagination properly
  - Add delays between requests
  - Cache results when possible

### Data Freshness
- **Challenge**: Admin Reports API has lag (up to 24-48 hours for some events)
- **Solution**:
  - Use Drive Activity API for real-time per-file data
  - Use Admin Reports API for historical/aggregate data
  - Note lag in reports

### Performance
- **Challenge**: Processing 30K+ activities daily
- **Solution**:
  - Process in batches
  - Use efficient data structures
  - Store pre-aggregated summaries
  - Only store what's needed for analytics

## Integration with Letta Scheduling & Memory

### Architecture Overview

The system uses a **tool-based approach**:
- **Custom Letta Tools**: Python functions that query Google APIs and process data
- **Scheduled Reminders**: Trigger agent to run tools at specific times
- **Letta Agent**: Executes tools, stores results in memory blocks, performs intelligent analysis
- **On-Demand Access**: Tools can be called by agent or user at any time

### Scheduling & Execution Flow

#### 1. Daily Data Collection (6:00 AM ET, Monday-Friday)

**Scheduled Reminder** (via `schedule_reminder` tool):
- **When**: "every weekday at 6am"
- **Message**: "Run the Drive analytics collection tools for yesterday's workday. First, ensure memory blocks exist: for each block name (drive_analytics_workspace, drive_analytics_personal, drive_analytics_mentions), check if it exists using memory_read. If any block doesn't exist, create it with an empty JSON object {} using memory_create. Then call collect_daily_workspace_activity(), collect_daily_personal_activity(), and collect_daily_mentions(). For each tool result: 1) Read the corresponding consolidated memory block. 2) Parse the JSON (or use {} if empty). 3) Extract the date from the tool result (format: YYYY-MM-DD). 4) Add or update the entry: block_data[date] = parsed_tool_result. 5) Remove entries older than 50 days. 6) Use memory_replace to update the block with the merged JSON (formatted with indent=2)."
- **Agent ID**: Your agent ID (specified when scheduling)

**Agent Execution Flow**:
1. Agent receives reminder message
2. Agent calls `collect_daily_workspace_activity()` tool
   - Tool queries Admin Reports API for previous workday
   - Returns JSON with workspace activity data
3. Agent calls `collect_daily_personal_activity()` tool
   - Tool queries Drive API + Drive Activity API
   - Returns JSON with personal activity data
4. Agent calls `collect_daily_mentions()` tool
   - Tool queries Drive API for comments
   - Returns JSON with mentions data
5. For each tool result:
   - Agent reads the corresponding consolidated memory block (or creates it if missing)
   - Agent parses the existing JSON (or starts with `{}`)
   - Agent extracts the date from the tool result
   - Agent merges: `block_data[date] = tool_result_data`
   - Agent removes entries older than 50 days
   - Agent uses `memory_replace` to update the block with merged JSON
6. Agent updates running averages if needed

#### 2. Weekly Aggregation (Sunday 6:00 AM ET)

**Scheduled Reminder**:
- **When**: "every Sunday at 6am"
- **Message**: "Calculate running averages for Drive analytics. Call calculate_running_averages() which will read historical data from memory blocks and calculate 3-day, 10-day, and 50-day averages. Store the results in the drive_analytics_averages memory block using memory_replace."
- **Agent ID**: Your agent ID

**Agent Execution Flow**:
1. Agent receives reminder message
2. Agent calls `calculate_running_averages()` tool
   - Tool reads historical daily logs from memory blocks (via Letta API)
   - Calculates averages
   - Returns JSON with averages
3. Agent uses `memory_replace` to update `drive_analytics_averages` memory block

#### 3. On-Demand Analysis (Triggered by User/Agent)

**Custom Tools** (available anytime):
- `collect_daily_workspace_activity()` - Collect workspace activity for any date range
- `collect_daily_personal_activity()` - Collect personal activity for any date range
- `collect_daily_mentions()` - Check for mentions (can run more frequently)
- `get_drive_analytics_summary()` - Read from memory blocks, generate summary
- `get_drive_trends()` - Compare current data to averages
- `get_my_drive_activity()` - Get personal activity with links
- `get_drive_mentions()` - Get mentions from memory
- `get_document_activity()` - Query specific documents
- `get_top_documents()` - Get top documents by category with links
- `get_recent_my_activity()` - Get documents you've viewed/edited recently with links

### Memory Storage Strategy

#### Option A: Memory Blocks (Recommended for Daily Logs)
- **Type**: Memory blocks (editable, in-context)
- **Size**: ~5000 chars per block (within 50k limit)
- **Structure**: One memory block per day
  - `drive_analytics_daily_2025-11-16` (workspace activity)
  - `drive_analytics_personal_2025-11-16` (personal activity)
  - `drive_analytics_mentions_2025-11-16` (mentions)
- **Access**: Agent can read/write via `memory_replace`, `memory_insert`
- **Retention**: Keep last 60 workdays (~12 weeks)

#### Option B: Files (For Historical Data)
- **Type**: Files (read-only, searchable)
- **Size**: Can be larger (5MB limit)
- **Structure**: One file per week containing all daily logs
  - `drive_analytics_week_2025-11-10_to_2025-11-16.json`
- **Access**: Agent can search via `semantic_search`, `grep`
- **Retention**: Keep all historical data

#### Option C: Hybrid Approach (Recommended)
- **Recent data (last 10 workdays)**: Memory blocks for fast access
- **Historical data (older)**: Files for long-term storage
- **Running averages**: Single memory block (updated weekly)

### Division of Labor: Tools vs Agent

#### Tools Handle (Heavy Computation):
1. **API Queries**: All Google API calls (Admin Reports, Drive Activity, Drive API)
2. **Data Aggregation**: Counting activities, grouping by document/user
3. **Pattern Detection**: Identifying activity patterns (viewed then stopped, etc.)
4. **Top-Five Calculations**: Ranking documents/users by activity type
5. **Declining Document Detection**: Comparing current vs. historical averages
6. **Workday Filtering**: Excluding weekends from calculations
7. **Comment Parsing**: Extracting @mentions from comment text
8. **Link Generation**: Creating shareable Drive links

#### Agent Handles (Intelligent Analysis):
1. **Tool Execution**: Calling tools when needed (scheduled or on-demand)
2. **Data Storage**: Using `memory_replace`/`memory_insert` to store tool results
3. **Trend Interpretation**: Understanding what trends mean
4. **Context-Aware Insights**: Connecting patterns to user's work
5. **Natural Language Reports**: Generating readable summaries from stored data
6. **Query Processing**: Answering user questions about analytics
7. **Summary Generation**: (Future) Creating document summaries

### Tool Output Format

Tools return JSON strings that agent can parse and store:

```python
def collect_daily_workspace_activity(date: str = None) -> str:
    """
    Collect workspace-wide Drive activity for a specific date.
    
    Args:
        date: Date in YYYY-MM-DD format. Defaults to yesterday if not provided.
    
    Returns:
        str: JSON string with workspace activity data
    """
    # ... API queries and processing ...
    return json.dumps({
        "type": "drive_analytics_daily",
        "date": "2025-11-16",
        "is_workday": True,
        "data": {
            # Full daily log structure
        }
    }, indent=2)
```

Agent receives JSON string, parses it, and stores in memory blocks.

### Agent Memory Block Structure

**Consolidated Memory Blocks** (to avoid clutter from per-date blocks):
- `drive_analytics_workspace` - JSON object with date-indexed workspace activity entries
- `drive_analytics_personal` - JSON object with date-indexed personal activity entries
- `drive_analytics_mentions` - JSON object with date-indexed mentions entries
- `drive_analytics_averages` - Running averages and trends (updated weekly)
- `drive_analytics_config` - Configuration (thresholds, your email, etc.)

**Memory Block Format**:
Each consolidated block contains JSON with date keys:
```json
{
  "2025-11-13": {
    "type": "drive_analytics_daily",
    "date": "2025-11-13",
    "summary": {...},
    "top_five": {...}
  },
  "2025-11-14": {
    "type": "drive_analytics_daily",
    "date": "2025-11-14",
    "summary": {...},
    "top_five": {...}
  }
}
```

This approach:
- Keeps memory block count low (4-5 blocks total)
- Allows easy date-based queries
- Automatically manages old data (keep last 50 days)
- Prevents memory block clutter

### Scheduling Setup (Using Letta Tools)

Instead of scheduler-service JSON files, use the `schedule_reminder` tool directly:

#### Daily Collection Reminder

**Initial Setup** (run once via Letta agent or script):
```python
# Agent calls schedule_reminder tool
schedule_reminder(
    title="Daily Drive Analytics Collection",
    message=(
        "Run the Drive analytics collection tools for yesterday's workday. "
        "Call collect_daily_workspace_activity(), collect_daily_personal_activity(), "
        "and collect_daily_mentions(). For each tool result: "
        "1) First, check if the corresponding consolidated memory block exists "
        "(drive_analytics_workspace, drive_analytics_personal, or drive_analytics_mentions) "
        "using memory_read. If it doesn't exist, create it with an empty JSON object {} "
        "using memory_create. Then read the block. "
        "2) Parse the existing JSON. "
        "3) Extract the date from the tool result (format: YYYY-MM-DD). "
        "4) Add or update the entry: block_data[date] = parsed_tool_result. "
        "5) Remove entries older than 50 days. "
        "6) Use memory_replace to update the block with the merged JSON (formatted with indent=2)."
    ),
    when="every weekday at 6am",
    agent_id="your-agent-id",  # Or omit to default to current agent
    category="drive_analytics",
    timezone="America/New_York"
)
```

#### Weekly Aggregation Reminder

```python
schedule_reminder(
    title="Weekly Drive Analytics Aggregation",
    message=(
        "Calculate running averages for Drive analytics. Read the drive_analytics_workspace "
        "and drive_analytics_personal memory blocks. Extract entries for the past 50 workdays. "
        "Calculate 3-day, 10-day, and 50-day running averages for each metric. Store the results "
        "in the drive_analytics_averages memory block using memory_replace. If the block doesn't "
        "exist, create it first using memory_create."
    ),
    when="every Sunday at 6am",
    agent_id="your-agent-id",
    category="drive_analytics",
    timezone="America/New_York"
)
```

#### More Frequent Mentions Check (Optional)

For documents being actively edited, check mentions more frequently:

```python
schedule_reminder(
    title="Check Drive Mentions",
    message=(
        "Check for new Drive comments mentioning you. Call collect_daily_mentions(). "
        "Read the drive_analytics_mentions memory block (or create it if missing). "
        "Parse the JSON, extract the date from the tool result, add/update the entry for that date, "
        "remove entries older than 50 days, and use memory_replace to update the block. "
        "Also check if any documents you own or have been editing recently have new comments."
    ),
    when="every 2 hours",
    agent_id="your-agent-id",
    category="drive_analytics_mentions",
    timezone="America/New_York"
)
```

### Agent-Side Processing Flow

When agent receives scheduled reminder:

1. **Parse Reminder**: Understand what tools to call and what to do with results
2. **Call Tools**: Execute the specified tools (e.g., `collect_daily_workspace_activity()`)
3. **Receive JSON**: Tools return JSON strings with data
4. **Parse JSON**: Extract data type and content from tool output
5. **Determine Storage**: Choose memory block name based on date and data type
6. **Store Data**: Use `memory_replace` or `memory_insert` to update memory blocks
7. **Update Averages**: If applicable, update running averages
8. **Archive Old Data**: Move data older than 10 workdays to files (if needed)
9. **Generate Summary**: (Optional) Create brief summary of notable changes

### Tool Architecture

Tools are Python functions that:
- Accept parameters (dates, filters, etc.)
- Query Google APIs
- Process and aggregate data
- Return JSON strings

Example tool structure:
```python
def collect_daily_workspace_activity(date: str = None) -> str:
    """
    Collect workspace-wide Drive activity for a specific date.
    
    Queries Admin Reports API for all Drive activity on the specified date,
    aggregates by activity type, document, and user, and returns top-five lists.
    
    Args:
        date: Date in YYYY-MM-DD format. Defaults to yesterday if not provided.
              If yesterday is a weekend, uses last workday.
    
    Returns:
        str: JSON string containing:
        {
            "type": "drive_analytics_daily",
            "date": "2025-11-16",
            "is_workday": true,
            "summary": {...},
            "top_five": {
                "most_edited": [...],
                "most_shared": [...],
                "most_commented": [...],
                "most_viewed": [...],
                "most_active_users": [...]
            }
        }
    """
    # Implementation: API queries, processing, return JSON
```

Tools are registered with Letta using:
```python
from letta import Letta

client = Letta(base_url="http://letta:8283")
tool = client.tools.create_from_function(
    func=collect_daily_workspace_activity,
    tags=["drive", "analytics", "workspace"]
)
```

Then attached to agent:
```python
client.add_tool_to_agent(
    agent_id="your-agent-id",
    tool_id=tool.id
)
```

### Custom Tools for Agent

#### Data Collection Tools (Called by Scheduled Reminders)

1. **`collect_daily_workspace_activity(date: str = None) -> str`**
   - Collects workspace-wide activity for a date
   - Returns JSON with top-five lists and summary
   - Called daily via scheduled reminder

2. **`collect_daily_personal_activity(date: str = None) -> str`**
   - Collects your personal activity for a date
   - Returns JSON with your activity patterns and top documents
   - Called daily via scheduled reminder

3. **`collect_daily_mentions(date: str = None) -> str`**
   - Checks for comments mentioning you
   - Returns JSON with mention details and timestamps
   - Called daily (or more frequently) via scheduled reminder

4. **`calculate_running_averages() -> str`**
   - Reads historical data from memory blocks
   - Calculates 3-day, 10-day, 50-day averages
   - Returns JSON with averages
   - Called weekly via scheduled reminder

#### Query Tools (Called On-Demand)

5. **`get_drive_analytics_summary(period: str, scope: str = "workspace") -> str`**
   - Reads from memory blocks
   - Returns summary for specified period
   - Parameters: `period` (today|yesterday|last_7_workdays|last_10_workdays), `scope` (workspace|personal)

6. **`get_drive_trends(metric: str, comparison_period: str = "10_day") -> str`**
   - Compares current data to historical averages
   - Returns trends, upticks, downticks
   - Parameters: `metric` (activity_type|document|user), `comparison_period` (3_day|10_day|50_day)

7. **`get_my_drive_activity(days: int = 7, include_links: bool = True) -> str`**
   - Gets your personal activity with document links
   - Returns JSON with documents you've engaged with
   - Parameters: `days` (workdays to look back), `include_links` (include Drive links)

8. **`get_drive_mentions(days: int = 7, unread_only: bool = False) -> str`**
   - Gets comments mentioning you from memory
   - Returns JSON with mention details and links
   - Parameters: `days` (days to look back), `unread_only` (filter unread)

9. **`get_document_activity(doc_ids: list[str], days: int = 7) -> str`**
   - Gets activity for specific documents
   - Returns JSON with activity details
   - Parameters: `doc_ids` (list of document IDs), `days` (lookback period)

10. **`get_top_documents(category: str, count: int = 5, include_links: bool = True) -> str`**
    - Gets top documents by category with links
    - Returns JSON with top documents
    - Parameters: `category` (edited|shared|commented|viewed), `count` (number to return), `include_links` (include Drive links)

11. **`get_recent_my_activity(activity_type: str = "all", days: int = 3, include_links: bool = True) -> str`**
    - Gets documents you've viewed/edited recently with links
    - Useful for quick access to active documents
    - Parameters: `activity_type` (edit|view|all), `days` (workdays), `include_links` (include Drive links)

### Execution Timeline

**Daily (6:00 AM ET, Mon-Fri)**:
- 6:00:00 - Reminder sent to agent
- 6:00:01 - Agent calls `collect_daily_workspace_activity()` (~30-60s)
- 6:01:00 - Agent calls `collect_daily_personal_activity()` (~10-20s)
- 6:01:20 - Agent calls `collect_daily_mentions()` (~5-10s)
- 6:01:30 - Agent stores data in memory blocks (~5s)
- **Total**: ~2 minutes

**Weekly (6:00 AM ET, Sunday)**:
- 6:00:00 - Reminder sent to agent
- 6:00:01 - Agent calls `calculate_running_averages()` (~10-20s)
- 6:00:20 - Agent updates averages memory block (~5s)
- **Total**: ~30 seconds

**On-Demand (User/Agent triggered)**:
- Agent calls query tools (e.g., `get_top_documents()`, `get_recent_my_activity()`)
- Tools read from memory blocks or query APIs directly
- Response time: < 1 second (memory blocks) or 5-30 seconds (API queries)

## Next Steps

1. **Create Tool Functions**: Implement Python functions for Drive analytics tools
2. **Register Tools**: Register tools with Letta using `client.tools.create_from_function()`
3. **Attach to Agent**: Add tools to your agent using `client.add_tool_to_agent()`
4. **Set Up Scheduling**: Use `schedule_reminder` tool to create daily/weekly reminders
5. **Configure Agent Memory**: Set up initial memory blocks (can be done by agent)
6. **Test Integration**: Run tools manually, then test scheduled reminders
7. **Iterate**: Refine based on usage

## Tool Implementation Files

Create the following files:

1. **`letta/drive_analytics_tools.py`**: All tool function definitions
2. **`letta/register_drive_analytics_tools.py`**: Script to register tools with Letta
3. **`letta/attach_drive_analytics_to_agent.py`**: Script to attach tools to agent

Follow the pattern established in `letta/slack_analytics_tools.py` and related files.

