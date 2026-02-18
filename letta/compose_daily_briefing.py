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

        # Calendar-day windows (workdays only, bounded by calendar days)
        # 7 calendar days = 5 workdays, 28 calendar days = 20 workdays (exact weeks)
        seven_days_ago = (target - timedelta(days=7)).strftime("%Y-%m-%d")
        twenty_eight_days_ago = (target - timedelta(days=28)).strftime("%Y-%m-%d")
        recent_7 = [h for h in history if h["snapshot_date"] > seven_days_ago]
        recent_28 = [h for h in history if h["snapshot_date"] > twenty_eight_days_ago]

        # --- Compute averages, deltas, and standout detection ---
        METRICS_TO_COMPARE = [
            ("drive_total_activities", "Drive activities"),
            ("drive_unique_users", "Drive users"),
            ("drive_unique_documents", "Drive documents"),
            ("drive_edits", "Drive edits"),
            ("drive_views", "Drive views"),
            ("drive_creates", "Drive creates"),
            ("drive_shares", "Drive shares"),
            ("drive_comments", "Drive comments"),
            ("email_total_sent", "Emails sent"),
            ("email_total_received", "Emails received"),
            ("email_total_activity", "Email total"),
            ("email_user_count", "Email users"),
            ("slack_total_messages", "Slack messages"),
            ("slack_channels_active", "Slack channels"),
            ("slack_members_active", "Slack members"),
        ]

        comparisons = {}
        for metric, label in METRICS_TO_COMPARE:
            today_val = today_snap.get(metric)
            if today_val is None:
                continue

            vals_28 = [h.get(metric, 0) for h in recent_28 if h.get(metric) is not None]
            vals_7 = [h.get(metric, 0) for h in recent_7 if h.get(metric) is not None]

            avg_28 = sum(vals_28) / len(vals_28) if vals_28 else 0
            avg_7 = sum(vals_7) / len(vals_7) if vals_7 else 0

            # Standard deviation for standout detection (28-day window)
            stddev_28 = 0.0
            if len(vals_28) > 1 and avg_28 > 0:
                variance = sum((v - avg_28) ** 2 for v in vals_28) / len(vals_28)
                stddev_28 = math.sqrt(variance)

            pct_vs_28 = round((today_val - avg_28) / avg_28 * 100) if avg_28 > 0 else 0
            pct_vs_7 = round((today_val - avg_7) / avg_7 * 100) if avg_7 > 0 else 0
            is_standout = abs(today_val - avg_28) > stddev_28 and stddev_28 > 0

            comparisons[metric] = {
                "label": label,
                "today": today_val,
                "avg_7": round(avg_7, 1),
                "avg_28": round(avg_28, 1),
                "pct_vs_7": pct_vs_7,
                "pct_vs_28": pct_vs_28,
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

        # --- Lambdas for formatting (no nested def — Letta constraint) ---
        fmt_pct = lambda p: "{} {}%".format(
            "\u25b2" if p > 0 else "\u25bc" if p < 0 else "\u2014", abs(p)
        )
        fmt_metric = lambda mk, lb: (
            None if not comparisons.get(mk) or not comparisons[mk]["today"] else
            "- {}: {} ({}){}".format(
                lb, comparisons[mk]["today"],
                ", ".join(filter(None, [
                    "7d: " + fmt_pct(comparisons[mk]["pct_vs_7"]) if comparisons[mk]["avg_7"] > 0 else None,
                    "28d: " + fmt_pct(comparisons[mk]["pct_vs_28"]) if comparisons[mk]["avg_28"] > 0 else None,
                ])) or "no history",
                " \u2014 **standout**" if comparisons[mk]["is_standout"] else ""
            )
        )
        get_top = lambda cat: [i for i in top_items if i.get("category") == cat]
        fmt_dual_trend = lambda comp: (
            "" if not comp else
            " ({})".format(", ".join(filter(None, [
                "7d: " + fmt_pct(comp["pct_vs_7"]) if comp["avg_7"] > 0 else None,
                "28d: " + fmt_pct(comp["pct_vs_28"]) if comp["avg_28"] > 0 else None,
            ]))) if (comp.get("avg_7", 0) > 0 or comp.get("avg_28", 0) > 0) else ""
        )

        # --- Format the briefing ---
        lines = [f"**Daily Analytics \u2014 {day_name}, {display_date}** (vs. 7d & 28d avg)\n"]

        # ===== DRIVE SECTION =====
        if today_snap.get("drive_total_activities"):
            lines.append("**Drive Activity**")

            # Summary line
            act_comp = comparisons.get("drive_total_activities")
            act_trend = fmt_dual_trend(act_comp)
            lines.append(
                f"- {today_snap['drive_total_activities']} activities across "
                f"{today_snap.get('drive_unique_documents', '?')} documents by "
                f"{today_snap.get('drive_unique_users', '?')} users{act_trend}"
            )

            # Activity breakdown with trends
            for metric_key, label in [
                ("drive_edits", "Edits"),
                ("drive_views", "Views"),
                ("drive_creates", "Creates"),
                ("drive_shares", "Shares"),
                ("drive_comments", "Comments"),
            ]:
                line = fmt_metric(metric_key, label)
                if line:
                    lines.append(line)

            # Top edited document
            edited = get_top("most_edited")
            if edited:
                top = edited[0]
                lines.append(
                    f"- Most edited: \"{top.get('item_title', '?')}\" "
                    f"({top.get('count', 0)} edits, owned by {top.get('item_owner', '?')})"
                )

            # Top viewed document (if different from most edited)
            viewed = get_top("most_viewed")
            if viewed:
                top = viewed[0]
                lines.append(
                    f"- Most viewed: \"{top.get('item_title', '?')}\" "
                    f"({top.get('count', 0)} views, owned by {top.get('item_owner', '?')})"
                )

            # Top shared document
            shared = get_top("most_shared")
            if shared:
                top = shared[0]
                lines.append(
                    f"- Most shared: \"{top.get('item_title', '?')}\" "
                    f"({top.get('count', 0)} shares, owned by {top.get('item_owner', '?')})"
                )

            # Top commented document
            commented = get_top("most_commented")
            if commented:
                top = commented[0]
                lines.append(
                    f"- Most commented: \"{top.get('item_title', '?')}\" "
                    f"({top.get('count', 0)} comments, owned by {top.get('item_owner', '?')})"
                )

            # Most active users (skip blank emails — org-level aggregates)
            active_users = [u for u in get_top("most_active_users") if u.get("item_title", "").strip()]
            if active_users:
                user_strs = []
                for u in active_users[:3]:
                    email = u.get("item_title", "")
                    short = email.split("@")[0] + "@" if "@" in email else email
                    user_strs.append(f"{short} ({u.get('count', 0)})")
                if user_strs:
                    lines.append(f"- Most active: {', '.join(user_strs)}")

            lines.append("")

        # ===== EMAIL SECTION =====
        email_activity = today_snap.get("email_total_activity") or 0
        email_received = today_snap.get("email_total_received") or 0
        if email_activity or email_received:
            lines.append("**Email**")
            sent = today_snap.get("email_total_sent", 0)
            received = today_snap.get("email_total_received", 0)
            ratio = today_snap.get("email_ratio", 0)
            user_count = today_snap.get("email_user_count", 0)
            total = sent + received

            # Main send/receive line with trend
            comp = comparisons.get("email_total_activity")
            range_note = fmt_dual_trend(comp)
            if comp and comp["is_standout"]:
                range_note += " \u2014 **standout**"
            elif comp and not range_note:
                range_note = " \u2014 typical"
            lines.append(f"- {sent} sent / {received} received (ratio: {ratio}){range_note}")

            # Note when sent=0 due to API lag
            if sent == 0 and received > 0:
                lines.append("  *(sent data may lag 24\u201348h in Admin Reports API)*")

            # Activity per user (derived metric)
            if user_count and user_count > 0:
                per_user = round(total / user_count, 1)
                lines.append(f"- {total} total activity across {user_count} users ({per_user}/user)")
            else:
                lines.append(f"- Total activity: {total}")

            # Sent trend (if we have history)
            sent_comp = comparisons.get("email_total_sent")
            sent_trend = fmt_dual_trend(sent_comp)
            if sent_trend:
                standout = " \u2014 **standout**" if sent_comp and sent_comp["is_standout"] else ""
                lines.append(f"- Sent{sent_trend}{standout}")

            # Received trend (if we have history)
            recv_comp = comparisons.get("email_total_received")
            recv_trend = fmt_dual_trend(recv_comp)
            if recv_trend:
                standout = " \u2014 **standout**" if recv_comp and recv_comp["is_standout"] else ""
                lines.append(f"- Received{recv_trend}{standout}")

            # Quartile workload distribution (when available and >= 12 active users)
            MIN_USERS_FOR_QUARTILE = 12
            quartiles = today_snap.get("email_quartiles")
            if quartiles and user_count and user_count >= MIN_USERS_FOR_QUARTILE:
                lines.append(f"- **Workload distribution** ({user_count} users, by total activity):")
                q_total_activity = sum(
                    quartiles.get(f"Q{i}", {}).get("activity", {}).get("count", 0) for i in range(1, 5)
                )
                for qi in range(1, 5):
                    qk = f"Q{qi}"
                    q = quartiles.get(qk, {})
                    q_users = q.get("user_count", 0)
                    q_act = q.get("activity", {})
                    q_avg = q_act.get("avg", 0)
                    q_count = q_act.get("count", 0)
                    q_sent_avg = q.get("sent", {}).get("avg", 0)
                    q_recv_avg = q.get("received", {}).get("avg", 0)
                    q_ratio = q.get("ratio", {}).get("avg", 0)
                    pct = round(q_count / q_total_activity * 100) if q_total_activity > 0 else 0
                    # Build detail string
                    detail_parts = [f"avg {q_avg}/user", f"{pct}% of volume"]
                    if q_sent_avg > 0 or q_recv_avg > 0:
                        detail_parts.append(f"s/r {q_sent_avg}/{q_recv_avg}")
                    if q_ratio > 0:
                        detail_parts.append(f"ratio {q_ratio}")
                    lines.append(f"  Q{qi} ({q_users} users): {', '.join(detail_parts)}")
                # Summary spread line
                q1_avg = quartiles.get("Q1", {}).get("activity", {}).get("avg", 0)
                q4_avg = quartiles.get("Q4", {}).get("activity", {}).get("avg", 0)
                if q1_avg > 0 and q4_avg > 0:
                    spread = round(q1_avg / q4_avg, 1)
                    lines.append(f"  Spread: {spread}x between top and bottom quartile")
                elif q1_avg > 0 and q4_avg == 0:
                    lines.append("  Spread: bottom quartile inactive")

            lines.append("")

        # ===== SLACK SECTION =====
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

            # Summary with trend
            msg_comp = comparisons.get("slack_total_messages")
            msg_trend = fmt_dual_trend(msg_comp)
            lines.append(
                f"- {today_snap['slack_total_messages']} messages across "
                f"{today_snap.get('slack_channels_active', '?')} channels by "
                f"{today_snap.get('slack_members_active', '?')} members{msg_trend}"
            )

            # Top channels
            slack_channels = get_top("top_channels")
            if slack_channels:
                top_list = ", ".join(
                    f"{ch.get('item_title', '?')} ({ch.get('count', 0)} msgs)"
                    for ch in slack_channels[:5]
                )
                lines.append(f"- Top: {top_list}")

            # Members active trend
            comp = comparisons.get("slack_members_active")
            if comp and comp["is_standout"]:
                members_trend = fmt_dual_trend(comp)
                lines.append(f"- Members active: {comp['today']}{members_trend} \u2014 **standout**")
            lines.append("")

        # ===== SLACK VIBE CHECK SECTION =====
        if vibe_text:
            MAX_VIBE_LENGTH = 500
            lines.append("**Slack Vibe Check**")
            if len(vibe_text) > MAX_VIBE_LENGTH:
                vibe_text = vibe_text[:MAX_VIBE_LENGTH - 3] + "..."
            lines.append(vibe_text)
            lines.append("")

        # ===== STANDOUT SUMMARY =====
        standouts = [c for c in comparisons.values() if c["is_standout"]]
        if standouts:
            notable = "; ".join(
                f"{s['label']} {'up' if s['pct_vs_28'] > 0 else 'down'} {abs(s['pct_vs_28'])}% (28d)"
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
            "snapshots_compared": len(recent_28),
            "standouts": len(standouts),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
