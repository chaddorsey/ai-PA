"""Supervisor R1 primitives: exclusive backend lock + foreign-writer tripwire
(plan Unit 3)."""
import os

from letta_push_receiver import supervisor as sup


def test_backend_lock_is_exclusive(tmp_path):
    lock = str(tmp_path / ".owner.lock")
    fh1 = sup.acquire_backend_lock(lock)
    assert fh1 is not None, "first holder should acquire the lock"

    fh2 = sup.acquire_backend_lock(lock)
    assert fh2 is None, "a second holder must be refused (single-writer)"

    fh1.close()  # releases the flock
    fh3 = sup.acquire_backend_lock(lock)
    assert fh3 is not None, "lock is free again after the first holder releases"
    fh3.close()


def test_scan_foreign_writers_detects_backend_openers_and_excludes_self(monkeypatch):
    mypid = os.getpid()
    fake_ps = "\n".join([
        "  111 node /opt/homebrew/bin/letta server --backend local --listen ws://127.0.0.1:4577",
        "  222 python /Users/x/.local/bin/letta-local-runner",
        "  333 vim notes.txt",
        "  999 node /opt/homebrew/bin/letta server --backend local",   # our child → excluded
        f"  {mypid} python own-supervisor --backend local",            # own pid → excluded
    ])

    class _R:
        stdout = fake_ps

    monkeypatch.setattr(sup.subprocess, "run", lambda *a, **k: _R())

    foreign = sup.scan_foreign_writers(own_child_pid=999)
    joined = " ".join(foreign)

    assert "111" in joined              # a foreign `letta --backend local`
    assert "222" in joined              # letta-local-runner
    assert "333" not in joined          # vim does not open the backend
    assert "999" not in joined          # our own child is excluded
    assert str(mypid) not in joined     # our own pid is excluded


def test_probe_forward_progress_degrades_gracefully_without_ws(monkeypatch):
    # If the WS client lib can't be imported, the probe must return True
    # (do-not-restart) so a missing optional dep never causes restart storms.
    import builtins
    real_import = builtins.__import__

    def _no_ws(name, *a, **k):
        if name.startswith("websockets"):
            raise ImportError("simulated: websockets unavailable")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_ws)
    assert sup.probe_forward_progress() is True
