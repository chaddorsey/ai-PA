import json
from slack_cli.error import format_error, SlackCliError, EXIT_VALIDATION, EXIT_EXECUTION


def test_format_error_returns_json():
    result = format_error("channel_not_found", "Channel 'C999' does not exist")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert parsed["error"] == "channel_not_found"
    assert parsed["detail"] == "Channel 'C999' does not exist"


def test_format_error_without_detail():
    result = format_error("invalid_auth")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert parsed["error"] == "invalid_auth"
    assert "detail" not in parsed


def test_slack_cli_error_has_exit_code():
    err = SlackCliError("channel_not_found", "Not found", exit_code=EXIT_VALIDATION)
    assert err.exit_code == EXIT_VALIDATION
    assert err.error == "channel_not_found"


def test_slack_cli_error_json():
    err = SlackCliError("rate_limited", "Too many requests", exit_code=EXIT_EXECUTION, hint="Wait and retry")
    output = err.to_json()
    parsed = json.loads(output)
    assert parsed["ok"] is False
    assert parsed["error"] == "rate_limited"
    assert err.hint == "Wait and retry"
