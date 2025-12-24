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

## Automatic OR Handling

Slack's API treats OR as AND when filters (user/channel) are present. The tool automatically works around this by splitting OR queries into separate searches and combining results.

**Auto-split triggers when:** OR in query + user or channel filter

```python
# These are automatically split and combined:
search_slack_messages(query="travel OR vacation", user="sue")
search_slack_messages(query="python OR code", channel="#random")
```

## Known Limitation

| Pattern | Issue | Workaround |
|---------|-------|------------|
| `*term` | Matches literal, not wildcard | Use `term*` |
