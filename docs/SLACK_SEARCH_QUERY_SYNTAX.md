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

## Known Limitations

| Pattern | Issue | Workaround |
|---------|-------|------------|
| `*term` | Matches literal, not wildcard | Use `term*` |
| `OR + NOT + filter` | Returns 0 with user/channel | Split: search `python NOT script`, then `java NOT script` |

## Automatic Handling

- **OR + user + channel**: Auto-split
- **Phrase OR Phrase + filter**: Auto-split
- **Empty query**: Uses `*` wildcard

## Examples

```python
# OR with filters (auto-handled)
search_slack_messages(query="travel OR vacation", user="sue", channel="#random")

# OR + NOT + filter (split manually)
# Instead: query="python OR java NOT script", user="sue"
# Do: query="python NOT script", user="sue"
#     query="java NOT script", user="sue"
```
