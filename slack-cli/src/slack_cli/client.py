"""Slack SDK client wrapper with credential chain and auto token selection."""
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from slack_cli.auth import resolve_token, TOKEN_TYPE_BOT, TOKEN_TYPE_USER, TOKEN_TYPE_EITHER
from slack_cli.error import SlackCliError, EXIT_EXECUTION
from slack_cli.schema import get_schema


class SlackClient:
    """Wrapper around slack_sdk.WebClient with credential chain."""

    def __init__(self, force_user: bool = False, force_bot: bool = False):
        bot_token = resolve_token(TOKEN_TYPE_BOT)
        user_token = resolve_token(TOKEN_TYPE_USER)
        self._bot_client = WebClient(token=bot_token) if bot_token else None
        self._user_client = WebClient(token=user_token) if user_token else None
        self._force_user = force_user
        self._force_bot = force_bot

    def _get_client(self, token_type: str) -> WebClient:
        """Get the appropriate WebClient for the token type."""
        if self._force_user:
            token_type = TOKEN_TYPE_USER
        elif self._force_bot:
            token_type = TOKEN_TYPE_BOT

        if token_type == TOKEN_TYPE_EITHER:
            client = self._bot_client or self._user_client
        elif token_type == TOKEN_TYPE_USER:
            client = self._user_client
        else:
            client = self._bot_client

        if client is None:
            hint = "Set SLACK_CLI_TOKEN (bot) or SLACK_CLI_USER_TOKEN (user) env var"
            if token_type == TOKEN_TYPE_USER:
                hint = "Set SLACK_CLI_USER_TOKEN env var (this method requires a user token)"
            raise SlackCliError("no_token", f"No {token_type} token available", hint=hint)

        return client

    # Methods that should auto-retry with user token on channel_not_found
    _DM_RETRY_METHODS = {
        "conversations.history", "conversations.replies", "conversations.info",
        "conversations.members", "conversations.open",
    }

    def call(self, method: str, params: dict | None = None,
             token_type: str | None = None) -> dict:
        """Call a Slack API method.

        For conversation methods, auto-retries with user token if bot token
        gets channel_not_found (common for DMs where bot isn't a member).
        """
        if token_type is None:
            schema = get_schema(method)
            token_type = schema["token_type"] if schema else TOKEN_TYPE_EITHER

        client = self._get_client(token_type)

        try:
            response = client.api_call(method, params=params or {})
            return dict(response.data) if hasattr(response, "data") else response
        except SlackApiError as e:
            error_code = e.response.get("error", "api_error") if hasattr(e.response, "get") else "api_error"

            # Auto-retry with user token for DM-related failures
            if (error_code in ("channel_not_found", "not_in_channel")
                    and method in self._DM_RETRY_METHODS
                    and not self._force_user
                    and not self._force_bot
                    and self._user_client
                    and client != self._user_client):
                try:
                    response = self._user_client.api_call(method, params=params or {})
                    return dict(response.data) if hasattr(response, "data") else response
                except SlackApiError:
                    pass  # Fall through to original error

            raise SlackCliError(
                error_code,
                str(e),
                exit_code=EXIT_EXECUTION,
                hint=f"Slack API returned error for {method}",
            )

    def paginate(self, method: str, params: dict | None = None,
                 token_type: str | None = None, max_pages: int = 10) -> list[dict]:
        """Call a Slack API method with cursor-based pagination."""
        params = dict(params or {})
        all_pages = []

        for _ in range(max_pages):
            result = self.call(method, params, token_type)
            all_pages.append(result)

            cursor = result.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
            params["cursor"] = cursor

        return all_pages
