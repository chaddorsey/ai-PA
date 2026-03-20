from typing import Dict, Any, Optional


def run_twitter(command: str, params: Optional[str] = None) -> Dict[str, Any]:
    """
    Interact with Twitter — read feeds, search, manage lists, bookmark tweets.

    Use command="schema" to see all available commands and their parameters.
    Use command="schema <name>" to see details for a specific command.

    Quick start:
      command="feed"                         -- Your home timeline
      command="user"    params='{"handle":"elonmusk","count":10}'  -- Someone's tweets
      command="search"  params='{"q":"AI agents"}'                 -- Search
      command="lists"                        -- Your Twitter lists (owned + followed)
      command="list-tweets" params='{"list_id":"123"}'  -- Tweets from a list
      command="curators"                     -- Top Twitter curators
      command="schema"                       -- List all commands

    Args:
        command: Command name or "schema" for discovery (REQUIRED)
        params: Optional JSON string of parameters (e.g. '{"count": 10}')

    Returns:
        Dictionary with status and the API response.
    """
    import json
    import traceback
    import urllib.request
    import urllib.parse

    # ENDPOINTS must be inside function body (Letta extracts function source only)
    ENDPOINTS = {
        # --- Read ---
        "feed": {
            "method": "GET",
            "path": "/twitter/feed",
            "description": "Your home timeline (paginated)",
            "params": {"count": "int (default 20)", "cursor": "str (optional, for next page)"},
        },
        "user": {
            "method": "GET",
            "path": "/twitter/user/{handle}",
            "description": "A user's recent tweets and retweets (paginated)",
            "params": {"handle": "str (required, in path)", "count": "int (default 20)", "cursor": "str (optional, for next page)"},
        },
        "bookmarks": {
            "method": "GET",
            "path": "/twitter/bookmarks",
            "description": "Your bookmarked tweets (paginated)",
            "params": {"count": "int (default 20)", "cursor": "str (optional, for next page)"},
        },
        "search": {
            "method": "GET",
            "path": "/twitter/search",
            "description": "Search tweets (paginated)",
            "params": {"q": "str (required)", "count": "int (default 20)", "cursor": "str (optional, for next page)"},
        },
        "tweet": {
            "method": "GET",
            "path": "/twitter/tweet/{tweet_id}",
            "description": "A tweet and its replies",
            "params": {"tweet_id": "str (required, in path)"},
        },
        "lists": {
            "method": "GET",
            "path": "/twitter/lists",
            "description": "Your owned and followed Twitter lists (id, name, member_count)",
            "params": {},
        },
        "list-members": {
            "method": "GET",
            "path": "/twitter/list/{list_id}/members",
            "description": "Members of a Twitter list (paginated)",
            "params": {"list_id": "str (required, in path)", "count": "int (default 100)", "cursor": "str (optional, for next page)"},
        },
        "list-tweets": {
            "method": "GET",
            "path": "/twitter/list/{list_id}/tweets",
            "description": "Recent tweets from a list timeline (paginated). Response includes next_cursor — pass it back as cursor to get the next page.",
            "params": {"list_id": "str (required, in path)", "count": "int (default 20)", "cursor": "str (optional, for pagination)"},
        },
        "curators": {
            "method": "GET",
            "path": "/twitter/curators",
            "description": "Top Twitter curators by retweeter overlap score",
            "params": {"top_k": "int (default 50)"},
        },
        "status": {
            "method": "GET",
            "path": "/twitter/status",
            "description": "Twitter ingestion progress and fetch status",
            "params": {},
        },
        # --- Write ---
        "bookmark": {
            "method": "POST",
            "path": "/twitter/bookmark/{tweet_id}",
            "description": "Bookmark a tweet (NOTE: currently blocked by Twitter — returns 404. Use list-add to save tweets to a list instead)",
            "params": {"tweet_id": "str (required, in path)"},
        },
        "list-add": {
            "method": "POST",
            "path": "/twitter/list-add",
            "description": "Add a user to a Twitter list",
            "params": {"list_id": "str (required)", "handle": "str (required)"},
        },
        "list-remove": {
            "method": "POST",
            "path": "/twitter/list-remove",
            "description": "Remove a user from a Twitter list",
            "params": {"list_id": "str (required)", "handle": "str (required)"},
        },
        "list-create": {
            "method": "POST",
            "path": "/twitter/list/create",
            "description": "Create a new Twitter list",
            "params": {"name": "str (required)", "description": "str (optional)", "private": "bool (default true)"},
        },
    }

    try:
        clean = command.strip().strip("/")

        # Schema discovery
        if clean == "schema":
            groups = {"read": [], "write": [], "pipeline": []}
            for name, meta in ENDPOINTS.items():
                if meta["method"] == "GET":
                    group = "read"
                elif name in ("run", "score"):
                    group = "pipeline"
                else:
                    group = "write"
                groups[group].append(
                    {"command": name, "description": meta["description"]}
                )
            return {"status": "ok", "result": groups}

        if clean.startswith("schema "):
            target = clean.split(" ", 1)[1].strip()
            if target in ENDPOINTS:
                meta = ENDPOINTS[target]
                return {"status": "ok", "result": {
                    "command": target,
                    "method": meta["method"],
                    "description": meta["description"],
                    "params": meta["params"] or "(none)",
                }}
            return {"status": "error", "error_message": f"Unknown command: {target}. Use command='schema' to list all."}

        # Resolve endpoint
        meta = ENDPOINTS.get(clean)
        if not meta:
            return {"status": "error", "error_message": f"Unknown command: {clean}. Use command='schema' to list all."}

        base_url = "http://curator-radar:5145/v1"

        query_params = {}
        if params:
            query_params = json.loads(params)

        # Normalize common param aliases
        ALIASES = {"id": "tweet_id", "list": "list_id", "user": "handle", "query": "q"}
        for alias, canonical in ALIASES.items():
            if alias in query_params and canonical not in query_params:
                query_params[canonical] = query_params.pop(alias)

        # Build URL, substituting path parameters
        path = meta["path"]
        path_params = {}
        for key in list(query_params.keys()):
            placeholder = "{" + key + "}"
            if placeholder in path:
                path = path.replace(placeholder, str(query_params.pop(key)))
                path_params[key] = True

        url = f"{base_url}{path}"

        if meta["method"] == "GET" and query_params:
            url += "?" + urllib.parse.urlencode(query_params)

        req = urllib.request.Request(url, method=meta["method"])
        req.add_header("Content-Type", "application/json")

        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read().decode())

        return {"status": "ok", "result": data}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
