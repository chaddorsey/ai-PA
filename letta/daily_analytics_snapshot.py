from typing import Dict, Any, Optional


def collect_analytics_snapshot(date: Optional[str] = None) -> Dict[str, Any]:
    """Collect daily analytics snapshot from Drive, Email, and Slack, then persist to database.

    Gathers quantitative metrics from Google Admin Reports API (Drive + Email) and
    Slack analytics CSV exports. Writes the snapshot to analytics.daily_snapshots
    via PostgREST as a side effect -- data is durable even if the agent drops context.

    Args:
        date: Date to collect in YYYY-MM-DD format (e.g., '2026-02-17'). Defaults to last workday.

    Returns:
        Dictionary with status, snapshot data, and database write confirmation.
    """
    import json
    import os
    import re
    import traceback
    import urllib.request
    import urllib.parse
    from datetime import datetime, timedelta

    try:
        # --- Determine target date ---
        if date:
            target = datetime.strptime(date, "%Y-%m-%d")
        else:
            today = datetime.now()
            target = today - timedelta(days=1)
            while target.weekday() >= 5:
                target -= timedelta(days=1)

        date_str = target.strftime("%Y-%m-%d")
        is_workday = target.weekday() < 5

        snapshot = {
            "snapshot_date": date_str,
            "collected_at": datetime.utcnow().isoformat() + "Z",
            "is_workday": is_workday,
            "drive": None,
            "email": None,
            "slack": None,
            "errors": [],
        }

        # --- Drive: Admin Reports API ---
        try:
            from drive_analytics_tools import collect_daily_workspace_activity

            drive_raw = collect_daily_workspace_activity(date=date_str)
            drive_data = json.loads(drive_raw) if isinstance(drive_raw, str) else drive_raw

            if "error" not in drive_data:
                # Extract summary counts from the structured return
                summary = drive_data.get("summary", {})
                top_five = drive_data.get("top_five", {})

                top_edited = top_five.get("most_edited", [])
                top_shared = top_five.get("most_shared", [])
                top_commented = top_five.get("most_commented", [])
                top_viewed = top_five.get("most_viewed", [])
                top_users = top_five.get("most_active_users", [])

                # Build activity breakdown from top_activity_types list
                activity_breakdown = {}
                for entry in drive_data.get("top_activity_types", []):
                    act_type = entry.get("type", "other")
                    act_count = entry.get("count", 0)
                    if act_type == "edit":
                        activity_breakdown["edit"] = activity_breakdown.get("edit", 0) + act_count
                    elif act_type == "view":
                        activity_breakdown["view"] = activity_breakdown.get("view", 0) + act_count
                    elif act_type == "create":
                        activity_breakdown["create"] = activity_breakdown.get("create", 0) + act_count
                    elif act_type in (
                        "change_user_access",
                        "change_acl_editors",
                        "change_document_visibility",
                        "change_document_access_scope",
                    ):
                        activity_breakdown["share"] = activity_breakdown.get("share", 0) + act_count
                    elif act_type in (
                        "create_comment",
                        "resolve_comment",
                        "delete_comment",
                        "edit_comment",
                    ):
                        activity_breakdown["comment"] = activity_breakdown.get("comment", 0) + act_count
                    else:
                        activity_breakdown["other"] = activity_breakdown.get("other", 0) + act_count

                snapshot["drive"] = {
                    "total_activities": summary.get("total_activities", 0),
                    "unique_users": summary.get("unique_users", 0),
                    "unique_documents": summary.get("unique_documents", 0),
                    "activity_breakdown": activity_breakdown,
                    "top_edited": top_edited[:5],
                    "top_shared": top_shared[:5],
                    "top_commented": top_commented[:5],
                    "top_viewed": top_viewed[:5],
                    "top_active_users": top_users[:5],
                }
            else:
                snapshot["errors"].append(f"Drive: {drive_data.get('error', 'unknown')}")
        except Exception as e:
            snapshot["errors"].append(f"Drive collection failed: {str(e)}")

        # --- Email: Admin Reports API ---
        try:
            from email_analytics_tools import get_email_analytics

            start_dt = f"{date_str}T00:00:00-05:00"
            end_dt = f"{date_str}T23:59:59-05:00"
            email_result = get_email_analytics(
                start_datetime=start_dt,
                end_datetime=end_dt,
                mode="org",
            )

            if email_result.get("status") == "ok":
                org_totals = email_result.get("data", {}).get("org_totals", {})
                total_sent = org_totals.get("sent", 0)
                total_received = org_totals.get("received", 0)
                total_activity = org_totals.get("activity", total_sent + total_received)
                ratio = org_totals.get("ratio", 0)
                if ratio == 0 and total_received > 0:
                    ratio = round(total_sent / total_received, 2)

                snapshot["email"] = {
                    "total_sent": total_sent,
                    "total_received": total_received,
                    "ratio": ratio,
                    "total_activity": total_activity,
                    "covers_date": date_str,
                }
            else:
                snapshot["errors"].append(
                    f"Email: {email_result.get('error_message', email_result.get('error', 'unknown'))}"
                )
        except Exception as e:
            snapshot["errors"].append(f"Email collection failed: {str(e)}")

        # --- Slack: Most recent CSV analysis ---
        try:
            from slack_analytics_simple import analyze_slack_analytics

            slack_token = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
            if slack_token:
                # List recent Slack files to find the latest channels CSV
                list_url = "https://slack.com/api/files.list"
                params = urllib.parse.urlencode({
                    "token": slack_token,
                    "types": "snippets,docs",
                    "count": "20",
                })
                req = urllib.request.Request(f"{list_url}?{params}")
                req.add_header("Authorization", f"Bearer {slack_token}")

                with urllib.request.urlopen(req, timeout=30) as resp:
                    files_data = json.loads(resp.read().decode("utf-8"))

                csv_file = None
                if files_data.get("ok"):
                    for f in files_data.get("files", []):
                        name = f.get("name", "").lower()
                        if "channel" in name and name.endswith(".csv"):
                            csv_file = f
                            break

                if csv_file:
                    file_url = csv_file.get("url_private_download", "")
                    csv_result_raw = analyze_slack_analytics(file_url, top_n=5)
                    csv_result = json.loads(csv_result_raw) if isinstance(csv_result_raw, str) else csv_result_raw

                    analysis = csv_result.get("analysis", {})
                    if analysis:
                        # Extract date from filename if possible (e.g., channels-2026-02-14.csv)
                        csv_name = csv_file.get("name", "")
                        covers_date = date_str  # fallback
                        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", csv_name)
                        if date_match:
                            covers_date = date_match.group(1)

                        total_messages = sum(
                            ch.get("count", 0)
                            for ch in analysis.get("top_by_messages_posted", [])
                        )

                        snapshot["slack"] = {
                            "covers_date": covers_date,
                            "total_messages_posted": total_messages,
                            "channels_active": analysis.get("total_channels", 0),
                            "members_active": 0,  # Only available from members CSV
                            "top_channels": [
                                {
                                    "channel": ch.get("channel", ""),
                                    "messages": ch.get("count", 0),
                                    "posters": 0,
                                }
                                for ch in analysis.get("top_by_messages_posted", [])[:5]
                            ],
                        }
                    else:
                        snapshot["errors"].append("Slack: CSV analysis returned no data")
                else:
                    snapshot["errors"].append("Slack: No channels CSV found in recent files")
            else:
                snapshot["errors"].append("Slack: SLACK_MCP_XOXP_TOKEN not set")
        except Exception as e:
            snapshot["errors"].append(f"Slack collection failed: {str(e)}")

        # --- Persist to database via PostgREST ---
        db_write_status = "skipped"
        try:
            supabase_url = os.getenv("SUPABASE_REST_URL", "http://supabase-rest:3000")
            service_key = os.getenv("SUPABASE_SERVICE_KEY", "")

            if not service_key:
                snapshot["errors"].append("DB: SUPABASE_SERVICE_KEY not set, snapshot not persisted")
            else:
                headers = {
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                    "Content-Type": "application/json",
                    "Accept-Profile": "analytics",
                    "Content-Profile": "analytics",
                    "Prefer": "resolution=merge-duplicates,return=representation",
                }

                drive = snapshot.get("drive") or {}
                email = snapshot.get("email") or {}
                slack = snapshot.get("slack") or {}

                row = {
                    "snapshot_date": date_str,
                    "is_workday": is_workday,
                    "drive_total_activities": drive.get("total_activities"),
                    "drive_unique_users": drive.get("unique_users"),
                    "drive_unique_documents": drive.get("unique_documents"),
                    "drive_edits": drive.get("activity_breakdown", {}).get("edit"),
                    "drive_views": drive.get("activity_breakdown", {}).get("view"),
                    "drive_creates": drive.get("activity_breakdown", {}).get("create"),
                    "drive_shares": drive.get("activity_breakdown", {}).get("share"),
                    "drive_comments": drive.get("activity_breakdown", {}).get("comment"),
                    "drive_other_activities": drive.get("activity_breakdown", {}).get("other"),
                    "email_total_sent": email.get("total_sent"),
                    "email_total_received": email.get("total_received"),
                    "email_ratio": email.get("ratio"),
                    "email_total_activity": email.get("total_activity"),
                    "slack_covers_date": slack.get("covers_date"),
                    "slack_total_messages": slack.get("total_messages_posted"),
                    "slack_channels_active": slack.get("channels_active"),
                    "slack_members_active": slack.get("members_active"),
                    "raw_snapshot": snapshot,
                }

                data = json.dumps(row).encode("utf-8")
                req = urllib.request.Request(
                    f"{supabase_url}/daily_snapshots",
                    data=data,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp.read()
                    if resp.status in (200, 201):
                        db_write_status = "success"
                    else:
                        db_write_status = f"unexpected status {resp.status}"
                        snapshot["errors"].append(f"DB write status: {resp.status}")

                # Write top items
                top_items = []
                for category, items in [
                    ("most_edited", drive.get("top_edited", [])),
                    ("most_shared", drive.get("top_shared", [])),
                    ("most_commented", drive.get("top_commented", [])),
                    ("most_viewed", drive.get("top_viewed", [])),
                ]:
                    for rank, item in enumerate(items[:5], 1):
                        top_items.append({
                            "snapshot_date": date_str,
                            "domain": "drive",
                            "category": category,
                            "rank": rank,
                            "item_title": item.get("title", item.get("display_title", "")),
                            "item_id": item.get("doc_id", ""),
                            "item_owner": item.get("owner", ""),
                            "count": item.get("count", 0),
                            "metadata": {"link": item.get("link", ""), "is_accessible": item.get("is_accessible", True)},
                        })

                for rank, ch in enumerate(slack.get("top_channels", [])[:5], 1):
                    top_items.append({
                        "snapshot_date": date_str,
                        "domain": "slack",
                        "category": "top_channels",
                        "rank": rank,
                        "item_title": ch.get("channel", ""),
                        "item_id": "",
                        "item_owner": "",
                        "count": ch.get("messages", 0),
                        "metadata": {"posters": ch.get("posters", 0)},
                    })

                if top_items:
                    # Delete existing top items for this date first
                    del_req = urllib.request.Request(
                        f"{supabase_url}/daily_top_items?snapshot_date=eq.{date_str}",
                        headers={
                            "apikey": service_key,
                            "Authorization": f"Bearer {service_key}",
                            "Accept-Profile": "analytics",
                            "Content-Profile": "analytics",
                        },
                        method="DELETE",
                    )
                    try:
                        urllib.request.urlopen(del_req, timeout=10)
                    except Exception:
                        pass  # OK if nothing to delete

                    items_data = json.dumps(top_items).encode("utf-8")
                    items_req = urllib.request.Request(
                        f"{supabase_url}/daily_top_items",
                        data=items_data,
                        headers=headers,
                        method="POST",
                    )
                    urllib.request.urlopen(items_req, timeout=30)

        except Exception as e:
            db_write_status = f"error: {str(e)}"
            snapshot["errors"].append(f"DB persistence failed: {str(e)}")

        return {
            "status": "ok" if not snapshot["errors"] else "partial",
            "snapshot_date": date_str,
            "db_write": db_write_status,
            "drive_collected": snapshot["drive"] is not None,
            "email_collected": snapshot["email"] is not None,
            "slack_collected": snapshot["slack"] is not None,
            "errors": snapshot["errors"],
            "summary": {
                "drive_activities": (snapshot.get("drive") or {}).get("total_activities", 0),
                "email_total": (snapshot.get("email") or {}).get("total_activity", 0),
                "slack_messages": (snapshot.get("slack") or {}).get("total_messages_posted", 0),
            },
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
