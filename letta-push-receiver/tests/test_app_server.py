from letta_push_receiver.app_server import _is_ready_line


def test_ready_line_detects_listening_banner():
    # Task-1 spike confirmed the exact banner the server prints when ready.
    assert _is_ready_line("Listening on ws://127.0.0.1:4577") is True


def test_ready_line_ignores_noise():
    assert _is_ready_line("loading agent config...") is False
