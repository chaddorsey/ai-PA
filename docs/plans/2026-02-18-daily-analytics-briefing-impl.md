# Daily Analytics Briefing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a daily pipeline that captures ephemeral Drive/Email/Slack metrics to a database, compares against trends, and delivers a morning briefing to the Pulse Monitor agent.

**Architecture:** A 4-step scheduler pipeline (CSV trigger → quantitative snapshot → Slack vibe check → compose briefing), where each step persists output to a durable store. Two new Letta tools (`collect_analytics_snapshot`, `compose_daily_briefing`) handle the quantitative capture and final assembly. The Pulse Monitor agent orchestrates the qualitative Slack vibe check using existing tools.

**Tech Stack:** PostgreSQL (analytics schema via PostgREST), Letta tools (Python), Scheduler-service cron jobs, Google Admin Reports API (existing), Slack analytics CSV (existing)

**Design Doc:** `docs/plans/2026-02-18-daily-analytics-briefing-design.md`

---

### Task 1: Database Schema

Create the `analytics` schema with `daily_snapshots` and `daily_top_items` tables in Supabase PostgreSQL.

**Files:**
- Create: `migrations/analytics_schema.sql`

**Step 1: Write the migration SQL**

Create `migrations/analytics_schema.sql`:

```sql
-- Daily Analytics Briefing schema
-- Stores ephemeral metrics (Drive Admin Reports, Email Admin Reports, Slack CSVs)
-- that cannot be reconstructed after their retention windows expire.

CREATE SCHEMA IF NOT EXISTS analytics;

-- Main snapshot table: one row per date
CREATE TABLE analytics.daily_snapshots (
  snapshot_date  DATE PRIMARY KEY,
  is_workday     BOOLEAN NOT NULL,
  collected_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Drive (Admin Reports API — ephemeral, 180-day window)
  drive_total_activities     INT,
  drive_unique_users         INT,
  drive_unique_documents     INT,
  drive_edits                INT,
  drive_views                INT,
  drive_creates              INT,
  drive_shares               INT,
  drive_comments             INT,
  drive_other_activities     INT,

  -- Email (Admin Reports API — ephemeral, 180-day window)
  email_total_sent           INT,
  email_total_received       INT,
  email_ratio                FLOAT,
  email_total_activity       INT,

  -- Slack (CSV export — point-in-time, non-recoverable)
  slack_covers_date          DATE,
  slack_total_messages       INT,
  slack_channels_active      INT,
  slack_members_active       INT,

  -- Full detail for ad-hoc queries and future metrics
  raw_snapshot               JSONB NOT NULL,

  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Top-N items per day (normalized for querying)
CREATE TABLE analytics.daily_top_items (
  id             SERIAL PRIMARY KEY,
  snapshot_date  DATE NOT NULL REFERENCES analytics.daily_snapshots(snapshot_date),
  domain         TEXT NOT NULL,
  category       TEXT NOT NULL,
  rank           INT NOT NULL,
  item_title     TEXT,
  item_id        TEXT,
  item_owner     TEXT,
  count          INT NOT NULL,
  metadata       JSONB
);

CREATE INDEX idx_daily_top_domain ON analytics.daily_top_items(domain, category, snapshot_date);

-- Grant PostgREST access
GRANT USAGE ON SCHEMA analytics TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA analytics TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA analytics TO service_role;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO anon, authenticated;
```

**Step 2: Apply the migration**

Run:
```bash
docker cp migrations/analytics_schema.sql ai-pa-supabase-db-1:/tmp/analytics_schema.sql
docker exec ai-pa-supabase-db-1 psql -U postgres -d postgres -f /tmp/analytics_schema.sql
```

Expected: `CREATE SCHEMA`, `CREATE TABLE` (x2), `CREATE INDEX`, `GRANT` (x4)

**Step 3: Expose analytics schema via PostgREST**

Edit `docker-compose.yml` line 41. Change:
```yaml
PGRST_DB_SCHEMA: public,pa_web,rag
```
to:
```yaml
PGRST_DB_SCHEMA: public,pa_web,rag,analytics
```

**Step 4: Add Supabase env vars to Letta container**

Edit `docker-compose.yml` in the letta service's `environment:` section (around line 627, after `DRIVE_RAG_SERVICE_URL`). Add:
```yaml
      # PostgREST access for analytics snapshot persistence
      SUPABASE_REST_URL: "http://supabase-rest:3000"
      SUPABASE_SERVICE_KEY: "${SUPABASE_SERVICE_KEY}"
```

**Step 5: Add analytics volume mount to Letta container**

Edit `docker-compose.yml` in the letta service's `volumes:` section (around line 599). Add:
```yaml
      - ./analytics:/app/tools/analytics  # Mount analytics directory for briefing output
```

**Step 6: Restart PostgREST to pick up schema change**

Run:
```bash
docker-compose restart supabase-rest
```

**Step 7: Verify schema is accessible via PostgREST**

Run:
```bash
curl -s http://localhost:8000/daily_snapshots -H "apikey: $(grep SUPABASE_SERVICE_KEY .env | cut -d= -f2)" -H "Accept-Profile: analytics" | head -20
```

Expected: `[]` (empty array, no error)

**Step 8: Create analytics/briefings directory with .gitkeep**

Run:
```bash
mkdir -p analytics/briefings
touch analytics/briefings/.gitkeep
```

**Step 9: Commit**

```bash
git add -f migrations/analytics_schema.sql analytics/briefings/.gitkeep
git add docker-compose.yml
git commit -m "feat: add analytics schema and PostgREST config for daily briefing"
```

---

### Task 2: `collect_analytics_snapshot` Letta Tool

Create the main quantitative snapshot tool that calls existing Drive/Email analytics functions and persists results to the database.

**Files:**
- Create: `letta/daily_analytics_snapshot.py`

**Step 1: Write the tool**

Create `letta/daily_analytics_snapshot.py`:

```python
from typing import Dict, Any, Optional


def collect_analytics_snapshot(date: Optional[str] = None) -> Dict[str, Any]:
    """Collect daily analytics snapshot from Drive, Email, and Slack, then persist to database.

    Gathers quantitative metrics from Google Admin Reports API (Drive + Email) and
    Slack analytics CSV exports. Writes the snapshot to analytics.daily_snapshots
    via PostgREST as a side effect — data is durable even if the agent drops context.

    Args:
        date: Date to collect in YYYY-MM-DD format (e.g., '2026-02-17'). Defaults to last workday.

    Returns:
        Dictionary with status, snapshot data, and database write confirmation.
    """
    import json
    import os
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
                activity_counts = {}
                top_edited = drive_data.get("top_edited", [])
                top_shared = drive_data.get("top_shared", [])
                top_commented = drive_data.get("top_commented", [])
                top_viewed = drive_data.get("top_viewed", [])
                top_users = drive_data.get("top_users", [])

                for item in top_edited:
                    activity_counts["edit"] = activity_counts.get("edit", 0) + item.get("count", 0)
                for item in top_shared:
                    activity_counts["share"] = activity_counts.get("share", 0) + item.get("count", 0)
                for item in top_commented:
                    activity_counts["comment"] = activity_counts.get("comment", 0) + item.get("count", 0)
                for item in top_viewed:
                    activity_counts["view"] = activity_counts.get("view", 0) + item.get("count", 0)

                total_activities = sum(activity_counts.values())
                unique_users = len(top_users)
                all_docs = set()
                for lst in [top_edited, top_shared, top_commented, top_viewed]:
                    for item in lst:
                        doc_id = item.get("doc_id", "")
                        if doc_id:
                            all_docs.add(doc_id)

                snapshot["drive"] = {
                    "total_activities": total_activities,
                    "unique_users": unique_users,
                    "unique_documents": len(all_docs),
                    "activity_breakdown": activity_counts,
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
                org_data = email_result.get("data", {})
                total_sent = org_data.get("total_sent", 0)
                total_received = org_data.get("total_received", 0)
                total_activity = total_sent + total_received
                ratio = round(total_sent / total_received, 2) if total_received > 0 else 0

                snapshot["email"] = {
                    "total_sent": total_sent,
                    "total_received": total_received,
                    "ratio": ratio,
                    "total_activity": total_activity,
                    "covers_date": date_str,
                }
            else:
                snapshot["errors"].append(f"Email: {email_result.get('error', 'unknown')}")
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
                        import re
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
                    resp_body = resp.read().decode("utf-8")
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
                        headers={**headers, "Prefer": ""},
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
```

**Step 2: Verify the tool imports work locally**

Run:
```bash
cd /Volumes/main-drive/ai-PA/letta && python -c "from daily_analytics_snapshot import collect_analytics_snapshot; print('Import OK')"
```

Expected: `Import OK`

**Step 3: Commit**

```bash
git add letta/daily_analytics_snapshot.py
git commit -m "feat: add collect_analytics_snapshot Letta tool with DB persistence"
```

---

### Task 3: `compose_daily_briefing` Letta Tool

Create the tool that reads from the database and archival memory, computes trends, and writes the final briefing to both a memory block and markdown file.

**Files:**
- Create: `letta/compose_daily_briefing.py`

**Step 1: Write the tool**

Create `letta/compose_daily_briefing.py`:

```python
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

        # --- Read today's snapshot from DB ---
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Accept-Profile": "analytics",
        }

        req = urllib.request.Request(
            f"{supabase_url}/daily_snapshots?snapshot_date=eq.{date_str}",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read().decode("utf-8"))

        if not rows:
            return {"status": "error", "error_message": f"No snapshot found for {date_str}"}

        today_snap = rows[0]

        # --- Read historical snapshots for trend comparison ---
        history_start = (target - timedelta(days=45)).strftime("%Y-%m-%d")
        hist_req = urllib.request.Request(
            f"{supabase_url}/daily_snapshots?snapshot_date=gte.{history_start}&snapshot_date=lte.{date_str}&is_workday=eq.true&order=snapshot_date.desc",
            headers=headers,
        )
        with urllib.request.urlopen(hist_req, timeout=15) as resp:
            history = json.loads(resp.read().decode("utf-8"))

        # Compute 7-day and 30-day workday averages
        recent_7 = [h for h in history[1:8] if h.get("is_workday")]
        recent_30 = [h for h in history[1:31] if h.get("is_workday")]

        metrics_to_compare = [
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
        for metric, label in metrics_to_compare:
            today_val = today_snap.get(metric)
            if today_val is None:
                continue

            vals_30 = [h.get(metric, 0) for h in recent_30 if h.get(metric) is not None]
            vals_7 = [h.get(metric, 0) for h in recent_7 if h.get(metric) is not None]

            avg_30 = sum(vals_30) / len(vals_30) if vals_30 else 0
            avg_7 = sum(vals_7) / len(vals_7) if vals_7 else 0

            stddev_30 = 0
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
            headers=headers,
        )
        with urllib.request.urlopen(top_req, timeout=15) as resp:
            top_items = json.loads(resp.read().decode("utf-8"))

        # --- Read Slack vibe check from archival memory ---
        vibe_text = ""
        if agent_id:
            try:
                vibe_req = urllib.request.Request(
                    f"{letta_url}/v1/agents/{agent_id}/archival-memory?search=daily_vibe_check%20{date_str}&limit=5",
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
        lines = [f"**Daily Analytics — {day_name}, {display_date}** (vs. 30-day avg)\n"]

        # Drive section
        drive = today_snap
        if drive.get("drive_total_activities"):
            lines.append("**Drive Activity**")
            lines.append(f"- {drive['drive_total_activities']} activities across {drive.get('drive_unique_documents', '?')} documents by {drive.get('drive_unique_users', '?')} users")

            for metric in ["drive_edits", "drive_views", "drive_shares", "drive_comments"]:
                comp = comparisons.get(metric)
                if comp and comp["today"]:
                    arrow = "▲" if comp["pct_vs_30"] > 0 else "▼" if comp["pct_vs_30"] < 0 else "—"
                    standout = " — **standout**" if comp["is_standout"] else ""
                    label_short = metric.replace("drive_", "").capitalize()
                    lines.append(f"- {label_short}: {comp['today']} ({arrow} {abs(comp['pct_vs_30'])}% vs avg){standout}")

            # Top edited
            edited_items = [i for i in top_items if i.get("category") == "most_edited"]
            if edited_items:
                top = edited_items[0]
                lines.append(f"- Most edited: \"{top.get('item_title', '?')}\" ({top.get('count', 0)} edits, owned by {top.get('item_owner', '?')})")

            lines.append("")

        # Email section
        if drive.get("email_total_activity"):
            lines.append("**Email**")
            sent = drive.get("email_total_sent", 0)
            received = drive.get("email_total_received", 0)
            ratio = drive.get("email_ratio", 0)
            comp = comparisons.get("email_total_activity")
            range_note = ""
            if comp:
                if comp["is_standout"]:
                    arrow = "▲" if comp["pct_vs_30"] > 0 else "▼"
                    range_note = f" ({arrow} {abs(comp['pct_vs_30'])}% vs avg) — **standout**"
                else:
                    range_note = " (within normal range)"
            lines.append(f"- {sent} sent / {received} received (ratio: {ratio})")
            lines.append(f"- Total activity: {sent + received}{range_note}")
            lines.append("")

        # Slack section
        slack_date = drive.get("slack_covers_date", "")
        if drive.get("slack_total_messages"):
            slack_display = ""
            if slack_date and slack_date != date_str:
                slack_display = f" (covering {slack_date})"
            lines.append(f"**Slack**{slack_display}")
            lines.append(f"- {drive['slack_total_messages']} messages across {drive.get('slack_channels_active', '?')} channels by {drive.get('slack_members_active', '?')} members")

            slack_channels = [i for i in top_items if i.get("category") == "top_channels"]
            if slack_channels:
                top_list = ", ".join(
                    f"{ch.get('item_title', '?')} ({ch.get('count', 0)} msgs)"
                    for ch in slack_channels[:3]
                )
                lines.append(f"- Top: {top_list}")

            comp = comparisons.get("slack_members_active")
            if comp and comp["is_standout"]:
                arrow = "▲" if comp["pct_vs_30"] > 0 else "▼"
                lines.append(f"- Members active: {comp['today']} ({arrow} {abs(comp['pct_vs_30'])}% vs avg)")
            lines.append("")

        # Vibe check section
        if vibe_text:
            lines.append("**Slack Vibe Check**")
            # Truncate to keep briefing concise
            if len(vibe_text) > 500:
                vibe_text = vibe_text[:497] + "..."
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
        try:
            output_dir = Path("/app/tools/analytics/briefings")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{date_str}.md"
            output_file.write_text(briefing_text, encoding="utf-8")
            md_written = True
        except Exception as e:
            # Fallback: try relative path
            try:
                output_dir = Path("analytics/briefings")
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"{date_str}.md"
                output_file.write_text(briefing_text, encoding="utf-8")
                md_written = True
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
            "block_written": block_written,
            "snapshots_compared": len(recent_30),
            "standouts": len(standouts),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
```

**Step 2: Verify the tool imports work locally**

Run:
```bash
cd /Volumes/main-drive/ai-PA/letta && python -c "from compose_daily_briefing import compose_daily_briefing; print('Import OK')"
```

Expected: `Import OK`

**Step 3: Commit**

```bash
git add letta/compose_daily_briefing.py
git commit -m "feat: add compose_daily_briefing Letta tool with trend comparison"
```

---

### Task 4: Registration Script

Create the script to register both tools with Letta and attach them to the Pulse Monitor agent.

**Files:**
- Create: `letta/register_daily_analytics.py`

**Step 1: Write the registration script**

Create `letta/register_daily_analytics.py`:

```python
#!/usr/bin/env python3
"""
Register Daily Analytics Briefing Tools with Letta Agent.

Tools:
  - collect_analytics_snapshot: Captures Drive/Email/Slack metrics, persists to DB
  - compose_daily_briefing: Reads from DB + archival, writes briefing to block + markdown

Usage:
  LETTA_BASE_URL=http://localhost:8283 python letta/register_daily_analytics.py

Attach to Pulse Monitor:
  LETTA_BASE_URL=http://localhost:8283 LETTA_AGENT_ID=agent-2ed14ef4-6289-453a-ae27-290b6ed196b8 python letta/register_daily_analytics.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from letta_client import Letta
except ImportError:
    try:
        from letta import Letta
    except ImportError:
        print("Error: letta_client not found. Install with: pip install letta-client")
        sys.exit(1)

from daily_analytics_snapshot import collect_analytics_snapshot
from compose_daily_briefing import compose_daily_briefing

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID")
# Pulse Monitor agent ID (default)
PULSE_MONITOR_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"


def main():
    print(f"{'='*60}")
    print("Daily Analytics Briefing Tools Registration")
    print(f"{'='*60}\n")

    print(f"Letta Base URL: {LETTA_BASE_URL}")
    agent_id = AGENT_ID or PULSE_MONITOR_ID
    print(f"Target Agent: {agent_id}\n")

    tools_to_register = [
        ("collect_analytics_snapshot", collect_analytics_snapshot,
         ["analytics", "drive", "email", "slack", "snapshot"]),
        ("compose_daily_briefing", compose_daily_briefing,
         ["analytics", "briefing", "trends", "daily"]),
    ]

    registered_tool_ids = []

    try:
        client = Letta(base_url=LETTA_BASE_URL)
        print("Connected to Letta server\n")

        for tool_name, tool_func, tags in tools_to_register:
            print(f"Registering tool: {tool_name}")

            try:
                created_tool = client.tools.create_from_function(
                    func=tool_func,
                    tags=tags,
                )
                tool_id = created_tool.id if hasattr(created_tool, "id") else "N/A"
                print(f"  Registered: {tool_name} (ID: {tool_id})")
                registered_tool_ids.append(tool_id)

            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "409" in error_str:
                    print(f"  Tool exists, re-registering...")
                    try:
                        all_tools = client.tools.list()
                        for tool in all_tools:
                            name = tool.name if hasattr(tool, "name") else tool.get("name")
                            if name == tool_name:
                                tid = tool.id if hasattr(tool, "id") else tool.get("id")
                                if tid:
                                    client.tools.delete(tool_id=tid)
                                    created_tool = client.tools.create_from_function(
                                        func=tool_func,
                                        tags=tags,
                                    )
                                    new_id = created_tool.id if hasattr(created_tool, "id") else "N/A"
                                    registered_tool_ids.append(new_id)
                                    print(f"  Re-registered: {tool_name} (ID: {new_id})")
                                    break
                    except Exception as re_e:
                        print(f"  Could not re-register: {re_e}")
                else:
                    print(f"  Failed: {e}")
            print()

        if agent_id and registered_tool_ids:
            print(f"Attaching tools to agent {agent_id}...")
            for tool_id in registered_tool_ids:
                try:
                    client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
                    print(f"  Attached {tool_id}")
                except Exception as e:
                    if "already" in str(e).lower():
                        print(f"  Already attached: {tool_id}")
                    else:
                        print(f"  Could not attach: {e}")

        print(f"\n{'='*60}")
        print("Registration Complete")
        print(f"{'='*60}")
        return 0

    except Exception as e:
        print(f"\nFailed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Commit**

```bash
git add letta/register_daily_analytics.py
git commit -m "feat: add registration script for daily analytics tools"
```

---

### Task 5: Memory Block Setup

Create the `daily_analytics_briefing` memory block and attach it to the Pulse Monitor agent.

**Files:**
- Create: `letta/create_daily_analytics_block.py`

**Step 1: Write the block creation script**

Create `letta/create_daily_analytics_block.py`:

```python
#!/usr/bin/env python3
"""
Create and attach the daily_analytics_briefing memory block to Pulse Monitor.

Usage:
  LETTA_BASE_URL=http://localhost:8283 python letta/create_daily_analytics_block.py
"""

import json
import os
import sys
import urllib.request

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
PULSE_MONITOR_ID = os.getenv(
    "LETTA_AGENT_ID",
    "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
)

BLOCK_LABEL = "daily_analytics_briefing"
BLOCK_DESCRIPTION = (
    "Most recent daily analytics briefing. Updated each morning by "
    "compose_daily_briefing(). Contains Drive, Email, and Slack metrics "
    "with trend comparisons. Replaced daily — only the latest briefing is stored here."
)
INITIAL_VALUE = "(No briefing generated yet. Run compose_daily_briefing() to populate.)"


def main():
    print(f"Letta: {LETTA_BASE}")
    print(f"Agent: {PULSE_MONITOR_ID}\n")

    # Check if block already exists
    req = urllib.request.Request(
        f"{LETTA_BASE}/v1/blocks/?label={BLOCK_LABEL}",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        existing = json.loads(resp.read().decode("utf-8"))

    if existing:
        block_id = existing[0].get("id")
        print(f"Block already exists: {block_id}")
    else:
        payload = json.dumps({
            "label": BLOCK_LABEL,
            "value": INITIAL_VALUE,
            "description": BLOCK_DESCRIPTION,
            "limit": 5000,
        }).encode("utf-8")
        create_req = urllib.request.Request(
            f"{LETTA_BASE}/v1/blocks/",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create_req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            block_id = result.get("id")
            print(f"Created block: {block_id}")

    # Attach to agent
    try:
        attach_req = urllib.request.Request(
            f"{LETTA_BASE}/v1/agents/{PULSE_MONITOR_ID}/core-memory/blocks/attach/{block_id}",
            method="PATCH",
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(attach_req, timeout=10)
        print(f"Attached to agent {PULSE_MONITOR_ID}")
    except Exception as e:
        if "already" in str(e).lower() or "409" in str(e).lower():
            print("Already attached to agent")
        else:
            print(f"Attach failed: {e}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Run the script**

```bash
LETTA_BASE_URL=http://localhost:8283 python letta/create_daily_analytics_block.py
```

Expected: `Created block: block-...` and `Attached to agent agent-2ed14ef4-...`

**Step 3: Commit**

```bash
git add letta/create_daily_analytics_block.py
git commit -m "feat: add daily_analytics_briefing memory block creation script"
```

---

### Task 6: Register Tools and Apply Docker Config

Register the tools with Letta, apply the docker-compose changes, and restart services.

**Step 1: Register tools**

Run:
```bash
LETTA_BASE_URL=http://localhost:8283 LETTA_AGENT_ID=agent-2ed14ef4-6289-453a-ae27-290b6ed196b8 python letta/register_daily_analytics.py
```

Expected: Both tools registered and attached.

**Step 2: Restart Letta to pick up new env vars and volume mount**

Run:
```bash
docker-compose up -d letta
```

Wait for Letta to become healthy:
```bash
docker-compose logs -f letta 2>&1 | head -30
```

**Step 3: Verify tools are visible**

Run:
```bash
curl -s http://localhost:8283/v1/tools | python3 -c "import sys,json; tools=json.load(sys.stdin); print([t['name'] for t in tools if 'analytics' in t.get('name','') or 'briefing' in t.get('name','')])"
```

Expected: `['collect_analytics_snapshot', 'compose_daily_briefing']`

---

### Task 7: Scheduler Jobs

Create the 4 scheduler jobs for the daily pipeline.

**Files:**
- Create: `scripts/create-analytics-pipeline-jobs.py`

**Step 1: Write the job creation script**

Create `scripts/create-analytics-pipeline-jobs.py`:

```python
#!/usr/bin/env python3
"""
Create scheduler jobs for the daily analytics briefing pipeline.

Pipeline:
  1. 2:00 AM ET Mon-Fri: Trigger Slack CSV export
  2. 2:30 AM ET Mon-Fri: Collect quantitative snapshot (Drive + Email + Slack CSV)
  3. 3:00 AM ET Mon-Fri: Slack vibe-check heartbeat
  4. 6:00 AM ET Mon-Fri: Compose final briefing from DB + archival memory
"""

import json
import sys
import requests

SCHEDULER_URL = "http://localhost:8087/v1"
PULSE_MONITOR_ID = "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8"

JOBS = [
    {
        "title": "Daily Analytics: Slack CSV Export Trigger",
        "description": "Trigger Slack analytics CSV export (channels + members). CSV covers 2-3 days ago due to Slack delay.",
        "created_by": "system",
        "category": "analytics_pipeline",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 7 * * 1-5"},  # 2 AM ET = 7 AM UTC
        },
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": PULSE_MONITOR_ID,
                "message": "Trigger Slack analytics CSV export for channels and members. Use trigger_slack_analytics_export(analytics_type='all'). Report the result.",
            },
        }],
    },
    {
        "title": "Daily Analytics: Quantitative Snapshot",
        "description": "Collect Drive/Email/Slack metrics and persist to analytics.daily_snapshots database.",
        "created_by": "system",
        "category": "analytics_pipeline",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "30 7 * * 1-5"},  # 2:30 AM ET = 7:30 AM UTC
        },
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": PULSE_MONITOR_ID,
                "message": "Collect the daily analytics snapshot using collect_analytics_snapshot(). This captures Drive, Email, and Slack quantitative metrics and persists them to the analytics database. Report the summary and any errors.",
            },
        }],
    },
    {
        "title": "Daily Analytics: Slack Vibe Check",
        "description": "Generate qualitative Slack channel summaries and write to archival memory for briefing assembly.",
        "created_by": "system",
        "category": "analytics_pipeline",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 8 * * 1-5"},  # 3 AM ET = 8 AM UTC
        },
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": PULSE_MONITOR_ID,
                "message": (
                    "Generate the daily Slack vibe check for yesterday across the top channels. "
                    "After summarizing each channel, write the summary to archival memory tagged "
                    "`daily_vibe_check` with today's date in YYYY-MM-DD format. "
                    "When all channels are done, write a combined summary to archival memory with "
                    "the same tag. Do NOT rely on conversation context to preserve these — the "
                    "compose step will read them from archival memory."
                ),
            },
        }],
    },
    {
        "title": "Daily Analytics: Compose Morning Briefing",
        "description": "Assemble final briefing from DB snapshot + archival vibe check. Writes to memory block + markdown.",
        "created_by": "system",
        "category": "analytics_pipeline",
        "schedule": {
            "type": "cron",
            "expression": {"cron": "0 11 * * 1-5"},  # 6 AM ET = 11 AM UTC
        },
        "actions": [{
            "action_type": "agent_message",
            "config": {
                "agent_id": PULSE_MONITOR_ID,
                "message": "Compose the daily analytics briefing using compose_daily_briefing(). This reads from the analytics database and archival memory, computes trend comparisons, and writes the briefing to both the daily_analytics_briefing memory block and the markdown archive. Share the briefing text with me.",
            },
        }],
    },
]


def main():
    print(f"Scheduler: {SCHEDULER_URL}")
    print(f"Agent: {PULSE_MONITOR_ID}\n")

    for job in JOBS:
        print(f"Creating: {job['title']}")
        try:
            resp = requests.post(f"{SCHEDULER_URL}/jobs", json=job, timeout=30)
            if resp.status_code in (200, 201):
                data = resp.json()
                job_id = data.get("job_id", "?")
                next_run = data.get("next_run_at", "?")
                print(f"  Created: {job_id}")
                print(f"  Next run: {next_run}")
            else:
                print(f"  Failed ({resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            print(f"  Error: {e}")
        print()

    print("Done. Verify with: curl http://localhost:8087/v1/jobs?category=analytics_pipeline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Run the job creation script**

```bash
python scripts/create-analytics-pipeline-jobs.py
```

Expected: 4 jobs created with next_run_at times.

**Step 3: Verify jobs are scheduled**

```bash
curl -s http://localhost:8087/v1/jobs?category=analytics_pipeline | python3 -c "import sys,json; jobs=json.load(sys.stdin); [print(f\"{j['title']}: next={j.get('next_run_at','?')}\") for j in jobs]"
```

**Step 4: Commit**

```bash
git add scripts/create-analytics-pipeline-jobs.py
git commit -m "feat: add scheduler jobs for daily analytics pipeline"
```

---

### Task 8: End-to-End Smoke Test

Manually trigger the snapshot and compose steps to verify the full pipeline works.

**Step 1: Trigger snapshot collection for a recent date**

Send a message to the Pulse Monitor agent:
```bash
curl -s -X POST http://localhost:8283/v1/agents/agent-2ed14ef4-6289-453a-ae27-290b6ed196b8/messages \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Collect the daily analytics snapshot for yesterday using collect_analytics_snapshot(). Report the full result."}]}'
```

Expected: Agent calls the tool, returns snapshot summary with `db_write: success`.

**Step 2: Verify data in database**

```bash
curl -s "http://localhost:8000/daily_snapshots?order=snapshot_date.desc&limit=1" \
  -H "apikey: $(grep SUPABASE_SERVICE_KEY .env | cut -d= -f2)" \
  -H "Accept-Profile: analytics"
```

Expected: JSON row with today's snapshot data.

**Step 3: Trigger compose (will have no vibe check data yet)**

```bash
curl -s -X POST http://localhost:8283/v1/agents/agent-2ed14ef4-6289-453a-ae27-290b6ed196b8/messages \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Compose the daily analytics briefing using compose_daily_briefing(). Share the full briefing text."}]}'
```

Expected: Agent returns formatted briefing text. Check `analytics/briefings/` for markdown output.

**Step 4: Verify markdown file was written**

```bash
ls -la analytics/briefings/
```

Expected: `YYYY-MM-DD.md` file with briefing content.

---

## Execution Notes

**PostgREST schema addition is critical.** Without adding `analytics` to `PGRST_DB_SCHEMA`, all PostgREST calls to the analytics tables will return 404.

**Letta env vars are critical.** Without `SUPABASE_SERVICE_KEY` and `SUPABASE_REST_URL` in the Letta container's environment, the tools can't persist to the database.

**Pulse Monitor agent ID.** Confirmed as `agent-2ed14ef4-6289-453a-ae27-290b6ed196b8` (pulse-monitor-agent_copy). If this is wrong, verify with:
```bash
curl -s http://localhost:8283/v1/agents | python3 -c "import sys,json; [print(f\"{a['name']}: {a['id']}\") for a in json.load(sys.stdin) if 'pulse' in a.get('name','').lower()]"
```

**Timezone note.** All cron expressions are in UTC (scheduler default). The design calls for ET times, so:
- 2:00 AM ET = 7:00 AM UTC (EST) or 6:00 AM UTC (EDT)
- Currently EST, so UTC offsets are +5 hours. Adjust when DST changes.
