"""Slack CLI entry point."""
import json
import sys

import click

from slack_cli.client import SlackClient
from slack_cli.error import SlackCliError, EXIT_VALIDATION, EXIT_SUCCESS, format_error
from slack_cli.formatter import format_output, apply_field_mask
from slack_cli.schema import get_schema
from slack_cli.validate import validate_body, validate_semantic


def _run(ctx, schema_key: str, params: dict, had_convenience_flags: bool = False):
    """Core execution helper. Every command routes through this.

    1. If --body provided: parse JSON, validate against schema
    2. If --body AND convenience flags: warn to stderr, use --body
    3. If no --body: use params from convenience flags
    4. Validation errors -> stdout JSON, exit 2
    5. --dry-run -> stdout JSON preview, exit 0 (valid) or 2 (invalid)
    6. Otherwise: call client and output result
    """
    body_json = ctx.obj.get("body")
    dry_run = ctx.obj.get("dry_run", False)
    format_flag = ctx.obj.get("format")
    fields = ctx.obj.get("fields")
    as_user = ctx.obj.get("as_user", False)
    as_bot = ctx.obj.get("as_bot", False)

    # Resolve params from --body or convenience flags
    if body_json is not None:
        if had_convenience_flags:
            click.echo("Warning: --body provided; ignoring convenience flags", err=True)
        try:
            body = json.loads(body_json)
        except json.JSONDecodeError as e:
            click.echo(format_error("invalid_json", str(e)))
            sys.exit(EXIT_VALIDATION)
            return
        merged = body
    else:
        merged = params

    # Validate against schema
    schema = get_schema(schema_key)
    errors = []
    if schema:
        errors.extend(validate_body(merged, schema["params"]))
        errors.extend(validate_semantic(merged, schema["params"]))

    if errors:
        click.echo(json.dumps({"ok": False, "error": "validation_failed", "errors": errors}, indent=2))
        sys.exit(EXIT_VALIDATION)
        return

    # Dry run
    if dry_run:
        token_type = schema["token_type"] if schema else "either"
        preview = {
            "method": schema_key,
            "token_type": token_type,
            "params": merged,
            "url": f"https://slack.com/api/{schema_key}",
            "validation": "passed",
        }
        click.echo(json.dumps(preview, indent=2))
        return

    # Execute
    try:
        client = SlackClient(force_user=as_user, force_bot=as_bot)

        page_all = ctx.obj.get("page_all", False)
        page_limit = ctx.obj.get("page_limit", 10)

        if page_all:
            pages = client.paginate(schema_key, merged, max_pages=page_limit)
            for page in pages:
                masked = apply_field_mask(page, fields)
                click.echo(format_output(masked, format_flag or "json"))
        else:
            result = client.call(schema_key, merged)
            masked = apply_field_mask(result, fields)
            click.echo(format_output(masked, format_flag or "json"))

    except SlackCliError as e:
        click.echo(e.to_json())
        if e.hint:
            click.echo(f"Hint: {e.hint}", err=True)
        sys.exit(e.exit_code)


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


# ── conversations command group ──────────────────────────────────────────────


@cli.group()
def conversations():
    """Manage channels and conversations."""


@conversations.command("list")
@click.option("--types", default=None, help="Comma-separated channel types (public_channel, private_channel, mpim, im)")
@click.option("--limit", type=int, default=None, help="Max results per page")
@click.option("--exclude-archived", is_flag=True, default=None, help="Exclude archived channels")
@click.option("--cursor", default=None, help="Pagination cursor")
@click.pass_context
def conversations_list(ctx, types, limit, exclude_archived, cursor):
    """List channels in the workspace."""
    params = {k: v for k, v in {
        "types": types, "limit": limit,
        "exclude_archived": exclude_archived, "cursor": cursor,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [types, limit, exclude_archived, cursor])
    _run(ctx, "conversations.list", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("info")
@click.option("--channel", default=None, help="Channel ID to get info on")
@click.pass_context
def conversations_info(ctx, channel):
    """Get information about a conversation."""
    params = {k: v for k, v in {"channel": channel}.items() if v is not None}
    had_flags = channel is not None
    _run(ctx, "conversations.info", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("history")
@click.option("--channel", default=None, help="Channel ID to fetch history for")
@click.option("--oldest", default=None, help="Only messages after this Unix timestamp")
@click.option("--latest", default=None, help="Only messages before this Unix timestamp")
@click.option("--limit", type=int, default=None, help="Max results per page")
@click.option("--inclusive", is_flag=True, default=None, help="Include messages with oldest or latest timestamps")
@click.option("--cursor", default=None, help="Pagination cursor")
@click.pass_context
def conversations_history(ctx, channel, oldest, latest, limit, inclusive, cursor):
    """Fetch message history of a conversation."""
    params = {k: v for k, v in {
        "channel": channel, "oldest": oldest, "latest": latest,
        "limit": limit, "inclusive": inclusive, "cursor": cursor,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, oldest, latest, limit, inclusive, cursor])
    _run(ctx, "conversations.history", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("create")
@click.option("--name", default=None, help="Name of the channel to create")
@click.option("--is-private", is_flag=True, default=None, help="Create a private channel")
@click.pass_context
def conversations_create(ctx, name, is_private):
    """Create a new channel."""
    params = {k: v for k, v in {
        "name": name, "is_private": is_private,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [name, is_private])
    _run(ctx, "conversations.create", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("archive")
@click.option("--channel", default=None, help="Channel ID to archive")
@click.pass_context
def conversations_archive(ctx, channel):
    """Archive a conversation."""
    params = {k: v for k, v in {"channel": channel}.items() if v is not None}
    had_flags = channel is not None
    _run(ctx, "conversations.archive", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("unarchive")
@click.option("--channel", default=None, help="Channel ID to unarchive")
@click.pass_context
def conversations_unarchive(ctx, channel):
    """Unarchive a conversation."""
    params = {k: v for k, v in {"channel": channel}.items() if v is not None}
    had_flags = channel is not None
    _run(ctx, "conversations.unarchive", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("invite")
@click.option("--channel", default=None, help="Channel ID to invite users to")
@click.option("--users", default=None, help="Comma-separated list of user IDs to invite")
@click.pass_context
def conversations_invite(ctx, channel, users):
    """Invite users to a conversation."""
    params = {k: v for k, v in {"channel": channel, "users": users}.items() if v is not None}
    had_flags = any(v is not None for v in [channel, users])
    _run(ctx, "conversations.invite", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("kick")
@click.option("--channel", default=None, help="Channel ID to remove user from")
@click.option("--user", default=None, help="User ID to remove")
@click.pass_context
def conversations_kick(ctx, channel, user):
    """Remove a user from a conversation."""
    params = {k: v for k, v in {"channel": channel, "user": user}.items() if v is not None}
    had_flags = any(v is not None for v in [channel, user])
    _run(ctx, "conversations.kick", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("join")
@click.option("--channel", default=None, help="Channel ID to join")
@click.pass_context
def conversations_join(ctx, channel):
    """Join an existing conversation."""
    params = {k: v for k, v in {"channel": channel}.items() if v is not None}
    had_flags = channel is not None
    _run(ctx, "conversations.join", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("leave")
@click.option("--channel", default=None, help="Channel ID to leave")
@click.pass_context
def conversations_leave(ctx, channel):
    """Leave a conversation."""
    params = {k: v for k, v in {"channel": channel}.items() if v is not None}
    had_flags = channel is not None
    _run(ctx, "conversations.leave", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("open")
@click.option("--channel", default=None, help="Resume a conversation by its channel ID")
@click.option("--users", default=None, help="Comma-separated list of user IDs to open a DM with")
@click.pass_context
def conversations_open(ctx, channel, users):
    """Open or resume a direct message or multi-person direct message."""
    params = {k: v for k, v in {"channel": channel, "users": users}.items() if v is not None}
    had_flags = any(v is not None for v in [channel, users])
    _run(ctx, "conversations.open", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("close")
@click.option("--channel", default=None, help="Channel ID to close")
@click.pass_context
def conversations_close(ctx, channel):
    """Close a direct message or multi-person direct message."""
    params = {k: v for k, v in {"channel": channel}.items() if v is not None}
    had_flags = channel is not None
    _run(ctx, "conversations.close", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("members")
@click.option("--channel", default=None, help="Channel ID to fetch members for")
@click.option("--limit", type=int, default=None, help="Max results per page")
@click.option("--cursor", default=None, help="Pagination cursor")
@click.pass_context
def conversations_members(ctx, channel, limit, cursor):
    """List members of a conversation."""
    params = {k: v for k, v in {
        "channel": channel, "limit": limit, "cursor": cursor,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, limit, cursor])
    _run(ctx, "conversations.members", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("rename")
@click.option("--channel", default=None, help="Channel ID to rename")
@click.option("--name", default=None, help="New name for the conversation")
@click.pass_context
def conversations_rename(ctx, channel, name):
    """Rename a conversation."""
    params = {k: v for k, v in {"channel": channel, "name": name}.items() if v is not None}
    had_flags = any(v is not None for v in [channel, name])
    _run(ctx, "conversations.rename", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("setPurpose")
@click.option("--channel", default=None, help="Channel ID to set purpose for")
@click.option("--purpose", default=None, help="The new purpose for the conversation")
@click.pass_context
def conversations_set_purpose(ctx, channel, purpose):
    """Set the purpose for a conversation."""
    params = {k: v for k, v in {"channel": channel, "purpose": purpose}.items() if v is not None}
    had_flags = any(v is not None for v in [channel, purpose])
    _run(ctx, "conversations.setPurpose", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("setTopic")
@click.option("--channel", default=None, help="Channel ID to set topic for")
@click.option("--topic", default=None, help="The new topic for the conversation")
@click.pass_context
def conversations_set_topic(ctx, channel, topic):
    """Set the topic for a conversation."""
    params = {k: v for k, v in {"channel": channel, "topic": topic}.items() if v is not None}
    had_flags = any(v is not None for v in [channel, topic])
    _run(ctx, "conversations.setTopic", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)
