from typing import Dict, Any, Optional


def compose_daily_briefing(date: Optional[str] = None, agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Compose the daily analytics briefing from durable stores.

    Reads quantitative snapshot from analytics.daily_snapshots (PostgREST),
    reads Slack vibe-check summaries from archival memory, computes trend
    comparisons, and writes the formatted briefing to both a memory block
    and a markdown file.

    Args:
        date: Date to compose briefing for in YYYY-MM-DD format. Defaults to last workday.
        agent_id: Letta agent ID for archival memory and block access. Defaults to LETTA_AGENT_ID env var.

    Returns:
        Dictionary with status, briefing text, and write confirmations.
    """
    import json
    import math
    import os
    import traceback
    import urllib.request
    import urllib.parse
    from datetime import datetime, timedelta
    from pathlib import Path

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
        day_name = target.strftime("%A")
        display_date = target.strftime("%B %d").replace(" 0", " ")

        agent_id = agent_id or os.getenv("LETTA_AGENT_ID", "")

        supabase_url = os.getenv("SUPABASE_REST_URL", "http://supabase-rest:3000")
        service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        letta_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

        if not service_key:
            return {
                "status": "error",
                "error_message": "SUPABASE_SERVICE_KEY not set — cannot read analytics database",
            }

        # --- Helper: make PostgREST GET request ---
        postgrest_headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Accept-Profile": "analytics",
        }

        # --- Read today's snapshot from DB ---
        req = urllib.request.Request(
            f"{supabase_url}/daily_snapshots?snapshot_date=eq.{date_str}",
            headers=postgrest_headers,
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read().decode("utf-8"))

        if not rows:
            return {"status": "error", "error_message": f"No snapshot found for {date_str}. Run collect_analytics_snapshot(date='{date_str}') first."}

        today_snap = rows[0]

        # --- Read historical snapshots (last 45 days, workdays only) for trend comparison ---
        history_start = (target - timedelta(days=45)).strftime("%Y-%m-%d")
        hist_req = urllib.request.Request(
            f"{supabase_url}/daily_snapshots?snapshot_date=gte.{history_start}&snapshot_date=lt.{date_str}&is_workday=eq.true&order=snapshot_date.desc",
            headers=postgrest_headers,
        )
        with urllib.request.urlopen(hist_req, timeout=15) as resp:
            history = json.loads(resp.read().decode("utf-8"))

        # Split into 7-day and 30-day windows (history is already descending, excludes today)
        recent_7 = history[:7]
        recent_30 = history[:30]

        # --- Compute averages, deltas, and standout detection ---
        METRICS_TO_COMPARE = [
            ("drive_total_activities", "Drive activities"),
            ("drive_edits", "Drive edits"),
            ("drive_unique_users", "Drive users"),
            ("email_total_sent", "Emails sent"),
            ("email_total_received", "Emails received"),
            ("email_total_activity", "Email total"),
            ("slack_total_messages", "Slack messages"),
            ("slack_members_active", "Slack members"),
        ]

        comparisons = {}
        for metric, label in METRICS_TO_COMPARE:
            today_val = today_snap.get(metric)
            if today_val is None:
                continue

            vals_30 = [h.get(metric, 0) for h in recent_30 if h.get(metric) is not None]
            vals_7 = [h.get(metric, 0) for h in recent_7 if h.get(metric) is not None]

            avg_30 = sum(vals_30) / len(vals_30) if vals_30 else 0
            avg_7 = sum(vals_7) / len(vals_7) if vals_7 else 0

            # Standard deviation for standout detection
            stddev_30 = 0.0
            if len(vals_30) > 1 and avg_30 > 0:
                variance = sum((v - avg_30) ** 2 for v in vals_30) / len(vals_30)
                stddev_30 = math.sqrt(variance)

            pct_vs_30 = round((today_val - avg_30) / avg_30 * 100) if avg_30 > 0 else 0
            is_standout = abs(today_val - avg_30) > stddev_30 and stddev_30 > 0

            comparisons[metric] = {
                "label": label,
                "today": today_val,
                "avg_7": round(avg_7, 1),
                "avg_30": round(avg_30, 1),
                "pct_vs_30": pct_vs_30,
                "is_standout": is_standout,
            }

        # --- Read top items for today ---
        top_req = urllib.request.Request(
            f"{supabase_url}/daily_top_items?snapshot_date=eq.{date_str}&order=domain,category,rank",
            headers=postgrest_headers,
        )
        with urllib.request.urlopen(top_req, timeout=15) as resp:
            top_items = json.loads(resp.read().decode("utf-8"))

        # --- Read Slack vibe check from archival memory ---
        vibe_text = ""
        if agent_id:
            try:
                encoded_search = urllib.parse.quote(f"daily_vibe_check {date_str}")
                vibe_req = urllib.request.Request(
                    f"{letta_url}/v1/agents/{agent_id}/archival-memory?search={encoded_search}&limit=5",
                    headers={"Accept": "application/json"},
                )
                with urllib.request.urlopen(vibe_req, timeout=15) as resp:
                    vibe_entries = json.loads(resp.read().decode("utf-8"))

                if vibe_entries:
                    # Find the combined summary (longest entry)
                    longest = max(vibe_entries, key=lambda e: len(e.get("text", "")))
                    vibe_text = longest.get("text", "")
            except Exception:
                vibe_text = ""

        # --- Format the briefing ---
        lines = [f"**Daily Analytics \u2014 {day_name}, {display_date}** (vs. 30-day avg)\n"]

        # Drive section
        if today_snap.get("drive_total_activities"):
            lines.append("**Drive Activity**")
            lines.append(
                f"- {today_snap['drive_total_activities']} activities across "
                f"{today_snap.get('drive_unique_documents', '?')} documents by "
                f"{today_snap.get('drive_unique_users', '?')} users"
            )

            for metric in ["drive_edits", "drive_views", "drive_shares", "drive_comments"]:
                comp = comparisons.get(metric)
                if comp and comp["today"]:
                    arrow = "\u25b2" if comp["pct_vs_30"] > 0 else "\u25bc" if comp["pct_vs_30"] < 0 else "\u2014"
                    standout_tag = " \u2014 **standout**" if comp["is_standout"] else ""
                    label_short = metric.replace("drive_", "").capitalize()
                    lines.append(
                        f"- {label_short}: {comp['today']} "
                        f"({arrow} {abs(comp['pct_vs_30'])}% vs avg){standout_tag}"
                    )

            # Top edited document
            edited_items = [i for i in top_items if i.get("category") == "most_edited"]
            if edited_items:
                top = edited_items[0]
                lines.append(
                    f"- Most edited: \"{top.get('item_title', '?')}\" "
                    f"({top.get('count', 0)} edits, owned by {top.get('item_owner', '?')})"
                )

            lines.append("")

        # Email section
        if today_snap.get("email_total_activity"):
            lines.append("**Email**")
            sent = today_snap.get("email_total_sent", 0)
            received = today_snap.get("email_total_received", 0)
            ratio = today_snap.get("email_ratio", 0)
            comp = comparisons.get("email_total_activity")
            range_note = ""
            if comp:
                if comp["is_standout"]:
                    arrow = "\u25b2" if comp["pct_vs_30"] > 0 else "\u25bc"
                    range_note = f" ({arrow} {abs(comp['pct_vs_30'])}% vs avg) \u2014 **standout**"
                else:
                    range_note = " \u2014 typical"
            lines.append(f"- {sent} sent / {received} received (ratio: {ratio}){range_note}")
            lines.append(f"- Total activity: {sent + received} (within normal range)" if not (comp and comp["is_standout"]) else f"- Total activity: {sent + received}")
            lines.append("")

        # Slack section
        slack_covers = today_snap.get("slack_covers_date", "")
        if today_snap.get("slack_total_messages"):
            slack_display = ""
            if slack_covers and slack_covers != date_str:
                try:
                    slack_dt = datetime.strptime(slack_covers, "%Y-%m-%d")
                    slack_display = f" (covering {slack_dt.strftime('%b %d').replace(' 0', ' ')})"
                except ValueError:
                    slack_display = f" (covering {slack_covers})"
            lines.append(f"**Slack**{slack_display}")
            lines.append(
                f"- {today_snap['slack_total_messages']} messages across "
                f"{today_snap.get('slack_channels_active', '?')} channels by "
                f"{today_snap.get('slack_members_active', '?')} members"
            )

            slack_channels = [i for i in top_items if i.get("category") == "top_channels"]
            if slack_channels:
                top_list = ", ".join(
                    f"{ch.get('item_title', '?')} ({ch.get('count', 0)} msgs)"
                    for ch in slack_channels[:3]
                )
                lines.append(f"- Top: {top_list}")

            comp = comparisons.get("slack_members_active")
            if comp and comp["is_standout"]:
                arrow = "\u25b2" if comp["pct_vs_30"] > 0 else "\u25bc"
                lines.append(
                    f"- Members active: {comp['today']} "
                    f"({arrow} {abs(comp['pct_vs_30'])}% vs avg)"
                )
            lines.append("")

        # Vibe check section (from archival memory)
        if vibe_text:
            MAX_VIBE_LENGTH = 500
            lines.append("**Slack Vibe Check**")
            if len(vibe_text) > MAX_VIBE_LENGTH:
                vibe_text = vibe_text[:MAX_VIBE_LENGTH - 3] + "..."
            lines.append(vibe_text)
            lines.append("")

        # Standout summary
        standouts = [c for c in comparisons.values() if c["is_standout"]]
        if standouts:
            notable = "; ".join(
                f"{s['label']} {'up' if s['pct_vs_30'] > 0 else 'down'} {abs(s['pct_vs_30'])}%"
                for s in standouts
            )
            lines.append(f"**Notable:** {notable}")

        briefing_text = "\n".join(lines)

        # --- Write to markdown file ---
        md_written = False
        md_path = ""
        try:
            output_dir = Path("/app/tools/analytics/briefings")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{date_str}.md"
            output_file.write_text(briefing_text, encoding="utf-8")
            md_written = True
            md_path = str(output_file)
        except Exception:
            # Fallback: try relative path (useful outside Docker)
            try:
                output_dir = Path("analytics/briefings")
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"{date_str}.md"
                output_file.write_text(briefing_text, encoding="utf-8")
                md_written = True
                md_path = str(output_file)
            except Exception:
                pass

        # --- Write to memory block ---
        block_written = False
        if agent_id:
            try:
                # Find the daily_analytics_briefing block
                blocks_req = urllib.request.Request(
                    f"{letta_url}/v1/agents/{agent_id}/core-memory/blocks",
                    headers={"Accept": "application/json"},
                )
                with urllib.request.urlopen(blocks_req, timeout=10) as resp:
                    blocks = json.loads(resp.read().decode("utf-8"))

                target_block = None
                for block in blocks:
                    if block.get("label") == "daily_analytics_briefing":
                        target_block = block
                        break

                if target_block:
                    block_id = target_block.get("id")
                    update_data = json.dumps({"value": briefing_text}).encode("utf-8")
                    update_req = urllib.request.Request(
                        f"{letta_url}/v1/blocks/{block_id}",
                        data=update_data,
                        headers={"Content-Type": "application/json"},
                        method="PATCH",
                    )
                    urllib.request.urlopen(update_req, timeout=10)
                    block_written = True
            except Exception:
                pass

        return {
            "status": "ok",
            "date": date_str,
            "briefing": briefing_text,
            "markdown_written": md_written,
            "markdown_path": md_path,
            "block_written": block_written,
            "snapshots_compared": len(recent_30),
            "standouts": len(standouts),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
