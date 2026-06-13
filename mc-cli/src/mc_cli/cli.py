"""mc — local-mode CLI for Mission Control.

Replaces 4 bespoke Letta tools with Bash-callable subcommands:
  - mc laptop    — execute_on_laptop (SSH over Tailscale)
  - mc widget    — manage_widget_queue (OmniFocus timer widget)
  - mc stage     — stage_resource (download to staging dir)
  - mc github    — search_github_stars (GraphQL)

All four tool sources live in /Volumes/main-drive/ai-PA/letta/mc-tools/
and are imported here. Same pattern as pulse-cli + email-cli.
"""

import json
import os
import sys
from pathlib import Path

import click

# Path setup so we can import the extracted tool sources without
# making them an installable subpackage (they're Letta-format
# stand-alone functions with imports inside the body).
REPO_ROOT = Path(os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA"))
TOOLS_DIR = REPO_ROOT / "letta" / "mc-tools"
sys.path.insert(0, str(TOOLS_DIR))


def _ensure_env_from_dotenv(*keys: str) -> None:
    """Backfill missing env vars from REPO_ROOT/.env.

    The launchd local-runner starts agents with a minimal environment that does
    NOT source .env or pa-tools.env, so secrets like GITHUB_TOKEN are absent —
    the same runner-env trap that bit twitter-cli. Reading them straight from the
    repo .env makes `mc` behave identically whether launched from an interactive
    shell or the runner, with the secret living in exactly one place.
    """
    missing = [k for k in keys if not os.environ.get(k)]
    if not missing:
        return
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key in missing and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")
    except OSError:
        pass


@click.group()
def cli() -> None:
    """Mission Control local-mode CLI."""


# ---------------------------------------------------------------------------
# laptop — execute_on_laptop
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("command", required=True)
@click.option("--applescript", is_flag=True, help="Execute as AppleScript via osascript")
def laptop(command: str, applescript: bool) -> None:
    """Execute a command on the laptop via SSH over Tailscale."""
    from execute_on_laptop import execute_on_laptop  # type: ignore
    out = execute_on_laptop(command=command, use_applescript=applescript)
    click.echo(out)


# ---------------------------------------------------------------------------
# widget — manage_widget_queue
# ---------------------------------------------------------------------------

@cli.command()
@click.argument(
    "action",
    type=click.Choice(["list", "set", "push", "insert", "remove", "move", "clear"]),
)
@click.option("--task-ids", help="Comma-separated OmniFocus task IDs")
@click.option("--position", type=int, help="0-indexed position (for insert/move)")
def widget(action: str, task_ids: str, position: int) -> None:
    """Manage the OmniFocus timer widget queue on the laptop."""
    from manage_widget_queue import manage_widget_queue  # type: ignore
    result = manage_widget_queue(
        action=action,
        task_ids=task_ids,
        position=position,
    )
    click.echo(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# stage — stage_resource
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--url", required=True, help="Source URL, Drive URL, or 'gmail:MSG_ID'")
@click.option("--label", required=True, help="Short descriptive label")
@click.option(
    "--priority",
    type=click.Choice(["primary", "secondary", "background"]),
    default="secondary",
)
@click.option("--ref-id", help="Optional 8-char hex ref_id (task association)")
def stage(url: str, label: str, priority: str, ref_id: str) -> None:
    """Download a resource to the staging directory."""
    from stage_resource import stage_resource  # type: ignore
    result = stage_resource(
        url=url,
        label=label,
        priority=priority,
        ref_id=ref_id,
    )
    click.echo(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# github — search_github_stars
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--query", help="Keyword search across name/description/topics")
@click.option("--repo", help="Specific repo lookup (owner/name)")
@click.option("--readme", is_flag=True, help="Include README content")
@click.option("--limit", type=int, default=10, show_default=True)
@click.option("--cursor", help="Pagination cursor (browse mode only)")
def github(query: str, repo: str, readme: bool, limit: int, cursor: str) -> None:
    """Search starred GitHub repositories."""
    _ensure_env_from_dotenv("GITHUB_TOKEN")
    from search_github_stars import search_github_stars  # type: ignore
    result = search_github_stars(
        query=query,
        repo=repo,
        readme=readme if readme else None,
        limit=limit,
        cursor=cursor,
    )
    click.echo(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# health — quick probe that subcommand imports + critical env work
# ---------------------------------------------------------------------------

@cli.command()
def health() -> None:
    """Probe import + env health for mc-cli."""
    status = {"status": "ok", "checks": {}}
    for name in ["execute_on_laptop", "manage_widget_queue", "stage_resource", "search_github_stars"]:
        try:
            __import__(name)
            status["checks"][name] = "import-ok"
        except Exception as e:
            status["checks"][name] = f"import-error: {e}"
            status["status"] = "degraded"

    env_required = ["GITHUB_TOKEN"]  # only the truly required-at-call-time one
    for v in env_required:
        if os.environ.get(v):
            status["checks"][f"env:{v}"] = "set"
        else:
            _ensure_env_from_dotenv(v)  # mirror what `mc github` does at call time
            if os.environ.get(v):
                status["checks"][f"env:{v}"] = "set (via .env fallback)"
            else:
                status["checks"][f"env:{v}"] = "MISSING (only needed for `mc github`)"

    click.echo(json.dumps(status, indent=2))
    sys.exit(0 if status["status"] == "ok" else 1)


if __name__ == "__main__":
    cli()
