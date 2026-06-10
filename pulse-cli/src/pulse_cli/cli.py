"""
pulse — agent-first CLI for pulse-monitor analytics ops.

Wraps the bespoke pulse Python tools extracted from Letta to
`letta/pulse-tools/`. Same Option-1 pattern as task-cli:

- One implementation, two interfaces (Letta tool registration retained
  on Docker for rollback; local-mode agent calls the CLI)
- Bug fixes land in one place (the underlying Python file)
- After pulse soak passes, relocate Python from `letta/pulse-tools/`
  to `pulse-cli/src/pulse_cli/lib/` (see task-cli followup for the
  same pattern)

The wrapped tools currently read/write Letta memory blocks
(drive_analytics_*) — that substrate is deprecated but functional
during the transition. A separate substrate migration (blocks →
pa_web analytics schema) is queued as soak-phase work; see
`docs/followups/2026-05-30-pulse-cli-scoping.md`.
"""

import json
import os
import sys
from pathlib import Path

import click


# ─── locate the wrapped Python implementations ──────────────────────────────
_REPO_ROOT = Path(
    os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
).resolve()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Add pulse-tools dir so imports `from collect_analytics_snapshot import ...`
# work — the tools were extracted as flat .py files (no package layout).
_PULSE_TOOLS = _REPO_ROOT / "letta" / "pulse-tools"
if _PULSE_TOOLS.exists() and str(_PULSE_TOOLS) not in sys.path:
    sys.path.insert(0, str(_PULSE_TOOLS))


def _emit_json(obj):
    """Dump a tool-return dict to stdout as JSON. Exit non-zero on error."""
    click.echo(json.dumps(obj, indent=2, default=str))
    if isinstance(obj, dict) and obj.get("status") == "error":
        sys.exit(2)


def _ensure_env():
    """Provide the env the wrapped tools expect.

    The original Letta tools ran inside the letta container and read
    LETTA_BASE_URL=http://localhost:8283. For local-mode invocation
    from host, we point at the host-mapped port; the wrapper script
    (~/bin/letta-pulse) sets this explicitly.
    """
    if "LETTA_BASE_URL" not in os.environ:
        os.environ["LETTA_BASE_URL"] = "http://localhost:8283"


# ─── click root group ───────────────────────────────────────────────────────


@click.group()
def cli():
    """pulse — agent-first CLI for pulse-monitor analytics ops.

    Wraps the bespoke Python from `letta/pulse-tools/`. JSON output by
    default. The wrapped tools currently read Letta memory blocks
    (drive_analytics_*) for stored state — that substrate is
    deprecated but functional during transition.

    Env:
      PA_AI_REPO_ROOT      path to ai-PA repo (default: /Volumes/main-drive/ai-PA)
      LETTA_BASE_URL       Letta API for block reads (default: http://localhost:8283)
      GITEA_BASE_URL       Canonical reads via Bash+curl
      GITEA_MEMFS_TOKEN    Canonical auth
      POSTGRES_PASSWORD    pa_web reads
    """
    _ensure_env()


# ─── briefing composition ──────────────────────────────────────────────────


@cli.command(name="compose-briefing")
@click.option("--date", default=None, help="ISO date (YYYY-MM-DD); defaults to today ET")
def compose_briefing(date):
    """Compose the daily analytics briefing.

    Reads from analytics.daily_snapshots + slack vibe-check summaries
    + Drive trends, computes deltas, emits canonical signal.
    """
    from compose_daily_briefing import compose_daily_briefing
    kwargs = {"date": date} if date else {}
    _emit_json(compose_daily_briefing(**kwargs))


# ─── analytics snapshot ────────────────────────────────────────────────────


@cli.command(name="snapshot")
@click.option("--date", default=None, help="ISO date for the snapshot")
def snapshot(date):
    """Collect quantitative analytics snapshot to pa_web."""
    from collect_analytics_snapshot import collect_analytics_snapshot
    kwargs = {"date": date} if date else {}
    _emit_json(collect_analytics_snapshot(**kwargs))


# ─── slack analytics CSV pipeline (already had slack-extract; expose canonical interface here too) ──


@cli.command(name="slack-trigger")
@click.option("--analytics-type", default="channels",
              type=click.Choice(["channels", "members", "messages", "overview"]))
def slack_trigger(analytics_type):
    """Trigger a Slack analytics CSV export via Playwright."""
    from trigger_slack_analytics_export import trigger_slack_analytics_export
    _emit_json(trigger_slack_analytics_export(analytics_type=analytics_type))


@cli.command(name="slack-download")
@click.option("--url", required=True, help="Slack file URL to download")
@click.option("--output", default=None, help="Output path")
def slack_download(url, output):
    """Download a Slack analytics CSV by URL."""
    from download_slack_analytics_file import download_slack_analytics_file
    kwargs = {"file_url": url}
    if output:
        kwargs["output_path"] = output
    _emit_json(download_slack_analytics_file(**kwargs))


@cli.command(name="slack-analyze")
@click.option("--url", required=True, help="Slack file URL of the CSV to analyze")
def slack_analyze(url):
    """Parse + summarize a Slack analytics CSV."""
    from analyze_slack_analytics import analyze_slack_analytics
    _emit_json(analyze_slack_analytics(file_url=url))


# ─── drive analytics — collectors ─────────────────────────────────────────


@cli.command(name="drive-workspace")
@click.option("--date", default=None)
def drive_workspace(date):
    """Collect workspace-wide Drive activity for a date (Admin Reports API)."""
    from collect_daily_workspace_activity import collect_daily_workspace_activity
    kwargs = {"date": date} if date else {}
    _emit_json(collect_daily_workspace_activity(**kwargs))


@cli.command(name="drive-personal")
@click.option("--date", default=None)
def drive_personal(date):
    """Collect personal Drive activity for a date (Drive Activity API)."""
    from collect_daily_personal_activity import collect_daily_personal_activity
    kwargs = {"date": date} if date else {}
    _emit_json(collect_daily_personal_activity(**kwargs))


@cli.command(name="drive-mentions")
@click.option("--date", default=None)
def drive_mentions(date):
    """Collect @mentions of Chad in Drive comments for a date."""
    from collect_daily_mentions import collect_daily_mentions
    kwargs = {"date": date} if date else {}
    _emit_json(collect_daily_mentions(**kwargs))


# ─── drive analytics — readers (over stored block state) ──────────────────


@cli.command(name="drive-averages")
def drive_averages():
    """Compute 3/10/50-day running averages from stored daily logs."""
    from calculate_running_averages import calculate_running_averages
    _emit_json(calculate_running_averages())


@cli.command(name="drive-summary")
@click.option("--date", default=None)
def drive_summary(date):
    """Summary of Drive activity for a period or date."""
    from get_drive_analytics_summary import get_drive_analytics_summary
    kwargs = {"date": date} if date else {}
    _emit_json(get_drive_analytics_summary(**kwargs))


@cli.command(name="drive-mentions-read")
@click.option("--date", default=None)
@click.option("--lookback-days", default=None, type=int)
def drive_mentions_read(date, lookback_days):
    """Read @mentions from stored state for a date range or lookback."""
    from get_drive_mentions import get_drive_mentions
    kwargs = {}
    if date:
        kwargs["date"] = date
    if lookback_days:
        kwargs["lookback_days"] = lookback_days
    _emit_json(get_drive_mentions(**kwargs))


@cli.command(name="drive-trends")
def drive_trends():
    """Drive activity trends from stored running averages."""
    from get_drive_trends import get_drive_trends
    _emit_json(get_drive_trends())


# ─── drive — current state / queries (not analytics) ─────────────────────


@cli.command(name="drive-files")
@click.option("--query", default=None, help="Filter expression (e.g., name contains 'X')")
@click.option("--limit", default=20, type=int)
def drive_files(query, limit):
    """List Drive files matching a query."""
    from get_drive_documents import get_drive_documents
    kwargs = {"limit": limit}
    if query:
        kwargs["query"] = query
    _emit_json(get_drive_documents(**kwargs))


@cli.command(name="drive-info")
@click.argument("file_id_or_url")
def drive_info(file_id_or_url):
    """Get metadata for a specific Drive file."""
    from get_drive_file_info import get_drive_file_info
    _emit_json(get_drive_file_info(file_id_or_url=file_id_or_url))


@cli.command(name="drive-top")
@click.option("--days", default=7, type=int)
@click.option("--limit", default=10, type=int)
def drive_top(days, limit):
    """Top documents by activity in the last N days."""
    from get_top_documents import get_top_documents
    _emit_json(get_top_documents(days=days, limit=limit))


@cli.command(name="drive-my-activity")
@click.option("--date", default=None)
def drive_my_activity(date):
    """My Drive activity for a date."""
    from get_my_drive_activity import get_my_drive_activity
    kwargs = {"date": date} if date else {}
    _emit_json(get_my_drive_activity(**kwargs))


@cli.command(name="drive-recent")
@click.option("--hours", default=24, type=int)
def drive_recent(hours):
    """My recent Drive activity (last N hours)."""
    from get_recent_my_activity import get_recent_my_activity
    _emit_json(get_recent_my_activity(hours=hours))


@cli.command(name="drive-doc-events")
@click.argument("file_id_or_url")
def drive_doc_events(file_id_or_url):
    """Event timeline for a specific document."""
    from get_document_events import get_document_events
    _emit_json(get_document_events(file_id_or_url=file_id_or_url))


@cli.command(name="drive-activity-search")
@click.option("--query", required=True)
@click.option("--days", default=7, type=int)
def drive_activity_search(query, days):
    """Search Drive activity by query."""
    from search_drive_activity import search_drive_activity
    _emit_json(search_drive_activity(query=query, days=days))


# ─── email analytics ──────────────────────────────────────────────────────


@cli.command(name="email-analytics")
@click.option("--date", default=None)
def email_analytics(date):
    """Daily email analytics summary."""
    from get_email_analytics import get_email_analytics
    kwargs = {"date": date} if date else {}
    _emit_json(get_email_analytics(**kwargs))


# ─── initialization helper ────────────────────────────────────────────────


@cli.command(name="init-drive-memory")
def init_drive_memory():
    """Initialize the drive_analytics_* memory blocks (first-time setup)."""
    from initialize_drive_analytics_memory import initialize_drive_analytics_memory
    _emit_json(initialize_drive_analytics_memory())


# ─── health ──────────────────────────────────────────────────────────────


@cli.command()
def health():
    """Probe Letta + canonical + analytics connectivity."""
    import urllib.request, urllib.error
    status = {"status": "healthy", "checks": {}}
    # Letta API
    try:
        with urllib.request.urlopen(f"{os.environ['LETTA_BASE_URL']}/v1/health", timeout=5) as r:
            status["checks"]["letta_api"] = "ok" if r.status == 200 else f"status {r.status}"
    except Exception as e:
        status["checks"]["letta_api"] = f"error: {e}"
        status["status"] = "unhealthy"
    # Gitea (canonical)
    try:
        with urllib.request.urlopen(
            f"{os.environ.get('GITEA_BASE_URL', 'http://127.0.0.1:3030')}/api/v1/version",
            timeout=5,
        ) as r:
            status["checks"]["gitea"] = "ok" if r.status == 200 else f"status {r.status}"
    except Exception as e:
        status["checks"]["gitea"] = f"error: {e}"
        status["status"] = "unhealthy"
    _emit_json(status)


if __name__ == "__main__":
    cli()
