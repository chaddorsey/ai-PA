"""Structured error output for Slack CLI."""
import json
import sys

EXIT_SUCCESS = 0
EXIT_EXECUTION = 1
EXIT_VALIDATION = 2


def format_error(error: str, detail: str | None = None) -> str:
    """Format an error as JSON string for stdout."""
    result = {"ok": False, "error": error}
    if detail is not None:
        result["detail"] = detail
    return json.dumps(result, indent=2)


def print_error(error: str, detail: str | None = None, hint: str | None = None,
                exit_code: int = EXIT_EXECUTION) -> None:
    """Print structured error to stdout (JSON) and optional hint to stderr, then exit."""
    output = format_error(error, detail)
    print(output)

    if hint:
        print(f"Hint: {hint}", file=sys.stderr)

    sys.exit(exit_code)


class SlackCliError(Exception):
    """Structured error with exit code and optional hint."""

    def __init__(self, error: str, detail: str | None = None,
                 exit_code: int = EXIT_EXECUTION, hint: str | None = None):
        self.error = error
        self.detail = detail
        self.exit_code = exit_code
        self.hint = hint
        super().__init__(detail or error)

    def to_json(self) -> str:
        return format_error(self.error, self.detail)
