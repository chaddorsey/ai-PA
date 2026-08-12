"""Supervises a resident `letta server --listen` App Server (warm runtime).

One responsibility: App Server process lifecycle. Per-task dispatch lives in
app_server_client.py. Env mirrors warm_pool (shared build_runtime_env()).
"""
from __future__ import annotations
import subprocess, threading, time
from pathlib import Path
from .config import log_dir, APP_SERVER_LISTEN
from .warm_pool import build_runtime_env  # extracted shared env builder

READY_TIMEOUT_S = 60.0


def _is_ready_line(line: str) -> bool:
    # Task-1 spike: server prints "Listening on ws://127.0.0.1:4577" when ready.
    return "listening on ws://" in line.lower()


class AppServer:
    def __init__(self, log_fn):
        self.log = log_fn
        self.proc: subprocess.Popen | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    @property
    def base_url(self) -> str:
        # ws://host:port  ->  http://host:port  (OpenAI-compatible routes share the port)
        return APP_SERVER_LISTEN.replace("ws://", "http://", 1)

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def ensure(self) -> None:
        with self._lock:
            if self.is_alive():
                return
            self._start_locked()

    def start(self) -> None:
        with self._lock:
            self._start_locked()

    def _start_locked(self) -> None:
        env = build_runtime_env()
        letta_bin = env.get("LETTA_BIN", "/opt/homebrew/bin/letta")
        # Task-1 spike: --backend local is REQUIRED, else --openai-api hits the
        # cloud APIBackend and fails with "Missing LETTA_API_KEY".
        cmd = [letta_bin, "server", "--backend", "local",
               "--listen", APP_SERVER_LISTEN, "--openai-api"]
        ts = time.strftime("%Y%m%d-%H%M%S")
        log_fh = open(log_dir() / f"app-server-{ts}.log", "w", buffering=1)
        self._ready.clear()
        self.proc = subprocess.Popen(
            cmd, env=env, stdout=subprocess.PIPE, stderr=log_fh, text=True, bufsize=1,
        )
        threading.Thread(target=self._read, args=(log_fh,), daemon=True).start()
        if not self._ready.wait(timeout=READY_TIMEOUT_S):
            raise RuntimeError(f"App Server not ready within {READY_TIMEOUT_S}s")
        self.log(f"App Server ready ({self.proc.pid}) at {self.base_url}")

    def _read(self, log_fh) -> None:
        assert self.proc and self.proc.stdout
        for line in iter(self.proc.stdout.readline, ""):
            log_fh.write(line); log_fh.flush()
            if _is_ready_line(line):
                self._ready.set()

    def shutdown(self) -> None:
        if self.is_alive():
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
