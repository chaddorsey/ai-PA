"""build_runtime_env backend-dir override + scoping (plan Unit 2b)."""
from letta_push_receiver.warm_pool import PROD_BACKEND_DIR, build_runtime_env


def test_default_is_prod_backend():
    assert build_runtime_env()["LETTA_LOCAL_BACKEND_DIR"] == PROD_BACKEND_DIR


def test_explicit_override_is_honored():
    assert build_runtime_env("/tmp/clone-x")["LETTA_LOCAL_BACKEND_DIR"] == "/tmp/clone-x"


def test_env_var_does_not_leak_into_default(monkeypatch):
    # Single-writer safety: a stray LETTA_LOCAL_BACKEND_DIR in the process env
    # must NOT repoint the default — only the explicit param (which only the
    # App Server supervisor passes) can override. Otherwise a leaked var could
    # point a warm subprocess at the wrong backend.
    monkeypatch.setenv("LETTA_LOCAL_BACKEND_DIR", "/tmp/evil")
    assert build_runtime_env()["LETTA_LOCAL_BACKEND_DIR"] == PROD_BACKEND_DIR
