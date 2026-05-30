def trigger_slack_analytics_export(analytics_type: str = "all") -> Dict[str, Any]:
    """Trigger Slack analytics CSV export via the slack-analytics-mcp-server.

    Calls the browser automation service to click "Export CSV" in Slack's admin
    analytics dashboard. The generated CSV files are delivered to Slackbot DMs
    within seconds and can then be picked up by collect_analytics_snapshot().

    Args:
        analytics_type: What to export. Options: 'channels', 'members', 'all'. Use 'all' to trigger both channels and members exports sequentially.

    Returns:
        Dictionary with status and export results.
    """
    import json
    import os
    import traceback
    import urllib.request
    import urllib.error

    try:
        EXPORT_URL = os.getenv(
            "SLACK_ANALYTICS_EXPORT_URL",
            "http://slack-analytics-mcp-server:8087/trigger-export",
        )
        REQUEST_TIMEOUT = 90

        valid_types = ("channels", "members", "all")
        if analytics_type not in valid_types:
            return {
                "status": "error",
                "error_message": f"Invalid analytics_type '{analytics_type}'. Must be one of: {', '.join(valid_types)}",
            }

        types_to_run = ["channels", "members"] if analytics_type == "all" else [analytics_type]
        results = []

        for atype in types_to_run:
            payload = json.dumps({
                "analytics_type": atype,
                "days_ago": 3,
                "date_range_days": 1,
            }).encode("utf-8")

            req = urllib.request.Request(
                EXPORT_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    results.append({
                        "type": atype,
                        "success": body.get("success", False),
                        "message": body.get("message", ""),
                        "date_range": body.get("date_range", {}),
                    })
            except urllib.error.HTTPError as http_err:
                error_body = http_err.read().decode("utf-8", errors="replace")[:500]
                results.append({
                    "type": atype,
                    "success": False,
                    "error": f"HTTP {http_err.code}: {error_body}",
                })
            except urllib.error.URLError as url_err:
                results.append({
                    "type": atype,
                    "success": False,
                    "error": f"Connection error: {str(url_err.reason)}",
                })

        all_ok = all(r.get("success") for r in results)
        return {
            "status": "ok" if all_ok else "partial",
            "exports": results,
            "summary": f"Triggered {len([r for r in results if r.get('success')])} of {len(results)} exports successfully.",
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}
{traceback.format_exc()}",
        }
