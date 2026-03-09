from typing import Dict, Any, Optional


def query_curator_radar(endpoint: str, params: Optional[str] = None) -> Dict[str, Any]:
    """
    Query the Curator Radar service for GitHub star overlap insights.

    Available endpoints:
      endpoint="curators"             -- Top curators ranked by overlap score
      endpoint="curators", params='{"top_k": 10}'  -- Limit results
      endpoint="discoveries"          -- New repos found by curators (last 7 days)
      endpoint="discoveries", params='{"since_days": 14}'  -- Custom window
      endpoint="digest"               -- Full weekly digest as Markdown
      endpoint="backfill/status"      -- Check backfill progress
      endpoint="score"                -- Trigger curator re-scoring (POST)

    Args:
        endpoint: The API endpoint to call (e.g. "curators", "discoveries", "digest")
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

        post_endpoints = {"backfill", "score", "monitor/refresh", "digest/deliver"}
        method = "POST" if endpoint.strip("/") in post_endpoints else "GET"

        if method == "GET" and query_params:
            url += "?" + urllib.parse.urlencode(query_params)

        req = urllib.request.Request(url, method=method)
        req.add_header("Content-Type", "application/json")

        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode())

        return {"status": "ok", "result": data}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
