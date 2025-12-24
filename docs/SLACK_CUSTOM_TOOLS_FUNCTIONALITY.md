# Slack Custom Tools: Functionality Requirements

## Overview
This document outlines the functionality requirements for custom Slack tools focused on **monitoring, searching, and summarizing** Slack activity across the organization. These tools will be primarily for **reading** Slack data (not posting).

## Core Requirements (Already Identified)

### 1. Channel Discovery & Management
- ✅ **List all channels** (public, private, DMs, MPDMs)
- ✅ **Get channel details** (metadata, membership, purpose, topic)
- ✅ **Resolve channel names to IDs** (e.g., `#random` → `C1234567890`)
- ✅ **Channel membership lists** (who's in which channels)

### 2. Message History Retrieval
- ✅ **Get messages from a channel** with precise date range filtering
- ✅ **Get individual messages** by timestamp/channel
- ✅ **Get thread replies** (all replies in a thread)
- ✅ **Combine messages + replies** (properly structured threads)
- ✅ **Pagination support** for large date ranges

### 3. Search Capabilities
- ✅ **Workspace-wide search** (`search.messages`)
- ✅ **Channel-specific search**
- ✅ **Date range filtering** (exact dates, not just relative)
- ✅ **User filtering** (messages from specific users)
- ✅ **Keyword/content search**
- ✅ **Advanced query syntax** (if supported by Slack API)

### 4. File & Link Extraction
- ✅ **Extract files from messages** (all file attachments)
- ✅ **Extract links from messages** (URLs embedded in text)
- ✅ **Files from specific channels** (channel-scoped file lists)
- ✅ **Files from specific date ranges**
- ✅ **File metadata** (type, size, uploader, timestamp)
- ✅ **Download URLs** for files

## Additional Useful Functionality for Monitoring

### 5. User Information & Activity
**Slack API Methods: `users.list`, `users.info`, `users.profile.get`**

- **List workspace members**
  - All users in workspace
  - User IDs, names, emails, status
  - User roles (admin, owner, member, etc.)
  - User status (active, inactive, deactivated)

- **User profiles & status**
  - Display names, real names
  - Profile photos
  - Status/availability (away, active)
  - Custom status messages

- **User activity indicators**
  - Last activity timestamps
  - Online/offline status
  - Presence information

**Use Cases:**
- Identify key contributors in channels
- Monitor engagement levels
- Track who's active in which channels
- User directory queries

### 6. Message Reactions & Engagement
**Slack API Methods: `reactions.get`, `reactions.list`**

- **Get reactions on messages**
  - All emoji reactions
  - Who reacted (user IDs)
  - Reaction counts

- **Thread engagement metrics**
  - Reply counts
  - Unique participants
  - Thread length/depth

**Use Cases:**
- Identify highly-engaged content
- Track sentiment/feedback patterns
- Find popular discussions
- Measure message resonance

### 7. Channel Activity Metrics
**Derived from `conversations.history` and `conversations.info`**

- **Channel statistics**
  - Message frequency over time
  - Peak activity times
  - Most active users per channel
  - Thread density
  - Average thread length

- **Channel metadata**
  - Creation date
  - Member count
  - Purpose/topic
  - Archive status

**Use Cases:**
- Identify most active channels
- Find channels with declining engagement
- Discover peak discussion times
- Monitor channel health

### 8. Advanced Search & Filtering
**Slack API Methods: `search.messages`, `search.files`**

- **Cross-channel search**
  - Search all channels at once
  - Filter by channel name/ID
  - Filter by date range
  - Filter by user

- **File search**
  - Search files by name
  - Search files by content type
  - Search files by uploader
  - Search files by date range

- **Search result metadata**
  - Highlight matching text
  - Context around matches
  - Match relevance scoring

**Use Cases:**
- Find all mentions of a topic across workspace
- Locate files shared about specific subjects
- Track discussions about key topics
- Comprehensive content discovery

### 9. Link Extraction & Analysis
**Parse message text for URLs**

- **Extract all links from messages**
  - URLs in message text
  - Links in message blocks/attachments
  - Shared links/unfurled content

- **Link metadata**
  - Link destination
  - Link text/description
  - Who shared it
  - When it was shared
  - Which channel/thread

**Use Cases:**
- Track shared resources
- Monitor external link sharing
- Build knowledge base of shared links
- Find resources shared in conversations

### 10. Thread Analysis & Summarization
**Using `conversations.replies`**

- **Thread metrics**
  - Total replies
  - Unique participants
  - Thread duration (first to last reply)
  - Reply frequency

- **Thread structure**
  - Parent message
  - All replies in order
  - Reply relationships (if threaded)
  - Participant list

**Use Cases:**
- Summarize long discussions
- Extract decision points
- Track conversation flows
- Identify key contributors in threads

### 11. Date Range & Time-Based Queries
**Using `conversations.history` with `oldest`/`latest`**

- **Precise date filtering**
  - Exact date ranges (start date + end date)
  - Single day queries
  - Week/month/year ranges
  - Relative ranges (last N days)

- **Time-based analysis**
  - Messages per day/hour
  - Activity patterns over time
  - Trend analysis

**Use Cases:**
- "What happened on Dec 19 in #random?"
- "Show all messages from last week in #general"
- Activity trend analysis
- Historical audits

### 12. Message Permalinks & References
**Using `chat.getPermalink` (already have this)**

- **Generate message links**
  - Permanent URLs to messages
  - Shareable references
  - Works for channels, DMs, threads

**Use Cases:**
- Reference specific messages in reports
- Share message context
- Build message indexes

### 13. Conversation Context
**Using `conversations.info`**

- **Channel information**
  - Channel purpose and topic
  - Creation information
  - Member list
  - Privacy settings (public/private)

- **Channel history metadata**
  - Oldest message timestamp
  - Message count estimates
  - Archive status

**Use Cases:**
- Understand channel purpose
- Determine channel relevance
- Context for channel-specific queries

## Prioritization (Based on Use Case Analysis)

### Phase 1: Essential (Core Requirements)
**Supported Use Cases:** All 10 use cases require these

1. **List channels** (all types: public, private, DM, MPDM)
2. **Get message history with precise date filtering** (single day, week, custom ranges)
3. **Get thread replies** (complete thread context)
4. **Extract files from messages** (with metadata)
5. **Extract links from messages** (URLs, Google Docs)
6. **Workspace-wide search** (with filters: user, topic, date, channel)
7. **User information** (list users, get user details)
8. **Message retrieval** (by ID, with context, with metadata)
9. **Permalink generation** (for all retrieved messages)

### Phase 2: Important (Enhanced Monitoring)
**Supported Use Cases:** #1 (real-time), #6 (complex queries), #7 (channel discovery)

10. **Advanced search with combined filters** (user + topic, topic + date, etc.)
11. **Channel discovery by topic** (search channel names/purposes)
12. **Recent activity retrieval** (minutes/hours, not just days)
13. **Multi-channel summarization** (summarize activity across channels)
14. **Message prioritization** (by channel membership, user interactions)
15. **Content type filtering** (images, files, links)

### Phase 3: Nice to Have (Advanced Analytics)
**Supported Use Cases:** #8 (sentiment), future analytics needs

16. **Sentiment analysis** (requires NLP integration - not Slack API)
17. **Topic extraction** (from message content)
18. **Thread analysis and summarization**
19. **Link analysis and tracking**
20. **Time-based trend analysis**
21. **Engagement metrics** (reactions, reply counts)

## API Methods Reference

### Primary Methods We'll Use

| Method | Purpose | Priority |
|--------|---------|----------|
| `conversations.list` | List all channels | P1 |
| `conversations.info` | Get channel details | P1 |
| `conversations.history` | Get messages from channel | P1 |
| `conversations.replies` | Get thread replies | P1 |
| `search.messages` | Search workspace messages | P1 |
| `users.list` | List workspace members | P2 |
| `users.info` | Get user details | P2 |
| `reactions.get` | Get message reactions | P2 |
| `files.list` | List workspace files | P1 |
| `chat.getPermalink` | Generate message permalink | P2 |

### Considerations

1. **Rate Limits**: Slack API has rate limits. Need to handle gracefully.
2. **Pagination**: Many methods return paginated results. Need robust pagination handling.
3. **Token Scopes**: Ensure we have necessary OAuth scopes for all methods.
4. **Performance**: Some operations (like getting all thread replies) require multiple API calls. Need efficient batching.
5. **Caching**: Consider caching channel/user lists to reduce API calls.

## Tools We'll Build

Based on this analysis, we'll create custom tools that:

1. **Provide clean abstractions** over Slack API complexity
2. **Handle pagination automatically**
3. **Combine related API calls** (e.g., messages + thread replies)
4. **Support precise date filtering**
5. **Extract and structure data** (files, links, reactions)
6. **Return well-structured JSON** with complete context for LLM processing
7. **Include error handling** and rate limit management
8. **Support both channel names and IDs**
9. **Return raw data** - let the LLM handle analysis, summarization, and intelligence

### Design Philosophy

Tools focus on **retrieving and structuring raw data**. The LLM uses this data to:
- Perform sentiment analysis
- Generate summaries
- Extract topics
- Prioritize results
- Provide intelligent responses

Tools do NOT perform analysis, summarization, or intelligence operations - that's the LLM's job.
