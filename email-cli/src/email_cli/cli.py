"""
email-agent — agent-first CLI for email-agent ops.

Wraps the bespoke email Python tools extracted from Letta to
`letta/email-tools/`. Same Option-1 pattern as task-cli + pulse-cli:

- One implementation, two interfaces (Letta tool registration on Docker
  for rollback; local agent calls `email-agent <verb>` via Bash)
- Bug fixes land once
- Post-soak relocate `letta/email-tools/` → `email-cli/src/email_cli/lib/`

Binary name is `email-agent` (not `email`) to avoid shadowing the
`/usr/bin/email` POSIX util on some systems.

Ad-hoc Gmail/Calendar/Drive ops continue via the `gws` CLI on PATH.
TaskQueue → pa_web.task_queue claims go via `task queue-claim --source email`.
"""

import json
import os
import sys
from pathlib import Path

import click


_REPO_ROOT = Path(
    os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
).resolve()
_EMAIL_TOOLS = _REPO_ROOT / "letta" / "email-tools"
if _EMAIL_TOOLS.exists() and str(_EMAIL_TOOLS) not in sys.path:
    sys.path.insert(0, str(_EMAIL_TOOLS))


def _emit_json(obj):
    click.echo(json.dumps(obj, indent=2, default=str))
    if isinstance(obj, dict) and obj.get("status") == "error":
        sys.exit(2)


def _ensure_env():
    if "LETTA_BASE_URL" not in os.environ:
        os.environ["LETTA_BASE_URL"] = "http://localhost:8283"


@click.group()
def cli():
    """email-agent — Gmail thread watch + TaskQueue label processing.

    JSON output by default. Wraps letta/email-tools/*.py.

    Env:
      PA_AI_REPO_ROOT      path to ai-PA repo (default: /Volumes/main-drive/ai-PA)
      LETTA_BASE_URL       Letta API for any remaining block reads
                           (default: http://localhost:8283)
    """
    _ensure_env()


@cli.command(name="watch")
@click.argument("thread_id")
@click.option("--subject", default=None)
@click.option("--recipients", default=None,
              help="Comma-separated recipient emails.")
@click.option("--followup-interval", default=None,
              help="Follow-up reminder interval e.g. '3d', '12h', '1w'.")
@click.option("--context", default=None,
              help="Additional context about why this thread is being watched.")
def watch(thread_id, subject, recipients, followup_interval, context):
    """Start watching a Gmail thread for replies."""
    from watch_gmail_thread import watch_gmail_thread
    kwargs = {"thread_id": thread_id}
    for k, v in [("subject", subject), ("recipients", recipients),
                 ("followup_interval", followup_interval), ("context", context)]:
        if v is not None:
            kwargs[k] = v
    _emit_json(watch_gmail_thread(**kwargs))


@cli.command(name="unwatch")
@click.argument("thread_id")
def unwatch(thread_id):
    """Stop watching a Gmail thread."""
    from unwatch_gmail_thread import unwatch_gmail_thread
    _emit_json(unwatch_gmail_thread(thread_id=thread_id))


@cli.command(name="watch-status")
@click.argument("thread_id")
def watch_status(thread_id):
    """Get detailed status of a watched Gmail thread."""
    from get_gmail_watch_status import get_gmail_watch_status
    _emit_json(get_gmail_watch_status(thread_id=thread_id))


@cli.command(name="watch-list")
def watch_list():
    """List all currently-watched Gmail threads."""
    from list_watched_gmail_threads import list_watched_gmail_threads
    _emit_json(list_watched_gmail_threads())


@cli.command(name="process-queue")
@click.option("--max-messages", default=10, show_default=True, type=int,
              help="Max TaskQueue-labeled messages to process per call (1-20).")
def process_queue(max_messages):
    """Process Gmail TaskQueue-labeled messages and queue for task extraction.

    Searches Gmail for the TaskQueue label, parses forward-with-notes vs
    direct-label messages, queues each as a row in pa_web.task_queue
    (source='email') — Tasks agent picks up via `task queue-claim --source email`.
    """
    from process_email_task_queue import process_email_task_queue
    _emit_json(process_email_task_queue(max_messages=max_messages))


@cli.command()
def health():
    """Probe gmail-watch-service connectivity."""
    import urllib.request, urllib.error, json as _json
    status = {"status": "healthy", "checks": {}}
    try:
        url = "http://gmail-watch-service:8000/mcp"
        # MCP health: send a tools/list request
        req = urllib.request.Request(
            url, data=_json.dumps({"name": "list_watched_threads", "arguments": {}}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            status["checks"]["gmail_watch_service"] = "ok" if r.status == 200 else f"status {r.status}"
    except Exception as e:
        status["checks"]["gmail_watch_service"] = f"error: {e}"
        status["status"] = "unhealthy"
    _emit_json(status)


if __name__ == "__main__":
    cli()
