"""Timer commands for OmniFocus task time tracking."""
from __future__ import annotations

import click

from omnifocus_cli.bridge import call_omnifocus
from omnifocus_cli.formatters import output_result, should_use_json

TIMER_PLUGIN = "com.dorsey.omnifocus-timer"
TIMER_LIBRARY = "timer-lib"


def _timer_call(method: str, params: dict | None = None) -> dict:
    """Call a timer plugin method via the bridge."""
    return call_omnifocus(method, params, plugin=TIMER_PLUGIN, library=TIMER_LIBRARY)


@click.group()
def timer():
    """Time tracking for OmniFocus tasks."""
    pass


@timer.command("start")
@click.argument("task_id")
@click.pass_context
def timer_start(ctx, task_id):
    """Start a timer for a task."""
    result = _timer_call("startTimer", {"taskId": task_id})
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, json_output=use_json)


@timer.command("stop")
@click.pass_context
def timer_stop(ctx):
    """Stop the active timer."""
    result = _timer_call("stopTimer")
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, json_output=use_json)


@timer.command("pause")
@click.pass_context
def timer_pause(ctx):
    """Pause the active timer."""
    result = _timer_call("pauseTimer")
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, json_output=use_json)


@timer.command("resume")
@click.pass_context
def timer_resume(ctx):
    """Resume the paused timer."""
    result = _timer_call("resumeTimer")
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, json_output=use_json)


@timer.command("status")
@click.pass_context
def timer_status(ctx):
    """Get the current timer status."""
    result = _timer_call("getTimerStatus")
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, json_output=use_json)


@timer.command("history")
@click.argument("task_id")
@click.pass_context
def timer_history(ctx, task_id):
    """Get timer history for a task."""
    result = _timer_call("getTimerHistory", {"taskId": task_id})
    use_json = should_use_json(ctx.obj.get("format"))
    output_result(result, json_output=use_json)
