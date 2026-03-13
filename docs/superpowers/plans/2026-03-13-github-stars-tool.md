# GitHub Starred Repos Search Tool — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained Letta tool that searches, browses, and retrieves details about starred GitHub repos via the GraphQL API.

**Architecture:** Single Letta tool function (`search_github_stars`) calling GitHub's GraphQL API directly with `urllib.request`. Three modes: browse (paginated recent stars), search (client-side keyword filtering), and repo lookup. No service dependencies.

**Tech Stack:** Python, GitHub GraphQL API, urllib.request, Letta SDK for registration

**Spec:** `docs/superpowers/specs/2026-03-13-github-stars-tool-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `letta/github_stars_tools.py` | Create | Tool function — all logic inline per Letta constraints |
| `letta/register_github_stars_tools.py` | Create | Registration script using letta_client SDK |
| `docker-compose.yml` | Modify (line ~657) | Add `GITHUB_TOKEN` to Letta container environment |

---

## Chunk 1: Infrastructure + Tool Implementation

### Task 1: Add GITHUB_TOKEN to Letta container environment

**Files:**
- Modify: `docker-compose.yml` (Letta service environment block, around line 657)

- [ ] **Step 1: Add GITHUB_TOKEN env var to Letta service**

In `docker-compose.yml`, in the `letta:` service `environment:` block (after the existing `OPENAI_API_KEY` line around line 673), add:

```yaml
      GITHUB_TOKEN: ${GITHUB_TOKEN}
```

This passes the token from `.env` (already present: `GITHUB_TOKEN=ghp_...`) into the Letta container where tool sandbox code runs.

- [ ] **Step 2: Verify the env var is set in .env**

Run: `grep GITHUB_TOKEN .env | head -1`
Expected: `GITHUB_TOKEN=ghp_...` (token present)

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: expose GITHUB_TOKEN to Letta container for GitHub tools"
```

---

### Task 2: Implement the search_github_stars tool

**Files:**
- Create: `letta/github_stars_tools.py`

- [ ] **Step 1: Create the tool file**

Create `letta/github_stars_tools.py` with the full tool function. The function must follow all Letta tool constraints:
- All imports inside function body
- No nested `def` statements
- try-except wrapper around entire body
- All params documented in `Args:` docstring

```python
from typing import Dict, Any, Optional


def search_github_stars(
    query: Optional[str] = None,
    repo: Optional[str] = None,
    readme: Optional[bool] = None,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search and browse your starred GitHub repositories.

    Three modes:
      1. Browse: No query/repo — returns most recently starred repos (supports cursor pagination)
      2. Search: query="keyword" — searches starred repos by name/description/topics (up to 500 stars scanned)
      3. Lookup: repo="owner/name" — fetches details for a specific repo

    Examples:
      search_github_stars()                                  — 10 most recent stars
      search_github_stars(query="mcp")                       — search stars matching "mcp"
      search_github_stars(repo="anthropics/claude-code")     — specific repo details
      search_github_stars(query="agent", readme=True)        — search with README content
      search_github_stars(cursor="abc123")                   — next page of recent stars

    Args:
        query: Keyword to search starred repos by name, description, and topics. Omit to list recent stars.
        repo: Full repo name (owner/repo) to look up a specific repo's details.
        readme: Set to True to include README.md content in results.
        limit: Max results to return (default 10, max 50). Ignored when repo is set.
        cursor: Pagination cursor from previous response's next_cursor (browse mode only, ignored in search mode).

    Returns:
        Dictionary with status, repos list, total_count, and next_cursor.
    """
    import json
    import os
    import traceback
    import urllib.request
    import urllib.error

    try:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            return {"status": "error", "error_message": "GITHUB_TOKEN environment variable not set"}

        if limit is None:
            limit = 10
        limit = max(1, min(limit, 50))

        graphql_url = "https://api.github.com/graphql"
        readme_fragment = ""
        if readme:
            readme_fragment = """
                object(expression: "HEAD:README.md") {
                  ... on Blob { text }
                }"""

        # --- Repo lookup mode ---
        if repo:
            parts = repo.strip().split("/", 1)
            if len(parts) != 2:
                return {"status": "error", "error_message": f"Invalid repo format: {repo}. Use owner/name."}
            owner, name = parts

            gql = """
            query($owner: String!, $name: String!) {
              repository(owner: $owner, name: $name) {
                nameWithOwner
                url
                description
                primaryLanguage { name }
                stargazerCount
                repositoryTopics(first: 20) {
                  nodes { topic { name } }
                }
                README_PLACEHOLDER
              }
            }
            """.replace("README_PLACEHOLDER", readme_fragment if readme else "")

            variables = {"owner": owner, "name": name}
            payload = json.dumps({"query": gql, "variables": variables}).encode()
            req = urllib.request.Request(graphql_url, data=payload, method="POST")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "letta-github-stars-tool")

            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read().decode())

            if "errors" in data:
                return {"status": "error", "error_message": str(data["errors"])}

            r = data.get("data", {}).get("repository")
            if not r:
                return {"status": "error", "error_message": f"Repository not found: {repo}"}

            readme_text = None
            if readme:
                obj = r.get("object")
                if obj:
                    readme_text = obj.get("text")

            repo_entry = {
                "name": r.get("nameWithOwner", repo),
                "url": r.get("url", f"https://github.com/{repo}"),
                "description": r.get("description"),
                "language": (r.get("primaryLanguage") or {}).get("name"),
                "stars": r.get("stargazerCount", 0),
                "topics": [n["topic"]["name"] for n in (r.get("repositoryTopics", {}).get("nodes") or [])],
            }
            if readme:
                repo_entry["readme"] = readme_text

            return {"status": "ok", "repos": [repo_entry], "total_count": 1}

        # --- Build starred repos GraphQL query ---
        gql = """
        query($first: Int!, $after: String) {
          viewer {
            starredRepositories(first: $first, after: $after, orderBy: {field: STARRED_AT, direction: DESC}) {
              totalCount
              pageInfo { endCursor hasNextPage }
              edges {
                starredAt
                node {
                  nameWithOwner
                  url
                  description
                  primaryLanguage { name }
                  stargazerCount
                  repositoryTopics(first: 20) {
                    nodes { topic { name } }
                  }
                  README_PLACEHOLDER
                }
              }
            }
          }
        }
        """.replace("README_PLACEHOLDER", readme_fragment if readme else "")

        # --- Browse mode (no query) ---
        if not query:
            variables = {"first": limit}
            if cursor:
                variables["after"] = cursor

            payload = json.dumps({"query": gql, "variables": variables}).encode()
            req = urllib.request.Request(graphql_url, data=payload, method="POST")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "letta-github-stars-tool")

            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read().decode())

            if "errors" in data:
                return {"status": "error", "error_message": str(data["errors"])}

            starred = data.get("data", {}).get("viewer", {}).get("starredRepositories", {})
            repos = []
            for edge in (starred.get("edges") or []):
                node = edge.get("node", {})
                entry = {
                    "name": node.get("nameWithOwner"),
                    "url": node.get("url"),
                    "description": node.get("description"),
                    "language": (node.get("primaryLanguage") or {}).get("name"),
                    "stars": node.get("stargazerCount", 0),
                    "topics": [n["topic"]["name"] for n in (node.get("repositoryTopics", {}).get("nodes") or [])],
                    "starred_at": edge.get("starredAt"),
                }
                if readme:
                    obj = node.get("object")
                    text = obj.get("text") if obj else None
                    entry["readme"] = text[:2000] if text and len(text) > 2000 else text
                repos.append(entry)

            page_info = starred.get("pageInfo", {})
            next_cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None

            return {
                "status": "ok",
                "repos": repos,
                "total_count": starred.get("totalCount", 0),
                "next_cursor": next_cursor,
            }

        # --- Search mode (query set) ---
        search_lower = query.lower()
        all_repos = []
        fetch_cursor = None
        max_pages = 5  # 500 stars max

        for _ in range(max_pages):
            variables = {"first": 100}
            if fetch_cursor:
                variables["after"] = fetch_cursor

            payload = json.dumps({"query": gql, "variables": variables}).encode()
            req = urllib.request.Request(graphql_url, data=payload, method="POST")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "letta-github-stars-tool")

            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read().decode())

            if "errors" in data:
                return {"status": "error", "error_message": str(data["errors"])}

            starred = data.get("data", {}).get("viewer", {}).get("starredRepositories", {})

            for edge in (starred.get("edges") or []):
                node = edge.get("node", {})
                name = node.get("nameWithOwner") or ""
                desc = node.get("description") or ""
                topics = [n["topic"]["name"] for n in (node.get("repositoryTopics", {}).get("nodes") or [])]
                topics_str = " ".join(topics)

                searchable = f"{name} {desc} {topics_str}".lower()
                if search_lower in searchable:
                    entry = {
                        "name": name,
                        "url": node.get("url"),
                        "description": node.get("description"),
                        "language": (node.get("primaryLanguage") or {}).get("name"),
                        "stars": node.get("stargazerCount", 0),
                        "topics": topics,
                        "starred_at": edge.get("starredAt"),
                    }
                    if readme:
                        obj = node.get("object")
                        text = obj.get("text") if obj else None
                        entry["readme"] = text[:2000] if text and len(text) > 2000 else text
                    all_repos.append(entry)

            page_info = starred.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            fetch_cursor = page_info.get("endCursor")

        return {
            "status": "ok",
            "repos": all_repos[:limit],
            "total_count": len(all_repos),
        }

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:500]
        except Exception:
            pass
        return {"status": "error", "error_message": f"GitHub API error {e.code}: {body}\n{traceback.format_exc()}"}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

- [ ] **Step 2: Verify file syntax**

Run: `python3 -c "import ast; ast.parse(open('letta/github_stars_tools.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add letta/github_stars_tools.py
git commit -m "feat: add search_github_stars Letta tool"
```

---

## Chunk 2: Registration + Deployment

### Task 3: Create the registration script

**Files:**
- Create: `letta/register_github_stars_tools.py`

- [ ] **Step 1: Create registration script**

Create `letta/register_github_stars_tools.py`:

```python
#!/usr/bin/env python3
"""Register search_github_stars tool with the Letta server.

Usage:
    LETTA_BASE_URL=http://localhost:8283 python register_github_stars_tools.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from letta_client import Letta
from github_stars_tools import search_github_stars

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")


def main():
    client = Letta(base_url=LETTA_BASE_URL)

    tools = [
        (search_github_stars, ["github", "stars", "repos", "search"]),
    ]

    registered = []
    for func, tags in tools:
        try:
            tool = client.tools.upsert_from_function(
                func=func,
                tags=tags,
            )
            registered.append(tool.name)
            print(f"Registered: {tool.name} ({tool.id})")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"Already exists: {func.__name__}")
                registered.append(func.__name__)
            else:
                print(f"Failed to register {func.__name__}: {e}")

    print(f"\nRegistered {len(registered)} tools")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add letta/register_github_stars_tools.py
git commit -m "feat: add registration script for GitHub stars tool"
```

---

### Task 4: Register tool and attach to Letta Code agent

- [ ] **Step 1: Register the tool with Letta**

Run:
```bash
cd /Volumes/main-drive/ai-PA && LETTA_BASE_URL=http://localhost:8283 python3 letta/register_github_stars_tools.py
```
Expected: `Registered: search_github_stars (tool-...)`

- [ ] **Step 2: Get the tool ID**

Capture the tool ID from registration output. It will look like `tool-XXXXXXXX-XXXX-...`.

- [ ] **Step 3: Attach to Letta Code agent safely**

**CRITICAL: Use the safe PATCH pattern — GET current tools, append, PATCH with full list.**

First, identify the Letta Code agent ID:
```bash
curl -s http://localhost:8283/v1/agents/?limit=50 | python3 -c "
import sys, json
agents = json.load(sys.stdin)
for a in agents:
    if 'code' in a['name'].lower() or 'letta-code' in a['name'].lower():
        print(f\"{a['name']}: {a['id']}\")
"
```

Then safely attach:
```bash
AGENT_ID="<agent-id-from-above>"
TOOL_ID="<tool-id-from-registration>"

# GET current tools
CURRENT=$(curl -s "http://localhost:8283/v1/agents/$AGENT_ID/" | python3 -c "
import sys, json
a = json.load(sys.stdin)
ids = [t['id'] for t in a.get('tools', [])]
print(','.join(ids))
")

echo "Current tool count: $(echo $CURRENT | tr ',' '\n' | wc -l)"

# Append new tool and PATCH
ALL_IDS="$CURRENT,$TOOL_ID"
TOOL_IDS_JSON=$(echo $ALL_IDS | tr ',' '\n' | python3 -c "
import sys, json
ids = [line.strip() for line in sys.stdin if line.strip()]
print(json.dumps(ids))
")

curl -s -X PATCH "http://localhost:8283/v1/agents/$AGENT_ID/" \
  -H 'Content-Type: application/json' \
  -d "{\"tool_ids\": $TOOL_IDS_JSON}" | python3 -c "
import sys, json
a = json.load(sys.stdin)
print(f\"Updated tool count: {len(a.get('tools', []))}\")"
```

Verify new count = old count + 1.

---

### Task 5: Restart Letta and smoke test

- [ ] **Step 1: Restart Letta to pick up GITHUB_TOKEN**

Run:
```bash
docker compose restart letta
```

Wait for healthy:
```bash
docker compose ps letta
```

- [ ] **Step 2: Test browse mode via Letta sandbox**

The tool runs inside Letta's sandbox. Test by sending a message to the Letta Code agent asking it to run `search_github_stars()` — or test the GitHub API directly from the container:

```bash
docker exec ai-pa-letta-1 python3 -c "
import os, json, urllib.request
token = os.environ.get('GITHUB_TOKEN', '')
print(f'Token present: {bool(token)}')
gql = '{\"query\": \"{ viewer { starredRepositories(first: 2, orderBy: {field: STARRED_AT, direction: DESC}) { totalCount edges { node { nameWithOwner } } } } }\"}'
req = urllib.request.Request('https://api.github.com/graphql', data=gql.encode(), method='POST')
req.add_header('Authorization', f'Bearer {token}')
req.add_header('Content-Type', 'application/json')
req.add_header('User-Agent', 'test')
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read().decode())
total = data['data']['viewer']['starredRepositories']['totalCount']
repos = [e['node']['nameWithOwner'] for e in data['data']['viewer']['starredRepositories']['edges']]
print(f'Total stars: {total}')
print(f'Recent: {repos}')
"
```

Expected: Token present, total star count, 2 recent repos listed.

- [ ] **Step 3: Test search mode**

Ask the Letta Code agent to run:
```
search_github_stars(query="mcp")
```

Expected: Matching repos returned with name, URL, description.

- [ ] **Step 4: Test repo lookup mode**

Ask the agent to run:
```
search_github_stars(repo="anthropics/claude-code", readme=True)
```

Expected: Repo details with README content.
