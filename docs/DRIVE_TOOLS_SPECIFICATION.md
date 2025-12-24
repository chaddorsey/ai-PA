# Google Drive Tools Specification

This document describes the consolidated Drive tools for Letta agents.

## Tool Summary

| Tool | Purpose | Key Use Cases |
|------|---------|---------------|
| `search_drive_activity` | Activity search | "What did X work on?", "Who edited Y?" |
| `get_drive_documents` | Document discovery | Find files by owner, name, type |

## search_drive_activity

Unified activity search with flexible filtering.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user` | str | None | Actor filter (who did action). Email or comma-separated list. |
| `owner` | str | None | Document owner filter. Email or comma-separated list. |
| `start_date` | str | 7 days ago | Start date (YYYY-MM-DD) |
| `end_date` | str | today | End date (YYYY-MM-DD) |
| `activity_type` | str | "all" | Filter: "edit", "view", "share", "comment", "all" |
| `count` | int | 50 | Max documents (max 200) |
| `sort_by` | str | "recent" | Sort: "recent", "edit_count", "view_count", "name" |

### Examples

```python
# What did Jie and Rebecca work on Monday?
search_drive_activity(
    user="jie@company.com,rebecca@company.com",
    start_date="2024-12-23",
    end_date="2024-12-23"
)

# What did Cynthia edit the most last week?
search_drive_activity(
    user="cynthia@company.com",
    activity_type="edit",
    start_date="2024-12-16",
    end_date="2024-12-20",
    sort_by="edit_count"
)

# Documents owned by Leslie that were viewed last month
search_drive_activity(
    owner="leslie@company.com",
    activity_type="view",
    start_date="2024-11-01",
    end_date="2024-11-30",
    sort_by="view_count"
)
```

### Response Structure

```json
{
  "status": "ok",
  "data": {
    "query": { ... },
    "total_documents": 38,
    "total_activities": 189,
    "documents": [
      {
        "doc_id": "...",
        "title": "Document Name",
        "owner": "user@company.com",
        "edit_count": 15,
        "view_count": 8,
        "share_count": 2,
        "comment_count": 3,
        "total_activity": 28,
        "actors": ["user1@", "user2@"],
        "actor_count": 2,
        "last_activity": "2024-12-23T14:30:00Z",
        "link": "https://docs.google.com/...",
        "is_accessible": true
      }
    ]
  }
}
```

## get_drive_documents

Document discovery and listing with flexible filters.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `owner` | str | None | Owner filter. **Full email required** (Drive API limitation). |
| `name` | str | None | Name search (partial match) |
| `file_type` | str | "all" | Type: "document", "spreadsheet", "presentation", "pdf", "folder", "image", "all" |
| `folder` | str | None | Folder ID to scope search |
| `modified_after` | str | None | Only files modified after date (YYYY-MM-DD) |
| `shared_only` | bool | False | Only shared documents |
| `count` | int | 50 | Max documents (max 200) |

### Examples

```python
# Documents owned by Leslie
get_drive_documents(owner="leslie@company.com")

# Spreadsheets with "budget" in name
get_drive_documents(name="budget", file_type="spreadsheet")

# Recently modified documents
get_drive_documents(modified_after="2024-12-01")

# Shared presentations
get_drive_documents(file_type="presentation", shared_only=True)
```

### Response Structure

```json
{
  "status": "ok",
  "data": {
    "query": { ... },
    "total_documents": 10,
    "documents": [
      {
        "id": "file-id",
        "name": "Document Name",
        "type": "document",
        "link": "https://docs.google.com/...",
        "owner": "user@company.com",
        "modified": "2024-12-23T14:30:00Z",
        "created": "2024-12-01T10:00:00Z",
        "shared": true,
        "size": "1024"
      }
    ]
  }
}
```

## Preserved Existing Tools

These existing tools remain available:

| Tool | Purpose |
|------|---------|
| `get_drive_file_info` | Get metadata for single file from URL |
| `get_drive_mentions` | Get @-mentions from memory blocks |
| `get_drive_analytics_summary` | Get activity summary from memory blocks |
| `collect_daily_workspace_activity` | Collect workspace activity for a date |
| `collect_daily_personal_activity` | Collect personal activity for a date |
| `collect_daily_mentions` | Collect @-mentions for a date |

## Best Practices

1. **Use names, not IDs**: Provide email addresses directly (e.g., "cynthia@company.com")
2. **Partial emails work**: "cynthia@" matches "cynthia@company.com"
3. **Date format**: Always use YYYY-MM-DD
4. **Combine filters**: Multiple filters work together (AND logic)
5. **Sort strategically**: Use `sort_by="edit_count"` to find most-edited docs

## API Path Selection

| Query Type | API Used | Date Limit | View Counts |
|------------|----------|------------|-------------|
| Owner + view filter/sort | Admin Reports | 180 days | ✓ Accurate |
| Owner only (edits/comments) | Drive Activity | No limit | ✗ Not tracked |
| User queries | Admin Reports | 180 days | ✓ Accurate |

**Note**: Drive Activity API doesn't track views. Queries needing view data automatically use Admin Reports API.
