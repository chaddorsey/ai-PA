from typing import Dict, Any, Optional


# Endpoint registry: defines method, description, and accepted params for each endpoint.
# The tool uses this for built-in schema discovery — no external docs needed.
ENDPOINTS = {
    # --- GitHub ---
    "curators": {
        "method": "GET",
        "description": "Top GitHub curators ranked by taste-overlap score",
        "params": {"top_k": "int (default 20)", "platform": "github|twitter (default github)"},
    },
    "discoveries": {
        "method": "GET",
        "description": "New repos discovered by top curators this week",
        "params": {"since_days": "int (default 7)"},
    },
    "digest": {
        "method": "GET",
        "description": "Combined GitHub + Twitter weekly digest as Markdown",
        "params": {"since_days": "int (default 7)"},
    },
    "backfill/status": {
        "method": "GET",
        "description": "GitHub star backfill progress",
        "params": {},
    },
    "score": {
        "method": "POST",
        "description": "Trigger curator re-scoring",
        "params": {"platform": "github|twitter (default github)"},
    },
    "monitor/refresh": {
        "method": "POST",
        "description": "Refresh public events from top GitHub curators",
        "params": {},
    },
    "stargazers/refresh": {
        "method": "POST",
        "description": "Incremental stargazer refresh: check counts, fetch new, rescore",
        "params": {},
    },
    "backfill": {
        "method": "POST",
        "description": "Scan for new GitHub stars and fetch their stargazers",
        "params": {"since_days": "int (default 365)"},
    },
    "digest/deliver": {
        "method": "POST",
        "description": "Generate and deliver weekly digest to Slack",
        "params": {"since_days": "int (default 7)"},
    },
    # --- Twitter ---
    "twitter/curators": {
        "method": "GET",
        "description": "Top Twitter curators by retweeter overlap score",
        "params": {"top_k": "int (default 50)"},
    },
    "twitter/status": {
        "method": "GET",
        "description": "Twitter ingestion progress and fetch status",
        "params": {},
    },
    "twitter/run": {
        "method": "POST",
        "description": "Full daily Twitter pipeline: ingest → fetch retweeters → score → sync list",
        "params": {},
    },
    "twitter/score": {
        "method": "POST",
        "description": "Score Twitter curators from retweeter overlap",
        "params": {},
    },
    "twitter/sync-list": {
        "method": "POST",
        "description": "Sync Twitter list membership with top curators",
        "params": {},
    },
}


def query_curator_radar(endpoint: str, params: Optional[str] = None) -> Dict[str, Any]:
    """
    Query the Curator Radar service — discovers people with similar taste
    in GitHub repos and Twitter content, then surfaces what they're finding.

    Use endpoint="schema" to see all available endpoints and their parameters.
    Use endpoint="schema <name>" to see details for a specific endpoint.

    Quick start:
      endpoint="discoveries"                          -- What did my curators find this week?
      endpoint="curators"                             -- Who are my top curators?
      endpoint="digest"                               -- Full weekly report
      endpoint="twitter/curators"                     -- Top Twitter curators
      endpoint="schema"                               -- List all endpoints

    Args:
        endpoint: API endpoint or "schema" for discovery (REQUIRED)
        params: Optional JSON string of query parameters (e.g. '{"top_k": 10}')

    Returns:
        Dictionary with status and the API response.
    """
    import json
    import traceback
    import urllib.request
    import urllib.parse

    try:
        clean = endpoint.strip().strip("/")

        # Schema discovery
        if clean == "schema":
            groups = {"github": [], "twitter": []}
            for name, meta in ENDPOINTS.items():
                group = "twitter" if name.startswith("twitter/") else "github"
                groups[group].append(
                    {"endpoint": name, "method": meta["method"], "description": meta["description"]}
                )
            return {"status": "ok", "result": groups}

        if clean.startswith("schema "):
            target = clean.split(" ", 1)[1].strip("/")
            if target in ENDPOINTS:
                meta = ENDPOINTS[target]
                return {"status": "ok", "result": {
                    "endpoint": target,
                    "method": meta["method"],
                    "description": meta["description"],
                    "params": meta["params"] or "(none)",
                }}
            return {"status": "error", "error_message": f"Unknown endpoint: {target}. Use endpoint='schema' to list all."}

        # Resolve method from registry
        meta = ENDPOINTS.get(clean)
        if not meta:
            return {"status": "error", "error_message": f"Unknown endpoint: {clean}. Use endpoint='schema' to list all."}

        base_url = "http://curator-radar:5145/v1"
        url = f"{base_url}/{clean}"

        query_params = {}
        if params:
            query_params = json.loads(params)

        if meta["method"] == "GET" and query_params:
            url += "?" + urllib.parse.urlencode(query_params)

        req = urllib.request.Request(url, method=meta["method"])
        req.add_header("Content-Type", "application/json")

        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read().decode())

        return {"status": "ok", "result": data}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
