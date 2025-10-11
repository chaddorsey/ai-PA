"""Top-level package for the scheduler service."""

from importlib.metadata import version


def get_version() -> str:
    """Return the installed package version."""

    return version("scheduler-service")


