#!/usr/bin/env python3
"""
Backfill Slack analytics data into daily_snapshots.

Keeps a single browser session open per analytics type and loops through
all dates without switching tabs. Runs channels first, then members.

Uses a fire-and-forget approach: trigger all exports quickly, then
batch-collect CSVs from Slack files API afterward.

Usage:
    # Backfill all existing snapshots that lack Slack data
    python3 scripts/backfill-slack-analytics.py

    # Backfill specific date range
    python3 scripts/backfill-slack-analytics.py --start 2025-01-17 --end 2025-08-21

    # Only update existing DB rows (don't create new ones)
    python3 scripts/backfill-slack-analytics.py --existing-only

    # Dry run
    python3 scripts/backfill-slack-analytics.py --dry-run

    # Limit to N dates (for testing)
    python3 scripts/backfill-slack-analytics.py --limit 3

    # Skip channels, only do members
    python3 scripts/backfill-slack-analytics.py --members-only
"""

import argparse
import asyncio
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

SLACK_WORKSPACE_URL = "https://concord-consortium.slack.com"
SLACK_DATA_START = "2025-01-17"

# Timing (seconds) — tuned for speed
WAIT_FOR_DATA_REFRESH = 5  # Wait after Save for table to refresh
WAIT_AFTER_EXPORT_CLICK = 2  # Wait after Export CSV click (just enough for toast)
CHUNK_SIZE = 5  # Trigger this many exports before collecting CSVs


def load_env():
    """Load .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if not os.getenv(key):
                        os.environ[key] = value


def get_dates_needing_slack(supabase_url, service_key, start_date=None, end_date=None):
    """Get dates from DB that have null Slack data."""
    params = "select=snapshot_date&slack_total_messages=is.null&order=snapshot_date.asc"
    if start_date:
        params += f"&snapshot_date=gte.{start_date}"
    if end_date:
        params += f"&snapshot_date=lte.{end_date}"

    req = urllib.request.Request(f"{supabase_url}/daily_snapshots?{params}")
    req.add_header("apikey", service_key)
    req.add_header("Authorization", f"Bearer {service_key}")
    req.add_header("Accept-Profile", "analytics")

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [d["snapshot_date"] for d in data]


def generate_workdays(start_date, end_date):
    """Generate workday dates in a range."""
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    dates = []
    while current <= end:
        if current.weekday() < 5:
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def find_slack_csv(slack_token, name_contains, max_age_minutes=5):
    """Find the most recent CSV in Slack files matching the name pattern."""
    params = urllib.parse.urlencode({"count": "10"})
    req = urllib.request.Request(f"https://slack.com/api/files.list?{params}")
    req.add_header("Authorization", f"Bearer {slack_token}")

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if not data.get("ok"):
        return None

    now = time.time()
    for f in data.get("files", []):
        name = f.get("name", "").lower()
        created = f.get("created", 0)
        age_minutes = (now - created) / 60
        if name_contains in name and name.endswith(".csv") and age_minutes < max_age_minutes:
            return f
    return None


def _parse_csv_filename_date(name):
    """Extract start date from a Slack analytics CSV filename.

    Filenames look like:
      Concord Consortium Channel Analytics Feb 15, 2026 - Feb 16, 2026.csv
      Concord Consortium Member Analytics Jan 17, 2025 - Jan 18, 2025.csv

    Returns start date as YYYY-MM-DD or None.
    """
    # Match: Month DD, YYYY - Month DD, YYYY
    m = re.search(
        r"Analytics\s+(\w+ \d{1,2}, \d{4})\s*-\s*\w+ \d{1,2}, \d{4}\.csv$",
        name,
        re.IGNORECASE,
    )
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1), "%b %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def batch_collect_csvs(slack_token, csv_type, expected_dates, ts_from=None, max_pages=20):
    """Collect all CSVs from Slack files API and match to expected dates.

    CSV filenames look like:
      Concord Consortium Channel Analytics Feb 15, 2026 - Feb 16, 2026.csv

    Args:
        csv_type: "channel" or "member" — used to filter filenames.
        expected_dates: list of YYYY-MM-DD dates to match.
        ts_from: Unix timestamp — only return files created after this time.
        max_pages: Max API pages to scan.

    Returns dict mapping start_date -> file_info.
    """
    matched = {}
    expected_set = set(expected_dates)
    page_num = 1

    while page_num <= max_pages and len(matched) < len(expected_set):
        query_params = {"count": "100", "page": str(page_num), "types": "all"}
        if ts_from:
            query_params["ts_from"] = str(int(ts_from))
        params = urllib.parse.urlencode(query_params)
        req = urllib.request.Request(f"https://slack.com/api/files.list?{params}")
        req.add_header("Authorization", f"Bearer {slack_token}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            break

        if not data.get("ok"):
            break

        files = data.get("files", [])
        if not files:
            break

        for f in files:
            name = f.get("name", "")
            if not name.endswith(".csv"):
                continue
            # Filter by type (Channel/Member)
            if csv_type.lower() not in name.lower():
                continue
            # Skip "Prior 30 Days" default exports
            if "prior" in name.lower():
                continue

            start_date = _parse_csv_filename_date(name)
            if start_date and start_date in expected_set and start_date not in matched:
                matched[start_date] = f

        paging = data.get("paging", {})
        if page_num >= paging.get("pages", 1):
            break
        page_num += 1

    return matched


def download_csv(slack_token, file_info):
    """Download a Slack CSV and return parsed rows."""
    url = file_info.get("url_private_download", "")
    if not url:
        return None

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {slack_token}")

    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read().decode("utf-8")

    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


def parse_channels_csv(rows):
    """Extract metrics from channels CSV rows."""
    total_messages = 0
    channels_active = len(rows)
    top_channels = []

    msg_col = None
    channel_col = None
    for name in ["Messages posted", "messages_posted", "Messages", "Messages sent"]:
        if rows and name in rows[0]:
            msg_col = name
            break
    for name in ["Channel", "Channel name", "Name", "channel", "name"]:
        if rows and name in rows[0]:
            channel_col = name
            break

    if msg_col:
        for row in rows:
            count = int(row.get(msg_col, "0").replace(",", ""))
            total_messages += count

        sorted_rows = sorted(rows, key=lambda r: int(r.get(msg_col, "0").replace(",", "")), reverse=True)
        for r in sorted_rows[:5]:
            top_channels.append({
                "channel": r.get(channel_col, "") if channel_col else "",
                "messages": int(r.get(msg_col, "0").replace(",", "")),
            })

    return {
        "total_messages_posted": total_messages,
        "channels_active": channels_active,
        "top_channels": top_channels,
    }


def parse_members_csv(rows):
    """Extract metrics from members CSV rows."""
    return {"members_active": len(rows)}


def db_update(supabase_url, service_key, date_str, updates):
    """PATCH an existing snapshot row."""
    data = json.dumps(updates).encode("utf-8")
    url = f"{supabase_url}/daily_snapshots?snapshot_date=eq.{date_str}"
    req = urllib.request.Request(url, data=data, method="PATCH")
    req.add_header("apikey", service_key)
    req.add_header("Authorization", f"Bearer {service_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept-Profile", "analytics")
    req.add_header("Content-Profile", "analytics")

    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status in (200, 204)


def db_upsert(supabase_url, service_key, date_str, slack_data):
    """Insert or update a snapshot row."""
    row = {
        "snapshot_date": date_str,
        "is_workday": True,
        "slack_covers_date": date_str,
        "slack_total_messages": slack_data.get("total_messages_posted", 0),
        "slack_channels_active": slack_data.get("channels_active", 0),
        "slack_members_active": slack_data.get("members_active", 0),
        "raw_snapshot": json.dumps({"source": "backfill", "slack": slack_data}),
    }

    data = json.dumps(row).encode("utf-8")
    req = urllib.request.Request(f"{supabase_url}/daily_snapshots", data=data, method="POST")
    req.add_header("apikey", service_key)
    req.add_header("Authorization", f"Bearer {service_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept-Profile", "analytics")
    req.add_header("Content-Profile", "analytics")
    req.add_header("Prefer", "resolution=merge-duplicates,return=representation")

    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status in (200, 201)


async def set_date_and_export(page, analytics_type, start_date, end_date, verbose=False):
    """Open date picker, type dates, click Save, click Export CSV.

    Returns True on success. Handles both fresh dropdown and already-in-custom-range states.
    """
    # Open date range dropdown (channels and members use different data-qa)
    if analytics_type == "channels":
        dd = 'div[data-qa="analytics_channels-table-header-filter-button"]'
    else:
        dd = 'div[data-qa="data_table_header-filter-button"]'
    if await page.locator(dd).count() == 0:
        if verbose:
            print("[dd not found] ", end="", flush=True)
        return False

    await page.locator(dd).click(timeout=5000)
    await page.wait_for_timeout(400)

    # Check if date inputs are already visible (already in custom range mode)
    si = page.get_by_role("textbox", name="Start date")
    if await si.count() == 0:
        # Not in custom range mode — need to click "Range..." first
        try:
            range_opt = page.locator('[data-qa="SELECT_NEW"]').or_(page.locator('text="Range"'))
            await range_opt.click(timeout=3000)
            await page.wait_for_timeout(500)
        except Exception:
            if verbose:
                print("[no Range opt] ", end="", flush=True)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
            return False

    # Type start date (triple-click to select all, then type)
    try:
        si = page.get_by_role("textbox", name="Start date")
        await si.click(click_count=3, timeout=3000)
        await si.type(start_date)
    except Exception:
        if verbose:
            print("[start input fail] ", end="", flush=True)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
        return False

    # Type end date
    try:
        ei = page.get_by_role("textbox", name="End date")
        await ei.click(click_count=3, timeout=3000)
        await ei.type(end_date)
    except Exception:
        if verbose:
            print("[end input fail] ", end="", flush=True)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
        return False

    # Validate + Save
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(300)

    try:
        save = page.get_by_role("button", name="Save")
        if await save.count() > 0:
            await save.click(timeout=3000)
        else:
            if verbose:
                print("[no Save btn] ", end="", flush=True)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
            return False
    except Exception:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
        return False

    # Wait for data refresh
    await page.wait_for_timeout(WAIT_FOR_DATA_REFRESH * 1000)

    # Dismiss modals and toasts aggressively
    for _ in range(3):
        if await page.locator('.ReactModal__Overlay').count() > 0:
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(200)
        else:
            break

    # Remove all toasts via JS to prevent them from covering the Export button
    await page.evaluate("document.querySelectorAll('.c-toast, .ReactModal__Content--after-open.c-toast').forEach(el => el.remove())")
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(300)

    # Click Export CSV
    selectors = [
        f'button[data-qa="analytics_{analytics_type}_csv-header-action"]',
        'button[aria-label="Export CSV"]',
        'button:has-text("Export CSV")',
    ]

    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                await btn.scroll_into_view_if_needed(timeout=2000)
                await btn.click(force=True, timeout=5000)
                await page.wait_for_timeout(WAIT_AFTER_EXPORT_CLICK * 1000)

                # Quick check for error toast
                err = page.locator('.c-toast:has-text("Unable to export")')
                if await err.count() > 0:
                    if verbose:
                        print("[export error toast] ", end="", flush=True)
                    return False

                return True
        except Exception:
            continue

    if verbose:
        print("[no Export btn] ", end="", flush=True)
    return False


async def run_pass(analytics_type, dates, auth_path):
    """Run a full pass for one analytics type across all dates.

    Processes dates in chunks of CHUNK_SIZE: trigger a chunk of exports,
    then collect their CSVs before moving to the next chunk. This avoids
    Slack's server-side rate limit on CSV generation.

    Returns dict mapping date -> parsed CSV data.
    """
    slack_token = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    results = {}
    start_time = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context_options = {}
        if auth_path.exists() and auth_path.stat().st_size > 0:
            try:
                with open(auth_path) as f:
                    json.load(f)
                context_options["storage_state"] = str(auth_path)
            except (json.JSONDecodeError, ValueError):
                pass

        context = await browser.new_context(**context_options)
        page = await context.new_page()

        target_url = f"{SLACK_WORKSPACE_URL}/admin/stats#{analytics_type}"
        print(f"  Navigating to {target_url}")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        if "/signin" in page.url or "Sign in to" in await page.content():
            print("  ERROR: Not authenticated.")
            await browser.close()
            return results

        # Click tab and wait for data table to load
        try:
            await page.click(f'a[data-analytics-tab="{analytics_type}"]', timeout=5000)
            await page.wait_for_timeout(5000)
        except Exception:
            pass

        await page.keyboard.press('Escape')
        await page.wait_for_timeout(1000)

        # Wait for the date dropdown to be present (confirms table loaded)
        if analytics_type == "channels":
            dd_sel = 'div[data-qa="analytics_channels-table-header-filter-button"]'
        else:
            dd_sel = 'div[data-qa="data_table_header-filter-button"]'
        try:
            await page.wait_for_selector(dd_sel, timeout=15000)
            print(f"  Data table loaded (date dropdown visible)")
        except Exception:
            print(f"  WARNING: Date dropdown not found, table may not have loaded")

        csv_type = "channel" if analytics_type == "channels" else "member"
        total_exported = 0
        consecutive_failures = 0

        # Process in chunks
        for chunk_start in range(0, len(dates), CHUNK_SIZE):
            chunk = dates[chunk_start:chunk_start + CHUNK_SIZE]
            chunk_exported = []
            chunk_ts = time.time()

            # Reload page at chunk boundaries to clear UI state
            if chunk_start > 0 or consecutive_failures >= 3:
                print(f"\n  [Reloading page...]")
                await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                try:
                    await page.click(f'a[data-analytics-tab="{analytics_type}"]', timeout=5000)
                    await page.wait_for_timeout(3000)
                except Exception:
                    pass
                await page.keyboard.press('Escape')
                await page.wait_for_timeout(1000)
                try:
                    await page.wait_for_selector(dd_sel, timeout=15000)
                except Exception:
                    print(f"  WARNING: Date dropdown not found after reload")
                consecutive_failures = 0

            # Trigger exports for this chunk
            for j, date_str in enumerate(chunk):
                i = chunk_start + j + 1
                elapsed = time.time() - start_time
                if total_exported > 0:
                    per_date = elapsed / total_exported
                    remaining = (len(dates) - i) * per_date / 60
                else:
                    remaining = 0

                end_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                print(f"  [{i}/{len(dates)}] {date_str} (ETA: {remaining:.0f}m)", end=" ", flush=True)

                try:
                    ok = await set_date_and_export(page, analytics_type, date_str, end_date, verbose=True)
                except Exception as e:
                    print(f"ERROR: {e}")
                    await page.keyboard.press('Escape')
                    await page.wait_for_timeout(1000)
                    consecutive_failures += 1
                    continue

                if not ok:
                    print("SKIP (export failed)")
                    consecutive_failures += 1
                    continue

                chunk_exported.append(date_str)
                consecutive_failures = 0
                total_exported += 1
                print("FIRED")

            if not chunk_exported:
                continue

            # Collect CSVs for this chunk
            # Members take longer to generate than channels
            wait_time = max(20, len(chunk_exported) * 8)
            print(f"  Collecting {len(chunk_exported)} CSVs (waiting {wait_time}s)...", end=" ", flush=True)
            await asyncio.sleep(wait_time)

            matched = batch_collect_csvs(
                slack_token, csv_type, chunk_exported,
                ts_from=chunk_ts, max_pages=5,
            )

            # Retry up to 3 times with increasing wait
            for attempt in range(3):
                missing = [d for d in chunk_exported if d not in matched]
                if not missing:
                    break
                retry_wait = 20 * (attempt + 1)
                await asyncio.sleep(retry_wait)
                retry = batch_collect_csvs(
                    slack_token, csv_type, missing,
                    ts_from=chunk_ts, max_pages=5,
                )
                matched.update(retry)

            # Download and parse
            for date_str, file_info in matched.items():
                try:
                    rows = download_csv(slack_token, file_info)
                    if rows:
                        if analytics_type == "channels":
                            results[date_str] = parse_channels_csv(rows)
                        else:
                            results[date_str] = parse_members_csv(rows)
                except Exception:
                    pass

            chunk_found = len([d for d in chunk_exported if d in results])
            print(f"{chunk_found}/{len(chunk_exported)} collected")

        await context.storage_state(path=str(auth_path))
        await browser.close()

    elapsed = time.time() - start_time
    print(f"\n  Pass complete: {len(results)}/{len(dates)} in {elapsed/60:.1f}m")
    return results


async def backfill(dates_to_process, null_slack_dates, args):
    """Run channels pass, then members pass, then merge and write to DB."""
    supabase_url = os.getenv("SUPABASE_REST_URL", "http://localhost:8000")
    service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    auth_path = Path(os.getenv("SLACK_AUTH_FILE", "./slack_auth_state.json"))

    # --- Pass 1: Channels ---
    if not args.members_only:
        print(f"\n{'='*60}")
        print(f"Pass 1: Channels ({len(dates_to_process)} dates)")
        print(f"{'='*60}")
        channels_results = await run_pass("channels", dates_to_process, auth_path)
        print(f"\nChannels pass: {len(channels_results)}/{len(dates_to_process)} succeeded")
    else:
        channels_results = {}
        print("Skipping channels pass (--members-only)")

    # --- Pass 2: Members ---
    # Only process dates that succeeded in channels pass (or all if members-only)
    if args.members_only:
        member_dates = dates_to_process
    else:
        member_dates = [d for d in dates_to_process if d in channels_results]

    print(f"\n{'='*60}")
    print(f"Pass 2: Members ({len(member_dates)} dates)")
    print(f"{'='*60}")
    members_results = await run_pass("members", member_dates, auth_path)
    print(f"\nMembers pass: {len(members_results)}/{len(member_dates)} succeeded")

    # --- Write to DB ---
    print(f"\n{'='*60}")
    print("Writing to database...")
    print(f"{'='*60}")

    success_count = 0
    for date_str in dates_to_process:
        ch = channels_results.get(date_str)
        mem = members_results.get(date_str)

        if not ch and not mem:
            continue

        updates = {"slack_covers_date": date_str}
        if ch:
            updates["slack_total_messages"] = ch.get("total_messages_posted", 0)
            updates["slack_channels_active"] = ch.get("channels_active", 0)
        if mem:
            updates["slack_members_active"] = mem.get("members_active", 0)

        try:
            if date_str in null_slack_dates:
                db_update(supabase_url, service_key, date_str, updates)
            else:
                slack_data = {
                    "total_messages_posted": updates.get("slack_total_messages", 0),
                    "channels_active": updates.get("slack_channels_active", 0),
                    "members_active": updates.get("slack_members_active", 0),
                }
                db_upsert(supabase_url, service_key, date_str, slack_data)

            msgs = updates.get("slack_total_messages", "?")
            mems = updates.get("slack_members_active", "?")
            print(f"  {date_str}: msgs={msgs}, members={mems}")
            success_count += 1
        except Exception as e:
            print(f"  {date_str}: DB error - {e}")

    return success_count


def main():
    load_env()

    parser = argparse.ArgumentParser(description="Backfill Slack analytics into daily_snapshots")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--existing-only", action="store_true",
                        help="Only update existing snapshots (skip dates not in DB)")
    parser.add_argument("--members-only", action="store_true",
                        help="Skip channels, only do members pass")
    parser.add_argument("--limit", type=int, default=0, help="Max dates to process (0=all)")
    args = parser.parse_args()

    slack_token = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    supabase_url = os.getenv("SUPABASE_REST_URL", "http://localhost:8000")

    if not slack_token:
        print("ERROR: SLACK_MCP_XOXP_TOKEN not set")
        return 1
    if not service_key:
        print("ERROR: SUPABASE_SERVICE_KEY not set")
        return 1

    start = args.start or SLACK_DATA_START
    end = args.end or datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print("Slack Analytics Backfill")
    print(f"{'='*60}")
    print(f"Date range: {start} to {end}")

    null_slack_dates = set(get_dates_needing_slack(supabase_url, service_key, start, end))
    print(f"Existing snapshots needing Slack data: {len(null_slack_dates)}")

    if args.existing_only:
        dates_to_process = sorted(null_slack_dates)
    else:
        dates_to_process = generate_workdays(start, end)

    if args.limit > 0:
        dates_to_process = dates_to_process[:args.limit]

    print(f"Total dates to process: {len(dates_to_process)}")

    if args.dry_run:
        print("\n[DRY RUN] Would process:")
        for d in dates_to_process[:20]:
            status = "UPDATE" if d in null_slack_dates else "INSERT"
            print(f"  {d} ({status})")
        if len(dates_to_process) > 20:
            print(f"  ... and {len(dates_to_process) - 20} more")
        return 0

    # ~15s per date per pass (9s trigger + 6s collection overhead)
    est_minutes = len(dates_to_process) * 15 * 2 / 60
    print(f"Estimated time: ~{est_minutes:.0f} minutes")
    print(f"{'='*60}")

    success = asyncio.run(backfill(dates_to_process, null_slack_dates, args))

    print(f"\n{'='*60}")
    print(f"Backfill Complete: {success} dates written to DB")
    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
