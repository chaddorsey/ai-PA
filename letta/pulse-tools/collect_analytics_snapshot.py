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

                user_count = email_result.get("data", {}).get("user_count", 0)

                snapshot["email"] = {
                    "total_sent": total_sent,
                    "total_received": total_received,
                    "ratio": ratio,
                    "total_activity": total_activity,
                    "user_count": user_count,
                    "covers_date": date_str,
                }

                # Quartile distribution (pinned by activity) — always collect for historical record
                try:
                    quartile_result = get_email_analytics(
                        start_datetime=start_dt,
                        end_datetime=end_dt,
                        mode="quartile",
                        quartile_pin_metric="activity",
                    )
                    if quartile_result.get("status") == "ok":
                        snapshot["email"]["quartiles"] = quartile_result.get("data", {}).get("quartiles", {})
                except Exception:
                    pass  # Quartile is optional enrichment
            else:
                snapshot["errors"].append(
                    f"Email: {email_result.get('error_message', email_result.get('error', 'unknown'))}"
                )
        except Exception as e:
            snapshot["errors"].append(f"Email collection failed: {str(e)}")

        # --- Slack: query silver tables (built 2026-04-29) for the target date ---
        # Replaces the old "fetch latest CSV via files.list count=20" approach
        # which had three bugs:
        #   - channels_active was total_channels (not channels with messages > 0)
        #   - members_active stuck at 0 because count=20 list often missed member CSV
        #   - no date filter → picked yesterday's CSV when today's hadn't arrived
        # The silver tables are kept fresh by scheduler-service crons:
        #   slack-analytics-csv-poll.py (07:00 ET): captures CSVs to bronze
        #   parse-slack-analytics-csv.py (07:15 ET): parses into silver
        try:
            pg_password = os.getenv("POSTGRES_PASSWORD", "")
            pg_url = os.getenv(
                "PA_WEB_POSTGRES_URL",
                f"postgresql://postgres:{pg_password}@supabase-db:5432/postgres",
            )
            try:
                import psycopg
            except ImportError:
                snapshot["errors"].append("Slack: psycopg not available in sandbox")
                psycopg = None

            if psycopg is not None:
                with psycopg.connect(pg_url, autocommit=True, connect_timeout=10) as sl_conn:
                    with sl_conn.cursor() as sl_cur:
                        # Channel data for the target date (silver: per-channel per-day)
                        sl_cur.execute(
                            """
                            SELECT COUNT(*) FILTER (WHERE messages_posted > 0) AS active_channels,
                                   SUM(messages_posted)                        AS total_messages,
                                   COUNT(*)                                    AS total_channels
                            FROM analytics.slack_channel_daily
                            WHERE snapshot_date = %s
                            """,
                            (date_str,),
                        )
                        ch_row = sl_cur.fetchone()
                        # Member rollup for the target date (silver: aggregate-only)
                        sl_cur.execute(
                            """
                            SELECT members_active, members_posted, total_members, total_messages
                            FROM analytics.slack_member_rollup
                            WHERE snapshot_date = %s AND csv_window = 'single-day'
                            ORDER BY captured_at DESC LIMIT 1
                            """,
                            (date_str,),
                        )
                        mem_row = sl_cur.fetchone()
                        # Top channels by messages_posted for the target date
                        sl_cur.execute(
                            """
                            SELECT channel_name, messages_posted, members_who_posted
                            FROM analytics.slack_channel_daily
                            WHERE snapshot_date = %s AND messages_posted > 0
                            ORDER BY messages_posted DESC LIMIT 5
                            """,
                            (date_str,),
                        )
                        top_rows = sl_cur.fetchall()

                if ch_row and ch_row[2] and ch_row[2] > 0:
                    snapshot["slack"] = {
                        "covers_date": date_str,
                        "total_messages_posted": int(ch_row[1] or 0),
                        "channels_active": int(ch_row[0] or 0),
                        "members_active": int(mem_row[0]) if mem_row else 0,
                        "members_posted": int(mem_row[1]) if mem_row else 0,
                        "total_members": int(mem_row[2]) if mem_row else 0,
                        "top_channels": [
                            {
                                "channel": r[0],
                                "messages": int(r[1] or 0),
                                "posters": int(r[2] or 0),
                            }
                            for r in top_rows
                        ],
                        "source": "silver",
                    }
                else:
                    snapshot["errors"].append(
                        f"Slack: no silver data for {date_str} (poll cron may not have fired yet for that day)"
                    )
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
                    "email_user_count": email.get("user_count"),
                    "email_quartiles": email.get("quartiles"),
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

                for rank, user in enumerate(drive.get("top_active_users", [])[:5], 1):
                    top_items.append({
                        "snapshot_date": date_str,
                        "domain": "drive",
                        "category": "most_active_users",
                        "rank": rank,
                        "item_title": user.get("email", ""),
                        "item_id": "",
                        "item_owner": "",
                        "count": user.get("activity_count", 0),
                        "metadata": {},
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
            "error_message": f"{str(e)}
{traceback.format_exc()}",
        }
