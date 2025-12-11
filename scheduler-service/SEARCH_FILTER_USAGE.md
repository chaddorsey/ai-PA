# Scheduler Search and Filtering Usage Guide

## Overview

The scheduler service now supports:
- **Filtering**: Filter jobs by status, category, or creator
- **Semantic Search**: Search jobs using natural language queries with vector embeddings

## REST API Usage

### Filter Jobs

```bash
# List all jobs
GET /v1/jobs

# Filter by status
GET /v1/jobs?status_filter=scheduled

# Filter by category
GET /v1/jobs?category_filter=backup

# Filter by creator
GET /v1/jobs?created_by_filter=letta-agent-123

# Combine filters
GET /v1/jobs?status_filter=scheduled&category_filter=automation&created_by_filter=letta-agent-123
```

### Semantic Search

```bash
# Basic search
GET /v1/jobs/search?query_text=backup tasks

# Search with filters
GET /v1/jobs/search?query_text=daily maintenance&category_filter=backup&limit=5&min_score=0.6

# Search with status filter
GET /v1/jobs/search?query_text=reminders&status_filter=scheduled&limit=10
```

### Parameters

**Search Parameters:**
- `query_text` (required): Natural language query
- `limit` (optional, default: 10): Max results (1-100)
- `min_score` (optional, default: 0.5): Minimum similarity (0.0-1.0)
- `status_filter` (optional): Filter by status
- `category_filter` (optional): Filter by category

**List Parameters:**
- `status_filter` (optional): scheduled|paused|cancelled|completed
- `category_filter` (optional): Category string
- `created_by_filter` (optional): Creator identifier

## MCP Tools for Letta

### scheduler_list_jobs

List jobs with optional filtering:

```python
# List all jobs
scheduler_list_jobs()

# Filter by status
scheduler_list_jobs(status_filter="scheduled")

# Filter by category
scheduler_list_jobs(category_filter="backup")

# Filter by creator
scheduler_list_jobs(created_by_filter="letta-agent-123")

# Combine filters
scheduler_list_jobs(
    status_filter="scheduled",
    category_filter="automation",
    created_by_filter="letta-agent-123"
)
```

### scheduler_search_jobs

Semantic search for jobs:

```python
# Basic search
scheduler_search_jobs(
    query_text="backup tasks",
    limit=10
)

# Search with filters
scheduler_search_jobs(
    query_text="daily maintenance reminders",
    limit=5,
    min_score=0.6,
    category_filter="backup",
    status_filter="scheduled"
)
```

## Examples for Letta Agents

### Find all backup jobs

```python
jobs = scheduler_search_jobs(
    query_text="backup",
    category_filter="backup"
)
```

### Find reminders from a specific agent

```python
jobs = scheduler_list_jobs(
    created_by_filter="letta-agent-123",
    category_filter="reminders"
)
```

### Search for maintenance tasks

```python
jobs = scheduler_search_jobs(
    query_text="system maintenance weekly cleanup",
    limit=20,
    min_score=0.5
)
```

## Testing

Run the test script to validate functionality:

```bash
cd scheduler-service
python test_search_filtering.py
```

The script tests:
1. List jobs with various filters
2. Semantic search functionality
3. MCP server health

**Note:** Semantic search requires the `sentence-transformers` package and embedding model to be available. If not configured, search will return a 503 error.

## Implementation Details

- **Embeddings**: Generated using `sentence-transformers/all-MiniLM-L6-v2`
- **Vector Search**: Uses pgvector cosine similarity (`<=>` operator)
- **Indexing**: `ivfflat` index on `vector_embedding` column for efficient search
- **Storage**: Embeddings stored when jobs are created/updated

## Troubleshooting

### Search returns 503 error
- Embedding model not available
- Ensure `sentence-transformers` package is installed
- Check that embedding service can load the model

### No search results
- Try lowering `min_score` (e.g., 0.3 instead of 0.5)
- Ensure jobs have embeddings (title + description)
- Verify query text matches job content semantically

### Filters not working
- Verify status values match exactly: `scheduled`, `paused`, `cancelled`, `completed`
- Category and created_by filters are case-sensitive
- Check that jobs have the specified category/creator values

