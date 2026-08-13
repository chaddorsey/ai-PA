"""Standalone launchd entrypoint: the sole-owner App Server supervisor.

This process OWNS the one `letta server --backend local --openai-api` that is
the sole writer of ``~/.letta/lc-local-backend`` (plan
docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md, Units 2-3).
Everything else — enrichment (letta-push-receiver), the web client, the terminal
client — is a *client* of the server this supervisor runs.

Responsibilities:
  1. Hold an advisory ``flock`` on the backend dir for the process lifetime — a
     tripwire for the single-writer (R1) invariant. Refuse to start if another
     holder exists (two owners = the projection-divergence race we exist to kill).
  2. Start and supervise the ``letta server`` child. **Single kill authority:**
     only this supervisor signals the child, so launchd (which supervises *this*
     process via KeepAlive) and the watchdog never contend for the same PID.
  3. Watchdog — TWO cadences:
       * fast: crash + HTTP responsiveness (child alive AND ``/v1/models`` answers);
       * slow: **forward progress** via a synthetic streamed ``/ws`` turn, because a
         bare ``/v1/models`` ping stays responsive *during* a silent stall
         (#99 / Unit 1 finding #12) — the ping cannot see a hung stream.
     N consecutive failures of either → kill + respawn the child.
  4. Periodic foreign-writer re-scan: warn loudly if another ``letta … --backend
     local`` process opens the backend *after* boot (the dangerous, common case a
     boot-only check misses).

Secrets: this module never logs ``build_runtime_env()`` (it carries DB
passwords + tokens); treat the log dir as secret-bearing.
"""
from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .app_server import AppServer
from .config import APP_SERVER_LISTEN, APP_SERVER_URL
from .warm_pool import PROD_BACKEND_DIR

# ---- config (env-tunable) ----
BACKEND_DIR = os.environ.get("PA_APP_SERVER_BACKEND_DIR") or PROD_BACKEND_DIR
LOCK_PATH = os.path.join(BACKEND_DIR, ".owner.lock")

HEALTH_INTERVAL_S = float(os.environ.get("PA_APP_SERVER_HEALTH_INTERVAL_S", "20"))
HEALTH_MISSES = int(os.environ.get("PA_APP_SERVER_HEALTH_MISSES", "3"))
HEALTH_TIMEOUT_S = float(os.environ.get("PA_APP_SERVER_HEALTH_TIMEOUT_S", "5"))

STALL_INTERVAL_S = float(os.environ.get("PA_APP_SERVER_STALL_INTERVAL_S", "300"))
STALL_TURN_TIMEOUT_S = float(os.environ.get("PA_APP_SERVER_STALL_TURN_TIMEOUT_S", "45"))
STALL_DISABLED = os.environ.get("PA_APP_SERVER_STALL_DISABLE", "0") == "1"
# A cheap agent for the synthetic streamed turn (deepseek-flash = fast + cheap).
STALL_PROBE_AGENT = os.environ.get(
    "PA_APP_SERVER_STALL_PROBE_AGENT",
    "agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a",  # docs
)
STALL_PROBE_CONVERSATION = os.environ.get("PA_APP_SERVER_STALL_PROBE_CONVERSATION", "default")

RESCAN_INTERVAL_S = float(os.environ.get("PA_APP_SERVER_RESCAN_INTERVAL_S", "60"))


def _log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # NEVER interpolate build_runtime_env() / os.environ here — secret-bearing.
    print(f"[{ts}] [supervisor] {msg}", file=sys.stdout, flush=True)


def acquire_backend_lock(lock_path: str = LOCK_PATH):
    """Take an exclusive, non-blocking advisory flock on the backend.

    Returns the held file object (keep a reference for the process lifetime) or
    None if another holder already owns it. This is a TRIPWIRE, not a hard
    guarantee — the stock ``letta`` binary does not consult it (so source-removal
    of other writers at cutover is the real guarantee, plan Unit 8) — but it
    reliably catches a second *supervisor* and cooperating tools.
    """
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    fh.write(f"pid={os.getpid()} started={int(time.time())}\n")
    fh.flush()
    return fh


def scan_foreign_writers(backend_dir: str = BACKEND_DIR, own_child_pid: int | None = None) -> list[str]:
    """Return descriptions of OTHER processes that appear to open the backend.

    Detects `letta ... --backend local` / `letta-local-runner` processes that are
    not our supervised child — the second-writer tripwire. Best-effort (ps-based);
    logs, does not kill.
    """
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True, text=True, timeout=8, check=False,
        ).stdout
    except Exception:
        return []
    foreign = []
    mypid = os.getpid()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid_str, cmd = line.split(None, 1)
            pid = int(pid_str)
        except ValueError:
            continue
        if pid in (mypid, own_child_pid):
            continue
        low = cmd.lower()
        opens_backend = (
            ("letta" in low and "--backend local" in low)
            or "letta-local-runner" in low
            or "letta_local_runner" in low
        )
        if opens_backend:
            foreign.append(f"pid={pid} {cmd[:120]}")
    return foreign


def probe_forward_progress(timeout_s: float = STALL_TURN_TIMEOUT_S) -> bool:
    """Drive one tiny synthetic streamed turn over /ws; return True on progress.

    Progress = at least one ``stream_delta`` AND a ``turn_finished`` within
    ``timeout_s``. Distinguishes a silent stall (turn hangs, no deltas / no
    finish) from a healthy-but-idle server (which a bare ping cannot). Returns
    True (do-not-restart) if the WS client library is unavailable or the probe
    can't run, so a missing optional dep never causes restart storms — the fast
    responsiveness check remains the always-on baseline.
    """
    try:
        from websockets.sync.client import connect  # optional dep
    except Exception:
        _log("stall-probe skipped: websockets client unavailable (fast check still active)")
        return True

    ws_url = APP_SERVER_LISTEN.rstrip("/") + "/ws"
    try:
        with connect(ws_url, open_timeout=10) as ws:
            ws.send(json.dumps({
                "type": "runtime_start", "request_id": "sup-probe",
                "agent_id": STALL_PROBE_AGENT, "conversation_id": STALL_PROBE_CONVERSATION,
            }))
            injected = False
            saw_delta = False
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                remaining = max(0.1, deadline - time.monotonic())
                try:
                    raw = ws.recv(timeout=remaining)
                except TimeoutError:
                    break
                mt = json.loads(raw).get("type")
                if mt == "runtime_start_response" and not injected:
                    ws.send(json.dumps({
                        "type": "input",
                        "runtime": {"agent_id": STALL_PROBE_AGENT, "conversation_id": STALL_PROBE_CONVERSATION},
                        "payload": {"kind": "create_message",
                                    "messages": [{"role": "user", "content": "Reply with exactly: OK. No tools."}]},
                    }))
                    injected = True
                elif mt == "stream_delta":
                    saw_delta = True
                elif mt == "turn_finished":
                    return saw_delta  # finished WITH output = healthy
            return False  # no turn_finished within the bound = stall
    except Exception as e:
        _log(f"stall-probe error (treated as no-progress): {e}")
        return False


class Supervisor:
    def __init__(self):
        self._server = AppServer(_log, backend_dir=(None if BACKEND_DIR == PROD_BACKEND_DIR else BACKEND_DIR))
        self._lock_fh = None
        self._stop = threading.Event()
        self._restart_lock = threading.Lock()  # single kill authority

    def _restart_child(self, reason: str) -> None:
        with self._restart_lock:
            _log(f"RESTART child: {reason}")
            self._server.shutdown()
            self._server.ensure()

    def _responsive(self) -> bool:
        try:
            req = urllib.request.Request(APP_SERVER_URL.rstrip("/") + "/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT_S) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    def _health_loop(self) -> None:
        misses = 0
        while not self._stop.wait(HEALTH_INTERVAL_S):
            if not self._server.is_alive():
                self._restart_child("child process died")
                misses = 0
                continue
            if self._responsive():
                misses = 0
            else:
                misses += 1
                _log(f"responsiveness miss {misses}/{HEALTH_MISSES}")
                if misses >= HEALTH_MISSES:
                    self._restart_child(f"{misses} consecutive responsiveness misses")
                    misses = 0

    def _stall_loop(self) -> None:
        if STALL_DISABLED:
            _log("forward-progress stall probe DISABLED via env")
            return
        # Stagger so the two loops don't fire together.
        if self._stop.wait(STALL_INTERVAL_S / 2):
            return
        while not self._stop.wait(STALL_INTERVAL_S):
            if not self._server.is_alive():
                continue  # health loop owns crash restarts
            if not probe_forward_progress():
                self._restart_child("forward-progress stall (no streamed turn within bound)")

    def _rescan_loop(self) -> None:
        while not self._stop.wait(RESCAN_INTERVAL_S):
            child_pid = self._server.proc.pid if self._server.proc else None
            foreign = scan_foreign_writers(own_child_pid=child_pid)
            if foreign:
                _log("TRIPWIRE: foreign backend writer(s) detected (single-writer at risk): "
                     + "; ".join(foreign))

    def run(self) -> int:
        # 1. R1 lock — refuse if another owner holds it.
        self._lock_fh = acquire_backend_lock()
        if self._lock_fh is None:
            _log(f"REFUSING to start: backend lock {LOCK_PATH} is held by another owner. "
                 "Two servers on one backend is the projection-divergence race — "
                 "quiesce the other writer first (plan Unit 8).")
            return 3  # non-zero; launchd ThrottleInterval paces the retry
        _log(f"acquired backend lock; backend_dir={'<prod>' if BACKEND_DIR == PROD_BACKEND_DIR else BACKEND_DIR}")

        # 2. start the child
        try:
            self._server.ensure()
        except Exception as e:
            _log(f"child failed to start: {e}")
            return 4

        # 3. signals — release + shut the child down cleanly
        def _sig(signum, frame):
            _log(f"received signal {signum}, shutting down")
            self._stop.set()
        signal.signal(signal.SIGTERM, _sig)
        signal.signal(signal.SIGINT, _sig)

        # 4. watchdog + tripwire threads
        threads = [
            threading.Thread(target=self._health_loop, daemon=True, name="health"),
            threading.Thread(target=self._stall_loop, daemon=True, name="stall"),
            threading.Thread(target=self._rescan_loop, daemon=True, name="rescan"),
        ]
        for t in threads:
            t.start()

        self._stop.wait()  # block until a signal
        self._server.shutdown()
        if self._lock_fh is not None:
            self._lock_fh.close()  # releases the flock
        _log("stopped")
        return 0


def main() -> int:
    return Supervisor().run()


if __name__ == "__main__":
    raise SystemExit(main())
