"""Cross-channel backtrace dispatch: payload builder contract.

Tests that the push-receiver body produced by _backtrace_push_body routes
to the tasks-agent and carries the correct recipe instruction + ref_id.

Run: cd pa-web-ui && python -m pytest tests/test_backtrace_dispatch.py -v
"""
import app


def test_backtrace_push_body():
    body = app._backtrace_push_body("abc123ef")
    assert body["agent"] == "tasks"
    assert "cross_channel_backtrace" in body["prompt"]
    assert "abc123ef" in body["prompt"]
    assert body["source_ref"] == "abc123ef"


def test_backtrace_push_body_priority():
    assert app._backtrace_push_body("abc123ef")["priority"] == "normal"
    assert app._backtrace_push_body("abc123ef", priority="urgent")["priority"] == "urgent"
