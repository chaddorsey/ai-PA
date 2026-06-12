"""Click-based CLI for Twitter operations."""
import json
import sys

import click

from .formatters import format_output

# Default Smaug config path (overridable via env or --config)
DEFAULT_CONFIG_PATH = "/app/smaug-config/smaug.config.json"


def _get_client(config_path: str):
    """Lazy-import and create client to keep CLI startup fast."""
    from .client import TwitterClient
    return TwitterClient(config_path)


def _output(data, fmt: str):
    """Print formatted output and exit."""
    click.echo(format_output(data, fmt))


def _error(message: str, code: int = 1):
    """Print error as JSON to stdout (agent-parseable) and exit."""
    click.echo(json.dumps({"status": "error", "error": message}))
    sys.exit(code)


@click.group()
@click.option("--config", envvar="TWITTER_CONFIG_PATH",
              default=DEFAULT_CONFIG_PATH,
              help="Path to Smaug config JSON.")
@click.pass_context
def cli(ctx, config):
    """Twitter CLI — read and write Twitter with TLS fingerprinting."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


# --- Schema discovery ---

COMMAND_SCHEMA = {
    "read": {
        "feed": {"description": "Your home timeline", "params": {"count": "int (default 20)"}},
        "user": {"description": "A user's recent tweets", "params": {"handle": "required", "count": "int (default 20)"}},
        "bookmarks": {"description": "Your bookmarked tweets", "params": {"count": "int (default 20)"}},
        "search": {"description": "Search tweets", "params": {"query": "required", "count": "int (default 20)"}},
        "list": {"description": "Members of a Twitter list", "params": {"list_id": "required"}},
        "tweet": {"description": "A tweet and its replies (flat)", "params": {"tweet_id": "required"}},
    },
    "write": {
        "bookmark": {"description": "Bookmark a tweet", "params": {"tweet_id": "required"}},
        "list-add": {"description": "Add user to a list", "params": {"list_id": "required", "handle": "required"}},
        "list-remove": {"description": "Remove user from a list", "params": {"list_id": "required", "handle": "required"}},
    },
}


@cli.command()
@click.argument("command", required=False)
def schema(command):
    """List available commands, or details for a specific command."""
    if not command:
        output = {}
        for group, cmds in COMMAND_SCHEMA.items():
            output[group] = [
                {"command": f"{group} {name}", "description": meta["description"]}
                for name, meta in cmds.items()
            ]
        click.echo(format_output(output, "json"))
        return

    # Look up specific command
    parts = command.split(" ", 1)
    group = parts[0] if parts else ""
    name = parts[1] if len(parts) > 1 else ""

    if group in COMMAND_SCHEMA and name in COMMAND_SCHEMA[group]:
        meta = COMMAND_SCHEMA[group][name]
        click.echo(format_output({
            "command": f"{group} {name}",
            "description": meta["description"],
            "params": meta["params"],
        }, "json"))
    else:
        _error(f"Unknown command: {command}. Run 'twitter-cli schema' to list all.")


# --- Read commands ---

@cli.group()
def read():
    """Read operations: feed, user, bookmarks, search, list, tweet."""
    pass


@read.command()
@click.option("--count", default=20, help="Number of tweets to fetch.")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def feed(ctx, count, fmt):
    """Fetch your home timeline."""
    client = _get_client(ctx.obj["config_path"])
    try:
        tweets = client.get_home_timeline(count=count)
        _output(tweets, fmt)
    finally:
        client.close()


@read.command()
@click.argument("handle")
@click.option("--count", default=20, help="Number of tweets to fetch.")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def user(ctx, handle, count, fmt):
    """Fetch a user's recent tweets."""
    client = _get_client(ctx.obj["config_path"])
    try:
        tweets = client.get_user_tweets(handle, count=count)
        _output(tweets, fmt)
    finally:
        client.close()


@read.command()
@click.option("--count", default=20, help="Number of bookmarks to fetch.")
@click.option("--cursor", default=None, help="Pagination cursor for the next page.")
@click.option("--paged", is_flag=True, help="Return {tweets, next_cursor} for pagination.")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def bookmarks(ctx, count, cursor, paged, fmt):
    """Fetch your bookmarked tweets."""
    client = _get_client(ctx.obj["config_path"])
    try:
        result = client.get_bookmarks(count=count, cursor=cursor, paged=paged or bool(cursor))
        _output(result, fmt)
    finally:
        client.close()


@read.command()
@click.argument("query")
@click.option("--count", default=20, help="Number of results.")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def search(ctx, query, count, fmt):
    """Search tweets."""
    client = _get_client(ctx.obj["config_path"])
    try:
        tweets = client.search_tweets(query, count=count)
        _output(tweets, fmt)
    finally:
        client.close()


@read.command("list")
@click.argument("list_id")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def read_list(ctx, list_id, fmt):
    """Fetch members of a Twitter list."""
    client = _get_client(ctx.obj["config_path"])
    try:
        members = client.get_list_members(list_id)
        _output(members, fmt)
    finally:
        client.close()


@read.command()
@click.argument("tweet_id")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def tweet(ctx, tweet_id, fmt):
    """Fetch a tweet and its replies."""
    client = _get_client(ctx.obj["config_path"])
    try:
        data = client.get_tweet_detail(tweet_id)
        _output(data, fmt)
    finally:
        client.close()


# --- Write commands ---

@cli.group()
def write():
    """Write operations: bookmark, list-add, list-remove."""
    pass


@write.command()
@click.argument("tweet_id")
@click.pass_context
def bookmark(ctx, tweet_id):
    """Bookmark a tweet."""
    client = _get_client(ctx.obj["config_path"])
    try:
        ok = client.add_bookmark(tweet_id)
        _output({"status": "ok" if ok else "error", "tweet_id": tweet_id}, "json")
    finally:
        client.close()


@write.command("list-add")
@click.argument("list_id")
@click.argument("handle")
@click.pass_context
def list_add(ctx, list_id, handle):
    """Add a user to a Twitter list."""
    client = _get_client(ctx.obj["config_path"])
    try:
        user_id = client.get_user_rest_id(handle)
        if not user_id:
            _error(f"User not found: {handle}")
        ok = client.add_list_member(list_id, user_id)
        _output({"status": "ok" if ok else "error", "handle": handle, "list_id": list_id}, "json")
    finally:
        client.close()


@write.command("list-remove")
@click.argument("list_id")
@click.argument("handle")
@click.pass_context
def list_remove(ctx, list_id, handle):
    """Remove a user from a Twitter list."""
    client = _get_client(ctx.obj["config_path"])
    try:
        user_id = client.get_user_rest_id(handle)
        if not user_id:
            _error(f"User not found: {handle}")
        ok = client.remove_list_member(list_id, user_id)
        _output({"status": "ok" if ok else "error", "handle": handle, "list_id": list_id}, "json")
    finally:
        client.close()
