# Slack Custom Tools: Use Cases Analysis

This document analyzes real-world use cases to identify the core categories of monitoring and information extraction capabilities needed.

## Use Cases Breakdown

### 1. "What's going on in Slack right now?"
**Category: Real-Time Activity Monitoring**

**Requirements:**
- Recent message retrieval (last N minutes/hours)
- Channel prioritization (channels user is part of)
- User prioritization (people user interacts with frequently)
- Activity summarization
- Real-time or near-real-time data (not days-old)

**Tools Needed:**
- `get_recent_messages` (date range: now - N minutes)
- `get_user_channels` (to prioritize)
- `summarize_messages` (aggregation/summarization)

**Key Features:**
- Very recent timestamps (up to the minute)
- Prioritization/filtering logic
- Summarization capability

---

### 2. "What did Sue say about the new candidate?"
**Category: User-Specific Content Search**

**Requirements:**
- Search by specific user ("Sue")
- Search by topic/keyword ("new candidate")
- Search across multiple channel types (public, private, DMs, MPDMs)
- Retrieve direct quotes from messages
- Generate links to specific messages
- Relevance ranking (most recent, most relevant)

**Tools Needed:**
- `search_messages_by_user_and_topic` (user + keyword filter)
- `get_message_with_context` (full message text)
- `get_message_permalink` (deep links)

**Key Features:**
- Multi-channel search scope
- User filtering combined with content filtering
- Message retrieval with context
- Permalink generation

---

### 3. "Give me the doc Danielle shared for this meeting"
**Category: Contextual File/Link Retrieval**

**Requirements:**
- Search by user ("Danielle")
- Search by context ("this meeting" - requires date/time or meeting-related keywords)
- Identify file/link shared in messages
- Retrieve file URL (Google Doc link or download link)
- May require multi-step search (first find relevant messages, then extract files)

**Tools Needed:**
- `search_messages` (user + context/keywords + date range)
- `extract_files_from_messages` (file extraction)
- `extract_links_from_messages` (link extraction)
- `get_file_download_url` (if needed)

**Key Features:**
- Multi-step workflow support
- Context-aware search (meeting-related, date-based)
- File/link extraction from search results
- Google Docs link handling

---

### 4. "What other pictures of lace work has Hee-Sun shared in the past?"
**Category: User Content History with Type Filtering**

**Requirements:**
- Search by user ("Hee-Sun")
- Filter by content type (images/pictures)
- Filter by topic ("lace work", "lacemaking")
- Long time range (5-6 years)
- Retrieve links to posts
- Retrieve summaries of posts
- Handle file attachments and shared content

**Tools Needed:**
- `search_user_content` (user + content type + keyword + date range)
- `list_files_by_user` (with type and keyword filters)
- `get_message_summaries` (brief summaries)
- `extract_images_from_messages` (image-specific extraction)

**Key Features:**
- Long historical queries (years)
- Content type filtering (images, files, etc.)
- Topic/keyword matching in file context
- Image/file metadata extraction

---

### 5. "Dan said he mentioned Sina's report on Slack last week. Give me that post"
**Category: Precise Message Retrieval by User + Topic + Time**

**Requirements:**
- Search by user ("Dan")
- Search by topic ("Sina's report")
- Filter by time ("last week")
- Retrieve specific message text
- Include metadata (channel, timestamp)
- Generate deep link to message

**Tools Needed:**
- `search_messages` (user + keyword + date range)
- `get_message_details` (full message with metadata)
- `get_message_permalink` (deep link)

**Key Features:**
- Precise time range filtering
- User + topic combination
- Full message retrieval with metadata
- Permalink generation

---

### 6. "What's happening in Slack with the MoDa proposal?"
**Category: Complex Multi-Channel Topic Monitoring**

**Requirements:**
- Search by topic ("MoDa proposal")
- Search across multiple channel types (MPDMs, dedicated channels)
- Filter by users (proposal channel participants, grants management staff)
- Extract links to related documents
- Extract references to documents
- Summarize activity
- Provide message links

**Tools Needed:**
- `search_messages` (keyword/topic search)
- `search_in_channels` (channel-specific filtering)
- `filter_by_users` (user-based filtering)
- `extract_links_from_messages` (document links)
- `summarize_topic_activity` (activity summarization)
- `get_message_permalink` (links to messages)

**Key Features:**
- Multi-channel search
- User group filtering
- Link/document reference extraction
- Activity summarization
- Complex multi-step queries

---

### 7. "What are people posting about AI lately?"
**Category: Topic-Based Channel Discovery and Monitoring**

**Requirements:**
- Search by topic ("AI")
- Identify relevant channels (AI-focused topics or channel names)
- Summarize activity in those channels
- Recent time range ("lately")

**Tools Needed:**
- `search_messages` (topic/keyword)
- `list_channels_by_topic` (channel discovery by name/topic)
- `get_channel_summaries` (summarize channel activity)
- `summarize_topic_activity` (aggregate summaries)

**Key Features:**
- Topic-based channel discovery
- Channel metadata search (name, purpose)
- Multi-channel summarization
- Recent activity focus

---

### 8. "What are people most concerned about in Slack?"
**Category: Sentiment Analysis and Negative Content Detection**

**Requirements:**
- Sentiment analysis of messages
- Identify negative sentiment
- Filter by time range ("past N days")
- Summarize concerns/negative topics
- Potentially rank by concern level

**Tools Needed:**
- `get_recent_messages` (time range)
- `analyze_sentiment` (sentiment scoring)
- `filter_by_sentiment` (negative sentiment filter)
- `summarize_concerns` (topic extraction from negative content)

**Key Features:**
- Sentiment analysis (not native to Slack API - requires NLP)
- Topic extraction from sentiment-filtered content
- Time-based filtering
- Summarization of concerns

---

### 9. "What links did people share today/yesterday?"
**Category: Time-Filtered Link Extraction**

**Requirements:**
- Extract all links from messages
- Filter by date (today/yesterday)
- Format output (already specified formatting mode)
- Include link metadata (who shared, when, where)

**Tools Needed:**
- `get_recent_messages` (date range: today/yesterday)
- `extract_links_from_messages` (link extraction)
- `format_links_output` (formatting)

**Key Features:**
- Precise date filtering (single day)
- Link extraction from message text
- Metadata inclusion (user, timestamp, channel)
- Output formatting

---

### 10. "What files did people share this week?"
**Category: Time-Filtered File Extraction**

**Requirements:**
- List files shared in workspace
- Filter by time range ("this week")
- Extract file URLs (Google Docs, downloads)
- Include file metadata

**Tools Needed:**
- `list_files` (with date range filter)
- `get_file_metadata` (file details)
- `get_file_download_url` (file URLs)

**Key Features:**
- Time-based file filtering
- File metadata extraction
- Google Docs link handling
- Download URL generation

---

## Categories of Monitoring/Information Extraction

Based on these use cases, we can identify the following categories:

### Category 1: Real-Time Activity Monitoring
**Use Cases:** #1 (What's going on right now?)

**Core Capabilities:**
- Recent message retrieval (minutes/hours, not days)
- Prioritization (channels, users)
- Activity summarization
- Real-time data access

**Tools:**
- `get_recent_activity`
- `summarize_recent_activity`
- `get_user_channel_priorities`

---

### Category 2: User-Specific Search & Retrieval
**Use Cases:** #2 (What did Sue say?), #4 (Hee-Sun's lace work), #5 (Dan's mention)

**Core Capabilities:**
- Search messages by user
- Combine user filter with topic/keyword
- Multi-channel search scope
- Message retrieval with context
- Permalink generation

**Tools:**
- `search_messages_by_user`
- `get_user_message_history`
- `get_message_with_context`
- `get_message_permalink`

---

### Category 3: Topic-Based Discovery & Monitoring
**Use Cases:** #6 (MoDa proposal), #7 (AI posts)

**Core Capabilities:**
- Keyword/topic search
- Multi-channel search
- Channel discovery by topic
- Activity summarization
- User group filtering

**Tools:**
- `search_messages_by_topic`
- `search_in_channels`
- `discover_channels_by_topic`
- `summarize_topic_activity`
- `filter_by_user_groups`

---

### Category 4: Contextual File & Link Retrieval
**Use Cases:** #3 (Danielle's doc), #9 (links today), #10 (files this week)

**Core Capabilities:**
- File extraction from messages
- Link extraction from messages
- Time-based filtering
- Context-aware search (meeting, topic)
- Google Docs/Drive link handling
- File metadata extraction

**Tools:**
- `extract_files_from_messages`
- `extract_links_from_messages`
- `list_files_by_date`
- `list_links_by_date`
- `search_files_by_context`
- `get_file_download_url`

---

### Category 5: Content Type Filtering
**Use Cases:** #4 (pictures of lace work)

**Core Capabilities:**
- Filter by content type (images, files, links)
- Combine type filter with topic/user filters
- Long historical queries
- Content metadata extraction

**Tools:**
- `search_by_content_type`
- `list_files_by_type`
- `extract_images_from_messages`
- `get_content_metadata`

---

### Category 6: Sentiment & Concern Analysis
**Use Cases:** #8 (most concerned about)

**Core Capabilities:**
- Sentiment analysis (requires NLP/ML)
- Negative sentiment detection
- Topic extraction from sentiment-filtered content
- Concern summarization

**Tools:**
- `analyze_message_sentiment`
- `filter_by_sentiment`
- `summarize_concerns`
- `extract_topics_from_messages`

**Note:** This category requires additional capabilities beyond Slack API (NLP/sentiment analysis). May need to integrate with existing analysis tools or use external libraries.

---

### Category 7: Precise Message Retrieval
**Use Cases:** #5 (Dan's specific post)

**Core Capabilities:**
- Exact message retrieval
- Message metadata (channel, timestamp, user)
- Permalink generation
- Full message context

**Tools:**
- `get_message_by_id`
- `get_message_details`
- `get_message_permalink`
- `get_message_context`

---

## Refined Tool Categories

Based on this analysis, our tools should support:

### 1. **Message Retrieval Tools** (Raw Data)
- Get messages from channel (with date range, filters)
- Get recent messages (time-based)
- Get message by ID/timestamp
- Get messages with threads/replies (complete thread data)
- **Returns**: Full message text, metadata, thread replies, reactions, files, links

### 2. **Search Tools** (Raw Data)
- Search messages by keyword/topic (with filters)
- Search messages by user (with optional topic/keyword)
- Search messages with combined filters (user + topic + date + channel)
- Search within specific channels
- Search across channel types (public, private, DM, MPDM)
- **Returns**: Matching messages with complete context

### 3. **Channel Discovery Tools** (Raw Data)
- List all channels (with filters: type, archived, etc.)
- Get channel details (metadata, members, purpose)
- Resolve channel names to IDs
- Get user's channels
- **Returns**: Channel information and metadata

### 4. **File & Link Extraction Tools** (Raw Data)
- Extract files from messages (with metadata)
- Extract links from messages (with context)
- List files by date range (with filters)
- List links by date range (with filters)
- Get file metadata and download URLs
- **Returns**: Files/links with full context (who shared, when, where, message context)

### 5. **User Tools** (Raw Data)
- List users (with filters)
- Get user details (profile, status)
- Get user's channels
- **Returns**: User information and metadata

### 6. **Utility Tools**
- Get message permalink
- Get message context (surrounding messages)
- Format timestamps
- Resolve identifiers (names to IDs)
- **Returns**: Access information and formatted data

## Removed: Analysis & Summarization Tools

These are **NOT** tools - they're LLM capabilities using the raw data:

- ❌ **Summarization Tools** → LLM summarizes message lists returned by retrieval tools
- ❌ **Sentiment Analysis Tools** → LLM analyzes message text from retrieval tools
- ❌ **Topic Extraction Tools** → LLM extracts topics from message content
- ❌ **Engagement Metrics Tools** → Raw data includes reactions/reply counts; LLM can analyze
- ❌ **Activity Pattern Analysis** → LLM analyzes timestamped data from retrieval tools

### How Use Cases Are Enabled

**"What's going on right now?"**
- Tool: `get_recent_messages()` → Returns raw messages
- LLM: Summarizes and prioritizes from the data

**"What did Sue say about X?"**
- Tool: `search_messages(user="Sue", keyword="X")` → Returns raw messages
- LLM: Summarizes and quotes from the messages

**"What are people most concerned about?"**
- Tool: `get_recent_messages()` → Returns raw messages
- LLM: Analyzes sentiment and extracts concerns from message text

**"What links did people share?"**
- Tool: `extract_links_from_messages()` → Returns raw links with metadata
- LLM: Formats and presents them appropriately

## Key Insights

1. **Multi-Step Queries are Common**: Many use cases require multiple tool calls (search → filter → extract)

2. **Combination Filters are Essential**: User + topic, topic + date, user + date + content type

3. **Precise Time Filtering is Critical**: Single-day, week, "lately", "last week" - need flexible date handling

4. **Multi-Channel Scope is Important**: Many searches need to span public, private, DMs, MPDMs

5. **Complete Context is Essential**: Tools must return full message text, metadata, threads, files, links - LLM needs all data

6. **Link/File Extraction is Central**: Many queries end with file or link retrieval - tools must provide complete file/link metadata

7. **Raw Data is Sufficient**: Tools return well-structured raw data - LLM handles summarization, sentiment analysis, topic extraction

8. **Permalinks Enable Traceability**: Every message should include permalink for verification and sharing

## Recommended Tool Structure

Based on this analysis, we should design tools that:

1. **Support flexible filtering** (user, topic, date, channel, content type - alone or combined)
2. **Handle multi-step workflows** (search → filter → extract → format)
3. **Return complete raw data** (full message text, metadata, threads, files, links - LLM does analysis)
4. **Generate permalinks** (for every message retrieved)
5. **Extract structured data** (files, links, with complete metadata and context)
6. **Support precise time queries** (single day, week, custom ranges)
7. **Work across channel types** (public, private, DM, MPDM)
8. **Include complete context** (metadata, surrounding messages, channel info, user info, thread relationships)
