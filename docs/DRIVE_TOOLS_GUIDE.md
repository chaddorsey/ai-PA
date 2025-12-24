# Drive Tools Guide

## search_drive_activity
Find activity: "What did X work on?", "Who edited Y?"

**Params:** `user`, `owner`, `start_date`, `end_date`, `activity_type`, `sort_by`, `count`

- `user`/`owner`: Partial emails work (`"cynthia@"` or `"cynthia"`)
- `activity_type`: `edit`, `view`, `share`, `comment`, `all`
- `sort_by`: `recent`, `edit_count`, `view_count`, `name`
- Dates: YYYY-MM-DD (default: last 7 days)

```python
# What did Jie and Rebecca work on Monday?
search_drive_activity(user="jie@,rebecca@", start_date="2024-12-23", end_date="2024-12-23")

# What did Cynthia edit most last week?
search_drive_activity(user="cynthia@", activity_type="edit", sort_by="edit_count")

# Docs owned by Leslie by view count
search_drive_activity(owner="leslie@", sort_by="view_count")
```

## get_drive_documents
Find files by owner, name, type.

**Params:** `owner`, `name`, `file_type`, `modified_after`, `shared_only`, `count`

- `owner`: **Full email required** (no partials)
- `name`: Partial match (`"budget"` → "Q4 Budget Report")
- `file_type`: `document`, `spreadsheet`, `presentation`, `pdf`, `folder`

```python
# Documents owned by Leslie
get_drive_documents(owner="leslie@company.com")

# Spreadsheets with "budget"
get_drive_documents(name="budget", file_type="spreadsheet")
```

## Key Differences

| Feature | search_drive_activity | get_drive_documents |
|---------|----------------------|---------------------|
| Partial emails | ✓ Email prefix only | ✗ Full email required |
| Date range | 1-2 weeks recommended | No limit |

**Note**: Long date ranges (>1 month) may return truncated results with a warning.
