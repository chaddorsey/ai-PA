from typing import Dict, Any, Optional, List

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
