from typing import Dict, Any, Optional


def query_curator_radar(endpoint: str, params: Optional[str] = None) -> Dict[str, Any]:
    """
    Query the Curator Radar service for GitHub and Twitter curator insights.

    GitHub endpoints:
      endpoint="curators"             -- Top GitHub curators by overlap score
      endpoint="curators", params='{"top_k": 10, "platform": "github"}'
      endpoint="discoveries"          -- New repos found by curators (last 7 days)
      endpoint="discoveries", params='{"since_days": 14}'
      endpoint="digest"               -- Full weekly digest (GitHub + Twitter) as Markdown
      endpoint="backfill/status"      -- Check GitHub backfill progress
      endpoint="score"                -- Trigger curator re-scoring (POST)
      endpoint="monitor/refresh"      -- Refresh curator events from GitHub (POST)
      endpoint="stargazers/refresh"   -- Incremental stargazer refresh + rescore (POST)
      endpoint="digest/deliver"       -- Generate and deliver digest to Slack (POST)

    Twitter endpoints:
      endpoint="twitter/curators"     -- Top Twitter curators by overlap score
      endpoint="twitter/curators", params='{"top_k": 20}'
      endpoint="twitter/status"       -- Twitter ingestion and fetch status
      endpoint="twitter/run"          -- Run full Twitter daily pipeline (POST)
      endpoint="twitter/score"        -- Score Twitter curators (POST)
      endpoint="twitter/sync-list"    -- Sync Twitter list with top curators (POST)

    Args:
        endpoint: The API endpoint to call (e.g. "curators", "discoveries", "twitter/curators")
        params: Optional JSON string of query parameters

    Returns:
        Dictionary with status and the API response.
    """
    import json
    import traceback
    import urllib.request
    import urllib.parse

    try:
        base_url = "http://curator-radar:5145/v1"
        url = f"{base_url}/{endpoint.strip('/')}"

        query_params = {}
        if params:
            query_params = json.loads(params)

        post_endpoints = {
            "backfill", "score", "monitor/refresh", "digest/deliver",
            "stargazers/refresh", "twitter/run", "twitter/ingest",
            "twitter/fetch-likers", "twitter/score", "twitter/sync-list",
        }
        method = "POST" if endpoint.strip("/") in post_endpoints else "GET"

        if method == "GET" and query_params:
            url += "?" + urllib.parse.urlencode(query_params)

        req = urllib.request.Request(url, method=method)
        req.add_header("Content-Type", "application/json")

        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read().decode())

        return {"status": "ok", "result": data}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
