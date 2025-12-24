# Slack Search Query Syntax

## Syntax

| Pattern | Meaning | Example |
|---------|---------|---------|
| `term` | Single word | `python` |
| `term1 term2` | AND | `python code` |
| `term1 OR term2` | Either | `python OR javascript` |
| `"exact phrase"` | Exact phrase | `"code review"` |
| `term*` | Suffix wildcard | `deploy*` |
| `NOT term` or `-term` | Exclude | `python NOT javascript` |
| `@username` | Mentions of user | `@cdorsey` |

## @-Mentions

Use `@username` in query to find messages mentioning a user:

```python
# All mentions of a user
search_slack_messages(query="@cdorsey")

# Mentions in a specific channel
search_slack_messages(query="@cdorsey", channel="random")

# Mentions from a specific person
search_slack_messages(query="@cdorsey", user="dougmartin")

# Mentions in the past week
search_slack_messages(query="@cdorsey", start_date="2024-12-17")
```

## Automatic Handling

- **OR + filter**: Split into separate searches (Slack treats OR as AND with filters)
- **Date filters**: Uses Slack's `after:/before:` syntax for accurate filtering

## Known Limitation

| Pattern | Issue | Workaround |
|---------|-------|------------|
| `*term` | Matches literal, not wildcard | Use `term*` |
