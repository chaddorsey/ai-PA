"""Slack CLI entry point."""
import click


@click.group()
@click.option("--format", "format_flag", type=click.Choice(["json", "text", "csv", "yaml"]), default=None,
              help="Output format (default: json)")
@click.option("--body", "body_json", default=None, help="Raw JSON input (agent-first path)")
@click.option("--dry-run", is_flag=True, default=False, help="Validate + preview, no execution")
@click.option("--fields", default=None, help="Comma-separated output fields")
@click.option("--page-all", is_flag=True, default=False, help="Auto-paginate through all results")
@click.option("--page-limit", default=10, type=int, help="Max pages when paginating (default: 10)")
@click.option("--as-user", is_flag=True, default=False, help="Force user token (xoxp)")
@click.option("--as-bot", is_flag=True, default=False, help="Force bot token (xoxb)")
@click.version_option(version="0.1.0")
@click.pass_context
def cli(ctx, format_flag, body_json, dry_run, fields, page_all, page_limit, as_user, as_bot):
    """Slack CLI - manage messages, channels, users, and more."""
    ctx.ensure_object(dict)
    ctx.obj["format"] = format_flag
    ctx.obj["body"] = body_json
    ctx.obj["dry_run"] = dry_run
    ctx.obj["fields"] = fields.split(",") if fields else None
    ctx.obj["page_all"] = page_all
    ctx.obj["page_limit"] = page_limit
    ctx.obj["as_user"] = as_user
    ctx.obj["as_bot"] = as_bot
