"""Slack CLI entry point."""
import json
import sys

import click

from slack_cli.client import SlackClient
from slack_cli.error import SlackCliError, EXIT_VALIDATION, EXIT_EXECUTION, EXIT_SUCCESS, format_error
from slack_cli.formatter import format_output, apply_field_mask
from slack_cli.schema import get_schema
from slack_cli.validate import validate_body, validate_semantic


# Global options that can appear anywhere in the command line (before or after subcommands).
# Click normally requires group options before the subcommand name. This custom Group class
# extracts these options from any position so agents can write natural commands like:
#   slack conversations list --body '{"limit":5}' --format json
# instead of requiring:
#   slack --body '{"limit":5}' --format json conversations list
GLOBAL_OPTIONS = {
    "--format": {"nargs": 1, "key": "format"},
    "--body": {"nargs": 1, "key": "body"},
    "--dry-run": {"nargs": 0, "key": "dry_run"},
    "--fields": {"nargs": 1, "key": "fields"},
    "--page-all": {"nargs": 0, "key": "page_all"},
    "--page-limit": {"nargs": 1, "key": "page_limit"},
    "--as-user": {"nargs": 0, "key": "as_user"},
    "--as-bot": {"nargs": 0, "key": "as_bot"},
}


class GlobalOptionsGroup(click.Group):
    """Click Group that allows global options to appear anywhere in the command line."""

    def parse_args(self, ctx, args):
        """Extract global options from args before normal parsing."""
        remaining = []
        i = 0
        extracted = {}
        while i < len(args):
            arg = args[i]
            if arg in GLOBAL_OPTIONS:
                opt = GLOBAL_OPTIONS[arg]
                if opt["nargs"] == 0:
                    extracted[opt["key"]] = True
                    i += 1
                elif opt["nargs"] == 1 and i + 1 < len(args):
                    extracted[opt["key"]] = args[i + 1]
                    i += 2
                else:
                    remaining.append(arg)
                    i += 1
            else:
                remaining.append(arg)
                i += 1

        # Store extracted globals for apply after normal parsing
        ctx.ensure_object(dict)
        ctx.obj["_extracted_globals"] = extracted
        return super().parse_args(ctx, remaining)


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


@click.group(cls=GlobalOptionsGroup)
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

    # Merge any global options that appeared after subcommand names
    extracted = ctx.obj.pop("_extracted_globals", {})
    if "format" in extracted:
        ctx.obj["format"] = extracted["format"]
    if "body" in extracted:
        ctx.obj["body"] = extracted["body"]
    if "dry_run" in extracted:
        ctx.obj["dry_run"] = True
    if "fields" in extracted:
        ctx.obj["fields"] = extracted["fields"].split(",")
    if "page_all" in extracted:
        ctx.obj["page_all"] = True
    if "page_limit" in extracted:
        ctx.obj["page_limit"] = int(extracted["page_limit"])
    if "as_user" in extracted:
        ctx.obj["as_user"] = True
    if "as_bot" in extracted:
        ctx.obj["as_bot"] = True


# ── conversations command group ──────────────────────────────────────────────


@cli.group(cls=GlobalOptionsGroup)
def conversations():
    """Manage channels and conversations."""


@conversations.command("+find")
@click.option("--name", required=True, help="Channel name substring to search for")
@click.pass_context
def conversations_find_helper(ctx, name):
    """Find channels by name (fuzzy match)."""
    format_flag = ctx.obj.get("format")
    fields = ctx.obj.get("fields")
    as_user = ctx.obj.get("as_user", False)
    as_bot = ctx.obj.get("as_bot", False)

    try:
        client = SlackClient(force_user=as_user, force_bot=as_bot)
        result = client.call("conversations.list", {"types": "public_channel,private_channel", "limit": 1000})
        channels = result.get("channels", [])
        matches = [c for c in channels if name.lower() in c.get("name", "").lower()]

        output_data = {"ok": True, "channels": matches, "count": len(matches)}
        masked = apply_field_mask(output_data, fields)
        click.echo(format_output(masked, format_flag or "json"))

    except SlackCliError as e:
        click.echo(e.to_json())
        if e.hint:
            click.echo(f"Hint: {e.hint}", err=True)
        sys.exit(e.exit_code)


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
    """Fetch message history of a conversation.

    Works for public channels, private channels, DMs, and group DMs.
    For DMs, automatically uses the user token if the bot token fails.
    """
    params = {k: v for k, v in {
        "channel": channel, "oldest": oldest, "latest": latest,
        "limit": limit, "inclusive": inclusive, "cursor": cursor,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, oldest, latest, limit, inclusive, cursor])
    _run(ctx, "conversations.history", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@conversations.command("replies")
@click.option("--channel", default=None, help="Channel ID containing the thread")
@click.option("--ts", default=None, help="Thread parent message timestamp")
@click.option("--oldest", default=None, help="Only replies after this Unix timestamp")
@click.option("--latest", default=None, help="Only replies before this Unix timestamp")
@click.option("--limit", type=int, default=None, help="Max results per page")
@click.option("--inclusive", is_flag=True, default=None, help="Include messages with oldest or latest timestamps")
@click.option("--cursor", default=None, help="Pagination cursor")
@click.pass_context
def conversations_replies(ctx, channel, ts, oldest, latest, limit, inclusive, cursor):
    """Fetch all replies in a message thread.

    Requires channel ID and the thread parent timestamp (ts).
    Returns the parent message plus all replies in chronological order.
    """
    params = {k: v for k, v in {
        "channel": channel, "ts": ts, "oldest": oldest, "latest": latest,
        "limit": limit, "inclusive": inclusive, "cursor": cursor,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, ts, oldest, latest, limit, inclusive, cursor])
    _run(ctx, "conversations.replies", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


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


# ── chat command group ───────────────────────────────────────────────────────


@cli.group(cls=GlobalOptionsGroup)
def chat():
    """Send, update, and delete messages."""


@chat.command("+send")
@click.option("--channel", required=True, help="Channel name or ID")
@click.option("--text", required=True, help="Message text")
@click.option("--thread-ts", default=None, help="Thread timestamp for reply")
@click.pass_context
def chat_send_helper(ctx, channel, text, thread_ts):
    """Send a message (resolves channel names to IDs)."""
    format_flag = ctx.obj.get("format")
    fields = ctx.obj.get("fields")
    as_user = ctx.obj.get("as_user", False)
    as_bot = ctx.obj.get("as_bot", False)

    try:
        client = SlackClient(force_user=as_user, force_bot=as_bot)

        # Resolve channel name to ID if not already an ID
        resolved_channel = channel
        if not channel.startswith(("C", "D", "G")):
            # Try to find by name
            result = client.call("conversations.list", {"types": "public_channel,private_channel", "limit": 1000})
            channels = result.get("channels", [])
            match = [c for c in channels if c.get("name") == channel]
            if not match:
                click.echo(format_error("channel_not_found", f"No channel named '{channel}'"))
                sys.exit(EXIT_EXECUTION)
                return
            resolved_channel = match[0]["id"]

        params = {"channel": resolved_channel, "text": text}
        if thread_ts:
            params["thread_ts"] = thread_ts

        result = client.call("chat.postMessage", params)
        masked = apply_field_mask(result, fields)
        click.echo(format_output(masked, format_flag or "json"))

    except SlackCliError as e:
        click.echo(e.to_json())
        if e.hint:
            click.echo(f"Hint: {e.hint}", err=True)
        sys.exit(e.exit_code)


@chat.command("postMessage")
@click.option("--channel", default=None, help="Channel, private group, or IM channel to send message to")
@click.option("--text", default=None, help="Text of the message to send")
@click.option("--thread-ts", default=None, help="Timestamp of another message to reply to as a thread")
@click.option("--blocks", default=None, help="JSON array of Block Kit blocks")
@click.option("--unfurl-links/--no-unfurl-links", default=None, help="Enable/disable unfurling of text-based content")
@click.pass_context
def chat_post_message(ctx, channel, text, thread_ts, blocks, unfurl_links):
    """Send a message to a channel."""
    params = {k: v for k, v in {
        "channel": channel, "text": text, "thread_ts": thread_ts,
        "blocks": blocks, "unfurl_links": unfurl_links,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, text, thread_ts, blocks, unfurl_links])
    _run(ctx, "chat.postMessage", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@chat.command("update")
@click.option("--channel", default=None, help="Channel containing the message to update")
@click.option("--ts", default=None, help="Timestamp of the message to update")
@click.option("--text", default=None, help="New text for the message")
@click.option("--blocks", default=None, help="JSON array of Block Kit blocks")
@click.pass_context
def chat_update(ctx, channel, ts, text, blocks):
    """Update an existing message."""
    params = {k: v for k, v in {
        "channel": channel, "ts": ts, "text": text, "blocks": blocks,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, ts, text, blocks])
    _run(ctx, "chat.update", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@chat.command("delete")
@click.option("--channel", default=None, help="Channel containing the message to delete")
@click.option("--ts", default=None, help="Timestamp of the message to delete")
@click.pass_context
def chat_delete(ctx, channel, ts):
    """Delete a message."""
    params = {k: v for k, v in {"channel": channel, "ts": ts}.items() if v is not None}
    had_flags = any(v is not None for v in [channel, ts])
    _run(ctx, "chat.delete", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@chat.command("postEphemeral")
@click.option("--channel", default=None, help="Channel to send the ephemeral message in")
@click.option("--user", default=None, help="User ID who will see the ephemeral message")
@click.option("--text", default=None, help="Text of the message")
@click.option("--blocks", default=None, help="JSON array of Block Kit blocks")
@click.pass_context
def chat_post_ephemeral(ctx, channel, user, text, blocks):
    """Send an ephemeral message visible only to a specific user."""
    params = {k: v for k, v in {
        "channel": channel, "user": user, "text": text, "blocks": blocks,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, user, text, blocks])
    _run(ctx, "chat.postEphemeral", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@chat.command("scheduleMessage")
@click.option("--channel", default=None, help="Channel to send the scheduled message to")
@click.option("--text", default=None, help="Text of the message to send")
@click.option("--post-at", type=int, default=None, help="Unix timestamp for when the message should be sent")
@click.pass_context
def chat_schedule_message(ctx, channel, text, post_at):
    """Schedule a message to be sent at a specific time."""
    params = {k: v for k, v in {
        "channel": channel, "text": text, "post_at": post_at,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, text, post_at])
    _run(ctx, "chat.scheduleMessage", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@chat.command("unfurl")
@click.option("--channel", default=None, help="Channel ID of the message")
@click.option("--ts", default=None, help="Timestamp of the message to add unfurl to")
@click.option("--unfurls", default=None, help="JSON map of URL to unfurl Block Kit attachment")
@click.pass_context
def chat_unfurl(ctx, channel, ts, unfurls):
    """Provide custom unfurl behavior for URLs in messages."""
    params = {k: v for k, v in {
        "channel": channel, "ts": ts, "unfurls": unfurls,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, ts, unfurls])
    _run(ctx, "chat.unfurl", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


# ── users command group ──────────────────────────────────────────────────────


@cli.group(cls=GlobalOptionsGroup)
def users():
    """Manage users."""


@users.command("+whois")
@click.option("--name", default=None, help="Display name to search for")
@click.option("--email", default=None, help="Email to look up")
@click.pass_context
def users_whois_helper(ctx, name, email):
    """Find a user by name or email."""
    format_flag = ctx.obj.get("format")
    fields = ctx.obj.get("fields")
    as_user = ctx.obj.get("as_user", False)
    as_bot = ctx.obj.get("as_bot", False)

    if not name and not email:
        click.echo(format_error("no_input", "Provide --name or --email"))
        sys.exit(EXIT_VALIDATION)
        return

    try:
        client = SlackClient(force_user=as_user, force_bot=as_bot)

        if email:
            result = client.call("users.lookupByEmail", {"email": email})
            output_data = {"ok": True, "users": [result.get("user", {})], "count": 1}
        else:
            result = client.call("users.list", {"limit": 1000})
            members = result.get("members", [])
            matches = [
                m for m in members
                if name.lower() in (m.get("real_name", "") or "").lower()
                or name.lower() in (m.get("name", "") or "").lower()
                or name.lower() in (m.get("profile", {}).get("display_name", "") or "").lower()
            ]
            output_data = {"ok": True, "users": matches, "count": len(matches)}

        masked = apply_field_mask(output_data, fields)
        click.echo(format_output(masked, format_flag or "json"))

    except SlackCliError as e:
        click.echo(e.to_json())
        if e.hint:
            click.echo(f"Hint: {e.hint}", err=True)
        sys.exit(e.exit_code)


@users.command("list")
@click.option("--limit", type=int, default=None, help="Maximum number of users to return per page")
@click.option("--cursor", default=None, help="Pagination cursor")
@click.pass_context
def users_list(ctx, limit, cursor):
    """List all users in a Slack team."""
    params = {k: v for k, v in {"limit": limit, "cursor": cursor}.items() if v is not None}
    had_flags = any(v is not None for v in [limit, cursor])
    _run(ctx, "users.list", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@users.command("info")
@click.option("--user", default=None, help="User ID to get info on")
@click.pass_context
def users_info(ctx, user):
    """Get information about a user."""
    params = {k: v for k, v in {"user": user}.items() if v is not None}
    had_flags = user is not None
    _run(ctx, "users.info", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@users.command("lookupByEmail")
@click.option("--email", default=None, help="Email address to look up")
@click.pass_context
def users_lookup_by_email(ctx, email):
    """Find a user by their email address."""
    params = {k: v for k, v in {"email": email}.items() if v is not None}
    had_flags = email is not None
    _run(ctx, "users.lookupByEmail", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@users.command("getPresence")
@click.option("--user", default=None, help="User ID to get presence for")
@click.pass_context
def users_get_presence(ctx, user):
    """Get a user's current presence status."""
    params = {k: v for k, v in {"user": user}.items() if v is not None}
    had_flags = user is not None
    _run(ctx, "users.getPresence", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@users.command("setPresence")
@click.option("--presence", default=None, help="Either 'auto' or 'away'")
@click.pass_context
def users_set_presence(ctx, presence):
    """Manually set the user's presence."""
    params = {k: v for k, v in {"presence": presence}.items() if v is not None}
    had_flags = presence is not None
    _run(ctx, "users.setPresence", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


# ── reactions command group ──────────────────────────────────────────────────


@cli.group(cls=GlobalOptionsGroup)
def reactions():
    """Manage reactions."""


@reactions.command("add")
@click.option("--channel", default=None, help="Channel where the message was posted")
@click.option("--timestamp", default=None, help="Timestamp of the message to react to")
@click.option("--name", default=None, help="Reaction emoji name (without colons)")
@click.pass_context
def reactions_add(ctx, channel, timestamp, name):
    """Add a reaction emoji to a message."""
    params = {k: v for k, v in {
        "channel": channel, "timestamp": timestamp, "name": name,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, timestamp, name])
    _run(ctx, "reactions.add", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@reactions.command("remove")
@click.option("--channel", default=None, help="Channel where the message was posted")
@click.option("--timestamp", default=None, help="Timestamp of the message to remove reaction from")
@click.option("--name", default=None, help="Reaction emoji name to remove (without colons)")
@click.pass_context
def reactions_remove(ctx, channel, timestamp, name):
    """Remove a reaction emoji from a message."""
    params = {k: v for k, v in {
        "channel": channel, "timestamp": timestamp, "name": name,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, timestamp, name])
    _run(ctx, "reactions.remove", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@reactions.command("get")
@click.option("--channel", default=None, help="Channel where the message was posted")
@click.option("--timestamp", default=None, help="Timestamp of the message to get reactions for")
@click.pass_context
def reactions_get(ctx, channel, timestamp):
    """Get reactions for a message."""
    params = {k: v for k, v in {"channel": channel, "timestamp": timestamp}.items() if v is not None}
    had_flags = any(v is not None for v in [channel, timestamp])
    _run(ctx, "reactions.get", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@reactions.command("list")
@click.option("--user", default=None, help="User ID to show reactions for")
@click.option("--limit", type=int, default=None, help="Maximum number of items to return")
@click.option("--cursor", default=None, help="Pagination cursor")
@click.pass_context
def reactions_list(ctx, user, limit, cursor):
    """List reactions made by a user."""
    params = {k: v for k, v in {"user": user, "limit": limit, "cursor": cursor}.items() if v is not None}
    had_flags = any(v is not None for v in [user, limit, cursor])
    _run(ctx, "reactions.list", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


# ── files command group ──────────────────────────────────────────────────────


@cli.group(cls=GlobalOptionsGroup)
def files():
    """Manage files."""


@files.command("list")
@click.option("--channel", default=None, help="Filter files appearing in this channel")
@click.option("--user", default=None, help="Filter files uploaded by this user")
@click.option("--types", default=None, help="Filter by file types (e.g. 'images', 'pdfs')")
@click.option("--count", type=int, default=None, help="Number of items to return per page")
@click.pass_context
def files_list(ctx, channel, user, types, count):
    """List files shared in a team."""
    params = {k: v for k, v in {
        "channel": channel, "user": user, "types": types, "count": count,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel, user, types, count])
    _run(ctx, "files.list", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@files.command("upload")
@click.option("--channels", default=None, help="Comma-separated list of channel IDs to share the file in")
@click.option("--content", default=None, help="File contents via a POST variable")
@click.option("--filename", default=None, help="Filename of the file")
@click.option("--title", default=None, help="Title of the file")
@click.pass_context
def files_upload(ctx, channels, content, filename, title):
    """Upload a file to Slack."""
    params = {k: v for k, v in {
        "channels": channels, "content": content,
        "filename": filename, "title": title,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channels, content, filename, title])
    _run(ctx, "files.upload", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@files.command("info")
@click.option("--file", "file_id", default=None, help="File ID to get info for")
@click.pass_context
def files_info(ctx, file_id):
    """Get information about a file."""
    params = {k: v for k, v in {"file": file_id}.items() if v is not None}
    had_flags = file_id is not None
    _run(ctx, "files.info", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@files.command("delete")
@click.option("--file", "file_id", default=None, help="File ID to delete")
@click.pass_context
def files_delete(ctx, file_id):
    """Delete a file."""
    params = {k: v for k, v in {"file": file_id}.items() if v is not None}
    had_flags = file_id is not None
    _run(ctx, "files.delete", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


# ── search command group ─────────────────────────────────────────────────────


@cli.group(cls=GlobalOptionsGroup)
def search():
    """Search messages and files."""


@search.command("messages")
@click.option("--query", default=None, help="Search query text")
@click.option("--sort", default=None, help="Sort results by 'score' or 'timestamp'")
@click.option("--sort-dir", default=None, help="Sort direction: 'asc' or 'desc'")
@click.option("--count", type=int, default=None, help="Number of items to return per page")
@click.option("--page", type=int, default=None, help="Page number of results to return")
@click.pass_context
def search_messages(ctx, query, sort, sort_dir, count, page):
    """Search for messages matching a query."""
    params = {k: v for k, v in {
        "query": query, "sort": sort, "sort_dir": sort_dir,
        "count": count, "page": page,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [query, sort, sort_dir, count, page])
    _run(ctx, "search.messages", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@search.command("files")
@click.option("--query", default=None, help="Search query text")
@click.option("--sort", default=None, help="Sort results by 'score' or 'timestamp'")
@click.option("--sort-dir", default=None, help="Sort direction: 'asc' or 'desc'")
@click.option("--count", type=int, default=None, help="Number of items to return per page")
@click.option("--page", type=int, default=None, help="Page number of results to return")
@click.pass_context
def search_files(ctx, query, sort, sort_dir, count, page):
    """Search for files matching a query."""
    params = {k: v for k, v in {
        "query": query, "sort": sort, "sort_dir": sort_dir,
        "count": count, "page": page,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [query, sort, sort_dir, count, page])
    _run(ctx, "search.files", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


# ── pins command group ───────────────────────────────────────────────────────


@cli.group(cls=GlobalOptionsGroup)
def pins():
    """Manage pinned items."""


@pins.command("add")
@click.option("--channel", default=None, help="Channel to pin the message in")
@click.option("--timestamp", default=None, help="Timestamp of the message to pin")
@click.pass_context
def pins_add(ctx, channel, timestamp):
    """Pin a message to a channel."""
    params = {k: v for k, v in {"channel": channel, "timestamp": timestamp}.items() if v is not None}
    had_flags = any(v is not None for v in [channel, timestamp])
    _run(ctx, "pins.add", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@pins.command("remove")
@click.option("--channel", default=None, help="Channel to unpin the message from")
@click.option("--timestamp", default=None, help="Timestamp of the message to unpin")
@click.pass_context
def pins_remove(ctx, channel, timestamp):
    """Unpin a message from a channel."""
    params = {k: v for k, v in {"channel": channel, "timestamp": timestamp}.items() if v is not None}
    had_flags = any(v is not None for v in [channel, timestamp])
    _run(ctx, "pins.remove", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@pins.command("list")
@click.option("--channel", default=None, help="Channel to list pins for")
@click.pass_context
def pins_list(ctx, channel):
    """List pinned items in a channel."""
    params = {k: v for k, v in {"channel": channel}.items() if v is not None}
    had_flags = channel is not None
    _run(ctx, "pins.list", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


# ── bookmarks command group ──────────────────────────────────────────────────


@cli.group(cls=GlobalOptionsGroup)
def bookmarks():
    """Manage channel bookmarks."""


@bookmarks.command("add")
@click.option("--channel-id", default=None, help="Channel ID to add the bookmark to")
@click.option("--title", default=None, help="Title for the bookmark")
@click.option("--type", "bookmark_type", default=None, help="Type of bookmark (e.g. 'link')")
@click.option("--link", default=None, help="URL for the bookmark")
@click.pass_context
def bookmarks_add(ctx, channel_id, title, bookmark_type, link):
    """Add a bookmark to a channel."""
    params = {k: v for k, v in {
        "channel_id": channel_id, "title": title,
        "type": bookmark_type, "link": link,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [channel_id, title, bookmark_type, link])
    _run(ctx, "bookmarks.add", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@bookmarks.command("edit")
@click.option("--bookmark-id", default=None, help="Bookmark ID to edit")
@click.option("--channel-id", default=None, help="Channel ID containing the bookmark")
@click.option("--title", default=None, help="New title for the bookmark")
@click.option("--link", default=None, help="New URL for the bookmark")
@click.pass_context
def bookmarks_edit(ctx, bookmark_id, channel_id, title, link):
    """Edit a bookmark in a channel."""
    params = {k: v for k, v in {
        "bookmark_id": bookmark_id, "channel_id": channel_id,
        "title": title, "link": link,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [bookmark_id, channel_id, title, link])
    _run(ctx, "bookmarks.edit", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@bookmarks.command("remove")
@click.option("--bookmark-id", default=None, help="Bookmark ID to remove")
@click.option("--channel-id", default=None, help="Channel ID containing the bookmark")
@click.pass_context
def bookmarks_remove(ctx, bookmark_id, channel_id):
    """Remove a bookmark from a channel."""
    params = {k: v for k, v in {
        "bookmark_id": bookmark_id, "channel_id": channel_id,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [bookmark_id, channel_id])
    _run(ctx, "bookmarks.remove", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@bookmarks.command("list")
@click.option("--channel-id", default=None, help="Channel ID to list bookmarks for")
@click.pass_context
def bookmarks_list(ctx, channel_id):
    """List bookmarks in a channel."""
    params = {k: v for k, v in {"channel_id": channel_id}.items() if v is not None}
    had_flags = channel_id is not None
    _run(ctx, "bookmarks.list", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


# ── reminders command group ──────────────────────────────────────────────────


@cli.group(cls=GlobalOptionsGroup)
def reminders():
    """Manage reminders."""


@reminders.command("add")
@click.option("--text", default=None, help="Content of the reminder")
@click.option("--time", "time_val", default=None, help="When the reminder should fire")
@click.option("--user", default=None, help="User ID to receive the reminder")
@click.pass_context
def reminders_add(ctx, text, time_val, user):
    """Create a reminder."""
    params = {k: v for k, v in {
        "text": text, "time": time_val, "user": user,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [text, time_val, user])
    _run(ctx, "reminders.add", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@reminders.command("complete")
@click.option("--reminder", default=None, help="Reminder ID to mark complete")
@click.pass_context
def reminders_complete(ctx, reminder):
    """Mark a reminder as complete."""
    params = {k: v for k, v in {"reminder": reminder}.items() if v is not None}
    had_flags = reminder is not None
    _run(ctx, "reminders.complete", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@reminders.command("delete")
@click.option("--reminder", default=None, help="Reminder ID to delete")
@click.pass_context
def reminders_delete(ctx, reminder):
    """Delete a reminder."""
    params = {k: v for k, v in {"reminder": reminder}.items() if v is not None}
    had_flags = reminder is not None
    _run(ctx, "reminders.delete", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@reminders.command("info")
@click.option("--reminder", default=None, help="Reminder ID to get info for")
@click.pass_context
def reminders_info(ctx, reminder):
    """Get information about a reminder."""
    params = {k: v for k, v in {"reminder": reminder}.items() if v is not None}
    had_flags = reminder is not None
    _run(ctx, "reminders.info", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@reminders.command("list")
@click.pass_context
def reminders_list(ctx):
    """List all reminders for the authenticated user."""
    _run(ctx, "reminders.list", {})


# ── team command group ───────────────────────────────────────────────────────


@cli.group(cls=GlobalOptionsGroup)
def team():
    """Team information and administration."""


@team.command("info")
@click.pass_context
def team_info(ctx):
    """Get information about the current team."""
    _run(ctx, "team.info", {})


@team.command("accessLogs")
@click.option("--count", type=int, default=None, help="Number of items to return per page")
@click.option("--page", type=int, default=None, help="Page number of results to return")
@click.option("--before", type=int, default=None, help="Unix timestamp to filter logs before this time")
@click.pass_context
def team_access_logs(ctx, count, page, before):
    """Get the access logs for the current team."""
    params = {k: v for k, v in {
        "count": count, "page": page, "before": before,
    }.items() if v is not None}
    had_flags = any(v is not None for v in [count, page, before])
    _run(ctx, "team.accessLogs", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


@team.command("billableInfo")
@click.option("--user", default=None, help="User ID to get billable info for")
@click.pass_context
def team_billable_info(ctx, user):
    """Get billable users information for the current team."""
    params = {k: v for k, v in {"user": user}.items() if v is not None}
    had_flags = user is not None
    _run(ctx, "team.billableInfo", params, had_convenience_flags=had_flags and ctx.obj.get("body") is not None)


# ── auth command group ───────────────────────────────────────────────────────


@cli.group(cls=GlobalOptionsGroup)
def auth():
    """Manage authentication."""


@auth.command("status")
@click.pass_context
def auth_status(ctx):
    """Show which tokens are configured."""
    import os
    from slack_cli.auth import CONFIG_PATH

    status = {}

    # Check bot token sources
    if os.environ.get("SLACK_CLI_TOKEN"):
        status["bot_token"] = "configured (env: SLACK_CLI_TOKEN)"
    elif os.environ.get("SLACK_BOT_TOKEN"):
        status["bot_token"] = "configured (env: SLACK_BOT_TOKEN)"
    else:
        status["bot_token"] = "not configured"

    # Check user token sources
    if os.environ.get("SLACK_CLI_USER_TOKEN"):
        status["user_token"] = "configured (env: SLACK_CLI_USER_TOKEN)"
    elif os.environ.get("SLACK_MCP_XOXP_TOKEN"):
        status["user_token"] = "configured (env: SLACK_MCP_XOXP_TOKEN)"
    else:
        status["user_token"] = "not configured"

    status["config_file"] = CONFIG_PATH

    format_flag = ctx.obj.get("format")
    click.echo(format_output(status, format_flag or "json"))


@auth.command("test")
@click.pass_context
def auth_test(ctx):
    """Verify tokens by calling auth.test API."""
    results = {}
    format_flag = ctx.obj.get("format")

    try:
        client = SlackClient()
        if client._bot_client:
            bot_result = client.call("auth.test", token_type="bot")
            results["bot"] = {"ok": True, "user": bot_result.get("user"), "team": bot_result.get("team")}
    except SlackCliError as e:
        results["bot"] = {"ok": False, "error": e.error}

    try:
        client = SlackClient()
        if client._user_client:
            user_result = client.call("auth.test", token_type="user")
            results["user"] = {"ok": True, "user": user_result.get("user"), "team": user_result.get("team")}
    except SlackCliError as e:
        results["user"] = {"ok": False, "error": e.error}

    if not results:
        results = {"ok": False, "error": "no tokens configured"}

    click.echo(format_output(results, format_flag or "json"))


@auth.command("store")
@click.option("--bot-token", default=None, help="Bot token (xoxb-...)")
@click.option("--user-token", default=None, help="User token (xoxp-...)")
@click.pass_context
def auth_store(ctx, bot_token, user_token):
    """Save tokens to config file."""
    from slack_cli.auth import save_credentials, CONFIG_PATH

    if not bot_token and not user_token:
        click.echo(format_error("no_input", "Provide --bot-token and/or --user-token"))
        sys.exit(EXIT_VALIDATION)
        return

    save_credentials(bot_token=bot_token, user_token=user_token)
    click.echo(json.dumps({"ok": True, "config_file": CONFIG_PATH}, indent=2))


# ── schema introspection command ─────────────────────────────────────────────


@cli.command("schema")
@click.argument("method", required=False)
@click.option("--list", "list_all", is_flag=True, help="List all available methods")
@click.option("--group", "group_name", default=None, help="List methods in a specific group")
@click.pass_context
def schema_cmd(ctx, method, list_all, group_name):
    """Inspect API method schemas."""
    from slack_cli.schema import get_schema as _get_schema, list_schemas as _list, get_group_methods, list_groups

    format_flag = ctx.obj.get("format")

    if list_all:
        click.echo(format_output(_list(), format_flag or "json"))
        return

    if group_name:
        methods = get_group_methods(group_name)
        if not methods:
            click.echo(format_error("group_not_found", f"No methods found for group '{group_name}'"))
            sys.exit(EXIT_EXECUTION)
            return
        click.echo(format_output(methods, format_flag or "json"))
        return

    if not method:
        # No args -- list groups
        click.echo(format_output(list_groups(), format_flag or "json"))
        return

    schema = _get_schema(method)
    if not schema:
        click.echo(format_error("method_not_found", f"No schema found for '{method}'"))
        sys.exit(EXIT_EXECUTION)
        return

    click.echo(format_output(schema, format_flag or "json"))
