# GitHub Starred Repos Search Tool — Design Spec

## Purpose

A self-contained Letta tool that lets agents search, browse, and retrieve details about the user's starred GitHub repositories. Enables lookup by keyword, specific repo retrieval, URL fetching, and README access via GitHub's GraphQL API.

## Tool Signature

```python
def search_github_stars(
    query: Optional[str] = None,
    repo: Optional[str] = None,
    readme: Optional[bool] = None,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `Optional[str]` | `None` | Keyword to search starred repos by name/description/topics. Omit to list recent stars. |
| `repo` | `Optional[str]` | `None` | Full repo name (`owner/repo`) to look up a specific repo. |
| `readme` | `Optional[bool]` | `None` | Include README content in results. `None` and `False` both mean "no README". |
| `limit` | `Optional[int]` | `None` | Max results (default 10, max 50). Ignored when `repo` is set. |
| `cursor` | `Optional[str]` | `None` | Pagination cursor for browsing (unfiltered mode only — see Modes below). |

### Modes of Operation

The tool has three distinct modes determined by which parameters are set:

**1. Browse mode** (`query=None`, `repo=None`)
Returns most recently starred repos, ordered by star date descending. Supports `cursor` for pagination. Each page returns up to `limit` results with `next_cursor` for the next page.

**2. Search mode** (`query` set)
Fetches starred repos (up to 500, i.e. 5 pages of 100) and filters client-side by case-insensitive substring match against repo name, description, and topics. Returns all matches up to `limit`. `cursor` is ignored in this mode — results are returned in a single batch since filtering is client-side.

**3. Repo lookup mode** (`repo` set)
Fetches a specific repo by `owner/name` via `repository(owner:, name:)` GraphQL query. Returns full repo details regardless of whether it's starred. `limit` and `cursor` are ignored.

### Usage Patterns

| Call | Behavior |
|------|----------|
| `search_github_stars()` | 10 most recently starred repos |
| `search_github_stars(limit=20)` | 20 most recently starred repos |
| `search_github_stars(query="mcp")` | Search stars matching "mcp" in name/description/topics |
| `search_github_stars(repo="anthropics/claude-code")` | Detail for a specific repo |
| `search_github_stars(query="agent", readme=True)` | Search with README content included |
| `search_github_stars(repo="foo/bar", readme=True)` | Single repo detail with full README |
| `search_github_stars(cursor="abc123")` | Next page of recent stars |

### Response Format

```json
{
  "status": "ok",
  "repos": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "description": "Short description",
      "language": "Python",
      "stars": 1234,
      "topics": ["ai", "agents"],
      "starred_at": "2026-03-01T12:00:00Z",
      "readme": "# Repo Title\n..."
    }
  ],
  "total_count": 342,
  "next_cursor": "Y3Vyc29yOnYy..."
}
```

- `readme` field only present when `readme=True`
- `next_cursor` present in browse mode; `null` when no more pages. Not returned in search or repo lookup modes.
- `total_count`: in browse mode, total starred repos. In search mode, total matches found within the fetch cap.

### Error Response

```json
{
  "status": "error",
  "error_message": "Description of what went wrong\n<traceback>"
}
```

## Architecture

### Self-contained — no service dependency

The tool calls GitHub's GraphQL API directly via `urllib.request`. No dependency on curator-radar or any other service.

### Auth

Reads `GITHUB_TOKEN` from `os.environ`. Already available in the Letta container via docker-compose environment configuration. Returns a clear error message if the token is missing.

### GitHub GraphQL API

**Endpoint:** `https://api.github.com/graphql`

**Browse mode query:** `viewer.starredRepositories` with:
- `first` / `after` for cursor-based pagination
- `orderBy: {field: STARRED_AT, direction: DESC}` for recency ordering
- Returns `totalCount`, `pageInfo.endCursor`, `pageInfo.hasNextPage`

**Search mode:** Same `starredRepositories` query but fetches up to 500 repos (5 pages of 100) and filters client-side. The `starredRepositories` field does NOT support a `query` parameter — server-side search is not available, so client-side substring matching on name, description, and topics is used.

**Repo lookup query:** `repository(owner: "...", name: "...")` — direct lookup, works for any public repo regardless of star status.

**README inline:** `object(expression: "HEAD:README.md")` fetched as part of the GraphQL query. Case-sensitive — only matches repos with a file literally named `README.md` at the root. Repos using `readme.md`, `README.rst`, or other variants will return no README content. This is a known limitation.

### Performance

- **Browse:** Single API call per page (up to 100 repos per call)
- **Search:** Up to 5 API calls to fetch starred repos for filtering (500 stars max scanned). Users with more than 500 stars will get results from their 500 most recent stars only.
- **Repo lookup:** Single API call
- **README with search:** Each page request includes inline README fetch — no additional calls, but increases response payload

### README Handling

- **Search results (`query` set):** READMEs truncated to first 2000 characters each to avoid context bloat
- **Single repo lookup (`repo` set):** Full README returned (no truncation)
- README fetched inline via GraphQL `object` field — no separate API call

### Letta Tool Constraints

Per project guidelines (`context/coding_custom_letta_tools.md`):
- All imports inside function body (after docstring)
- No nested `def` statements — all logic inline
- Parameters use only basic JSON types with `Optional[...]`
- All parameters documented in docstring `Args:` section
- Entire body wrapped in try-except
- Returns `Dict[str, Any]`

## Files

| File | Action | Purpose |
|------|--------|---------|
| `letta/github_stars_tools.py` | Create | Tool function |
| `letta/register_github_stars_tools.py` | Create | Registration script |

## Registration

```python
client.tools.upsert_from_function(
    func=search_github_stars,
    tags=["github", "stars", "repos", "search"],
)
```

Attach to Letta Code agent after registration (GET current tool IDs, append, PATCH with full list).

## Out of Scope (Phase 2)

- Full-text search across README contents of all starred repos
- Starring/unstarring repos
- Repo file browsing beyond README
- Caching or local indexing of starred repos
- README fallback for non-standard filenames (readme.md, README.rst, etc.)
