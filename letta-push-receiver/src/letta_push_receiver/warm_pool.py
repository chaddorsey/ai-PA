"""Warm subprocess pool — one resident `letta` process per agent.

Each agent has a dedicated subprocess kept alive across pushes. The
process is launched via the agent's existing `~/bin/letta-<slug>`
wrapper, with the stream-json flags injected before `letta` runs. This
preserves the wrapper's env block (canonical credentials, postgres
password, slack token, etc.) — we don't re-implement env in the
receiver.

Concurrency: dispatch is serialized per-agent via a per-handle lock.
Multiple producers can push concurrently to different agents; pushes
to the same agent queue (one prompt at a time per subprocess).

Lifecycle:
- on first push to an agent: spawn the subprocess, await init handshake
- on subsequent pushes: write to existing stdin
- on subprocess death: log + lazy-respawn on next push
- launchd KeepAlive on the receiver handles full restarts
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .config import AgentSpec, log_dir

# Init handshake timeout — stream-json subprocesses emit a system/init
# event when the agent is ready. If we don't see one within this window,
# the subprocess is treated as failed.
INIT_TIMEOUT_S = 60.0

# How long to wait between health-checks of warm subprocesses
HEALTH_PING_INTERVAL_S = 60.0

# Env vars from .env that runtime subprocesses need (the union of what
# the various wrappers export). Shared between the warm pool
# (_build_agent_env) and the App Server (build_runtime_env) so both get
# identical credentials — see the 2026-06-10 gws-creds regression note
# on GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE below.
_ENV_KEYS_FROM_DOTENV = (
    "POSTGRES_PASSWORD",
    "GITEA_MEMFS_TOKEN",
    "SLACK_MCP_XOXP_TOKEN",
    "GITHUB_TOKEN",
    "GRANOLA_API_KEY",
    "GRANOLA_OAUTH_TOKEN",
)


def _load_dotenv_file(env_path: Optional[str] = None) -> Dict[str, str]:
    """Read KEY=VALUE pairs from the repo .env file.

    Module-level so it can be used without a WarmPool instance (the App
    Server supervisor needs the same values but has no `self._dotenv`).
    """
    if env_path is None:
        env_path = os.environ.get(
            "LETTA_PUSH_RECEIVER_ENV_FILE",
            "/Volumes/main-drive/ai-PA/.env",
        )
    out: Dict[str, str] = {}
    try:
        with open(env_path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except Exception:
        pass
    return out


def build_runtime_env() -> Dict[str, str]:
    """Build the base env dict shared by every runtime subprocess.

    This is the agent-independent portion of what used to live only in
    WarmPool._build_agent_env: a minimal PATH, HOME, LETTA_LOCAL_BACKEND_DIR,
    and the curated credentials from .env. Excludes broad host env
    passthrough to keep behavior reproducible. Callers (WarmPool,
    AppServer) may layer per-invocation bits (e.g. per-agent settings) on
    top of this dict.
    """
    env = {
        "PATH": (
            f"{os.path.expanduser('~/.local/bin')}:"
            "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        ),
        "HOME": os.path.expanduser("~"),
        "TERM": "dumb",
        "LETTA_LOCAL_BACKEND_DIR": os.path.expanduser(
            "~/.letta/lc-local-backend"
        ),
        "GITEA_BASE_URL": "http://127.0.0.1:3030",
        "PA_AI_REPO_ROOT": "/Volumes/main-drive/ai-PA",
        "PA_WEB_POSTGRES_PORT": "5433",
        "GMAIL_WATCH_SERVICE_URL": "http://localhost:8094/mcp",
        # gws (Google Workspace CLI) needs file-based creds — the macOS
        # Keychain is unreachable in this spawned context, so without this
        # gws fails and email/Drive/meeting enrichment fetches degrade
        # ("remote Gmail fetch failed (gws CLI error)"). 2026-06-10.
        "GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE": "/Volumes/main-drive/ai-PA/gws-bridge/credentials.json",
    }
    dotenv = _load_dotenv_file()
    for k in _ENV_KEYS_FROM_DOTENV:
        v = dotenv.get(k)
        if v:
            env[k] = v
    return env


@dataclass
class SubprocessHandle:
    spec: AgentSpec
    proc: subprocess.Popen
    started_at: float
    last_prompt_at: float
    push_count: int = 0
    init_seen: bool = False
    init_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    log_path: Path = field(default_factory=lambda: Path("/tmp"))
    reader_thread: Optional[threading.Thread] = None

    def is_alive(self) -> bool:
        return self.proc.poll() is None

    def kill(self, log) -> None:
        try:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        except Exception as e:
            log(f"WARN: kill {self.spec.slug} subprocess failed: {e}")


class WarmPool:
    def __init__(self, agents: Dict[str, AgentSpec], log_fn):
        self.agents = agents
        self.log = log_fn
        self._handles: Dict[str, SubprocessHandle] = {}
        self._pool_lock = threading.Lock()
        self._stopping = False
        self._dotenv: Dict[str, str] = self._load_dotenv()

    def _load_dotenv(self) -> Dict[str, str]:
        env_path = os.environ.get(
            "LETTA_PUSH_RECEIVER_ENV_FILE",
            "/Volumes/main-drive/ai-PA/.env",
        )
        out = _load_dotenv_file(env_path)
        if not out:
            self.log(f"WARN: could not read .env at {env_path}")
        return out

    def _build_agent_env(self, spec: AgentSpec) -> Dict[str, str]:
        """Build the env dict for a warm subprocess.

        Delegates the agent-independent portion (PATH, HOME,
        LETTA_LOCAL_BACKEND_DIR, curated .env credentials) to the
        module-level build_runtime_env() so the App Server supervisor
        (app_server.py) gets an identical base env — DRY, and avoids
        re-introducing the 2026-06-10 gws-creds regression by drifting
        the two env builders apart. No per-agent bits are layered on
        top today (spec is accepted for future use / API stability).
        """
        return build_runtime_env()

    # ---- subprocess lifecycle ----

    def _spawn(self, spec: AgentSpec) -> SubprocessHandle:
        """Spawn a warm subprocess for an agent.

        Bypasses the ~/bin/letta-<slug> wrapper because the wrapper
        hard-codes `--conversation default` and letta-code disallows
        having `--conversation` specified twice (we want a stable
        warm-conversation name per agent so prompt-cache stays hot).

        Instead we replicate the wrapper's env block here (loaded from
        .env at receiver startup) and spawn `letta --backend local
        --agent X --conversation push-warm-X ...` directly.
        """
        # Load env from .env (same as the wrappers do)
        env = self._build_agent_env(spec)

        # letta-code disallows --agent + --conversation when
        # conversation_id isn't the literal "default" alias. We want a
        # stable per-spawn conversation that lives across pushes (memfs +
        # prompt cache stay warm), so we use --new which creates a fresh
        # conversation. The subprocess holds the conversation reference
        # internally; we just keep writing to its stdin.
        letta_bin = env.get("LETTA_BIN", "/opt/homebrew/bin/letta")
        if not os.path.isfile(letta_bin):
            from shutil import which
            letta_bin = which("letta") or letta_bin

        cmd = [
            letta_bin,
            "--backend", "local",
            "--agent", spec.agent_id,
            "--new",
            "--output-format", "stream-json",
            "--input-format", "stream-json",
            "--yolo",
            "--disallowedTools", "web_search,fetch_webpage",
        ]
        self.log(f"spawn {spec.slug}: {shlex.join(cmd)}")

        ts = time.strftime("%Y%m%d-%H%M%S")
        log_path = log_dir() / f"warm-{spec.slug}-{ts}.log"
        log_fh = open(log_path, "w", buffering=1)

        # Working dir = launchpad (avoid walking ai-PA's huge tree)
        launchpad = env.get(
            "LETTA_LAUNCH_DIR", "/Volumes/main-drive/letta-launchpad"
        )
        if not os.path.isdir(launchpad):
            launchpad = str(Path.home())

        proc = subprocess.Popen(
            cmd,
            cwd=launchpad,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log_fh,
            text=True,
            bufsize=1,
        )

        handle = SubprocessHandle(
            spec=spec,
            proc=proc,
            started_at=time.time(),
            last_prompt_at=time.time(),
            log_path=log_path,
        )

        # Start a reader thread that watches stdout for events. It
        # signals init_event when the system/init event arrives, and
        # appends everything to the log file.
        t = threading.Thread(
            target=self._read_stdout,
            args=(handle, log_fh),
            name=f"reader-{spec.slug}",
            daemon=True,
        )
        handle.reader_thread = t
        t.start()

        # Wait for init handshake
        if not handle.init_event.wait(timeout=INIT_TIMEOUT_S):
            handle.kill(self.log)
            log_fh.close()
            raise RuntimeError(
                f"{spec.slug} did not emit system/init within "
                f"{INIT_TIMEOUT_S}s (see {log_path})"
            )
        self.log(f"  {spec.slug} ready ({proc.pid}) — log: {log_path}")
        return handle

    def _read_stdout(self, handle: SubprocessHandle, log_fh) -> None:
        """Read subprocess stdout line by line, parse stream-json events.

        Looks for system/init to signal readiness. Everything goes to
        the log file for post-mortem inspection.
        """
        try:
            for line in iter(handle.proc.stdout.readline, ""):
                if not line:
                    break
                log_fh.write(line)
                log_fh.flush()
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if (
                    obj.get("type") == "system"
                    and obj.get("subtype") == "init"
                    and not handle.init_seen
                ):
                    handle.init_seen = True
                    handle.init_event.set()
        except Exception as e:
            self.log(f"reader for {handle.spec.slug} died: {e}")
        finally:
            try:
                handle.proc.stdout.close()
            except Exception:
                pass
            try:
                log_fh.close()
            except Exception:
                pass

    # ---- public API ----

    def get_or_spawn(self, slug: str) -> SubprocessHandle:
        """Get the warm handle for an agent, spawning if needed."""
        with self._pool_lock:
            handle = self._handles.get(slug)
            if handle and handle.is_alive():
                return handle
            if handle:
                self.log(f"warm subprocess for {slug} died — respawning")
                handle.kill(self.log)
                self._handles.pop(slug, None)

            spec = self.agents.get(slug)
            if not spec:
                raise KeyError(f"unknown agent slug: {slug}")
            handle = self._spawn(spec)
            self._handles[slug] = handle
            return handle

    def dispatch(self, slug: str, prompt: str) -> dict:
        """Write a prompt to the agent's stdin (fire-and-forget).

        Returns immediately with metadata. The actual processing
        happens asynchronously in the warm subprocess.
        """
        handle = self.get_or_spawn(slug)
        with handle.lock:
            try:
                # Stream-json input format expects newline-delimited JSON
                # messages. The user message shape is:
                # {"type": "user", "message": {"role": "user",
                #   "content": [{"type": "text", "text": "..."}]}}
                # Different letta-code versions use slightly different
                # shapes. We'll send a permissive 'text' event that's
                # widely accepted.
                msg = {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}],
                    },
                }
                handle.proc.stdin.write(json.dumps(msg) + "\n")
                handle.proc.stdin.flush()
                handle.last_prompt_at = time.time()
                handle.push_count += 1
                return {
                    "status": "queued",
                    "agent": slug,
                    "pid": handle.proc.pid,
                    "push_count": handle.push_count,
                    "log_path": str(handle.log_path),
                }
            except BrokenPipeError:
                # Subprocess died mid-write — drop the handle and tell
                # the caller. Next dispatch will respawn.
                self.log(
                    f"{slug} subprocess pipe broken on dispatch; will respawn"
                )
                with self._pool_lock:
                    self._handles.pop(slug, None)
                handle.kill(self.log)
                raise

    def status(self) -> List[dict]:
        out = []
        with self._pool_lock:
            for slug, h in self._handles.items():
                out.append({
                    "slug": slug,
                    "agent_id": h.spec.agent_id,
                    "pid": h.proc.pid,
                    "alive": h.is_alive(),
                    "started_at": h.started_at,
                    "last_prompt_at": h.last_prompt_at,
                    "push_count": h.push_count,
                    "uptime_s": time.time() - h.started_at,
                    "log_path": str(h.log_path),
                })
        return out

    def shutdown(self) -> None:
        self._stopping = True
        with self._pool_lock:
            for slug, h in list(self._handles.items()):
                self.log(f"shutting down {slug}")
                h.kill(self.log)
            self._handles.clear()
