# Slack Custom Tools: Design Principles

## Core Principle: Tools Provide Raw Data, LLM Provides Intelligence

The tools we build should focus on **retrieving and structuring raw data** from Slack. The LLM will use this data to perform analysis, summarization, sentiment detection, and other intelligent operations.

## Design Philosophy

### What Tools Should Do

1. **Retrieve Data**
   - Get messages from channels
   - Search for messages matching criteria
   - Extract files and links
   - Retrieve user and channel information

2. **Structure Data**
   - Return well-formatted JSON
   - Include all relevant metadata
   - Provide complete context (channel, timestamp, user, etc.)
   - Include related data (threads with messages, files with messages)

3. **Enable Filtering**
   - Support precise queries (user, date, channel, keyword)
   - Allow combination of filters
   - Handle pagination efficiently

4. **Provide Access**
   - Generate permalinks
   - Return download URLs
   - Include all necessary identifiers

### What Tools Should NOT Do

1. **Analysis**
   - ❌ Sentiment analysis (LLM can do this from raw messages)
   - ❌ Topic extraction (LLM can identify topics from content)
   - ❌ Concern detection (LLM can analyze message tone/content)
   - ❌ Engagement scoring (can be derived from raw data if needed)

2. **Summarization**
   - ❌ Message summarization (LLM can summarize message lists)
   - ❌ Activity summarization (LLM can summarize activity data)
   - ❌ Channel summaries (LLM can summarize channel message lists)

3. **Intelligence**
   - ❌ Relevance ranking (LLM can prioritize from full data)
   - ❌ Prioritization logic (LLM can prioritize based on context)
   - ❌ Pattern detection (LLM can detect patterns from data)

### Optional: Usage Hints

Tools may optionally provide brief usage hints in their descriptions or return data:

- Tool docstrings can suggest how returned data might be used
- Response metadata could include brief usage notes
- **But**: Be careful not to overreach - let the LLM determine the best approach

Example of acceptable hint in tool description:
```python
"""
Returns: JSON with message list including text, user, timestamp, channel.
The LLM can use this data to summarize activity, analyze sentiment, 
or extract specific information based on the query context.
"""
```

Example of potentially overreaching (avoid):
```python
"""
Returns: Messages formatted for sentiment analysis.
Call analyze_sentiment() on the result to get sentiment scores.
"""
```

## Implications for Tool Design

### Tool Categories Should Focus On:

1. **Data Retrieval**
   - Getting messages (by channel, date, user, keyword)
   - Getting channel information
   - Getting user information
   - Getting thread replies

2. **Data Extraction**
   - Extracting files from messages
   - Extracting links from messages
   - Extracting metadata

3. **Data Access**
   - Generating permalinks
   - Providing download URLs
   - Returning identifiers

4. **Data Structuring**
   - Formatting data clearly
   - Including complete context
   - Grouping related data (threads, files with messages)

### Removed from Tool Scope:

- Summarization tools → LLM summarizes raw message lists
- Sentiment analysis tools → LLM analyzes message text
- Topic extraction tools → LLM extracts topics from content
- Prioritization tools → LLM prioritizes based on query context
- Engagement metrics tools → Can be calculated from raw data if needed (reactions, reply counts are in message objects)

## Tool Return Format Principles

### Always Include:
- **Complete context**: channel, timestamp, user, message ID
- **Related data**: thread replies with parent, files with message
- **Access information**: permalinks, download URLs
- **Raw content**: Full message text, file names, link URLs

### Structure for LLM Use:
- Clear JSON structure
- Descriptive field names
- Complete data (don't truncate unnecessarily)
- Grouped logically (threads together, files with messages)

### Example Good Tool Response:
```json
{
  "messages": [
    {
      "ts": "1234567890.123456",
      "text": "Full message text here...",
      "user": "U123456",
      "channel": "C123456",
      "channel_name": "#random",
      "permalink": "https://workspace.slack.com/archives/C123456/p1234567890123456",
      "datetime": "2024-12-19T14:30:00Z",
      "thread_ts": null,
      "replies": [
        {
          "ts": "1234567891.123456",
          "text": "Reply text...",
          "user": "U789012",
          "datetime": "2024-12-19T14:35:00Z"
        }
      ],
      "reactions": [
        {"name": "thumbsup", "count": 3, "users": ["U123", "U456"]}
      ],
      "files": [
        {
          "id": "F123456",
          "name": "document.pdf",
          "url_private_download": "https://files.slack.com/...",
          "mimetype": "application/pdf"
        }
      ],
      "links": [
        {"url": "https://example.com/doc", "text": "shared document"}
      ]
    }
  ],
  "metadata": {
    "total_count": 1,
    "date_range": {"start": "2024-12-19", "end": "2024-12-19"}
  }
}
```

This gives the LLM everything it needs to:
- Summarize the messages
- Analyze sentiment
- Extract topics
- Provide context
- Generate responses

## Use Case Re-Interpretation

Looking at our use cases, the tools should enable them by providing:

1. **"What's going on right now?"**
   - Tool: `get_recent_messages` (returns raw messages)
   - LLM: Summarizes and prioritizes from the data

2. **"What did Sue say about X?"**
   - Tool: `search_messages(user="Sue", keyword="X")` (returns raw messages)
   - LLM: Summarizes and quotes from the messages

3. **"Give me the doc Danielle shared"**
   - Tool: `search_messages(user="Danielle")` + `extract_files_from_messages()` (returns raw data)
   - LLM: Identifies the relevant file and provides context

4. **"What are people most concerned about?"**
   - Tool: `get_recent_messages()` (returns raw messages)
   - LLM: Analyzes sentiment and extracts concerns

5. **"What links did people share?"**
   - Tool: `extract_links_from_messages()` (returns raw links with metadata)
   - LLM: Formats and presents them

## Revised Tool Categories

### 1. Message Retrieval
- Get messages from channel (with filters)
- Get recent messages (time-based)
- Get message by ID/timestamp
- Get messages with threads

### 2. Search
- Search messages (user, keyword, date, channel filters - combinable)
- Search in specific channels
- Search across channel types

### 3. Channel Discovery
- List channels
- Get channel details
- Resolve channel names to IDs

### 4. File & Link Extraction
- Extract files from messages
- Extract links from messages
- List files (with filters)
- Get file metadata and URLs

### 5. User Information
- List users
- Get user details
- Get user's channels

### 6. Utilities
- Get message permalink
- Format timestamps
- Resolve identifiers

## What We Removed

- ❌ Summarization tools → LLM does this
- ❌ Sentiment analysis tools → LLM does this
- ❌ Topic extraction tools → LLM does this
- ❌ Engagement metrics tools → Raw data includes reactions/reply counts
- ❌ Activity pattern analysis → LLM can analyze timestamped data
- ❌ Prioritization tools → LLM prioritizes based on query

## What We Kept/Enhanced

- ✅ Raw data retrieval (messages, channels, users)
- ✅ Flexible search and filtering
- ✅ Complete context (metadata, threads, files, links)
- ✅ Access information (permalinks, download URLs)
- ✅ Well-structured JSON responses
- ✅ Clear documentation of what data is returned
