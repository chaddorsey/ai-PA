"""letta-code subprocess pool for pa-web-ui (Phase 1, Unit 1.2).

Reimplements the letta-code-sdk `SubprocessTransport` + `Session` layers
plus LettaBot's `session-manager` concurrency patterns in Python.

This unit ships the spawn + control-protocol + concurrency surface. The
reader thread in this module does only the minimum needed for Unit 1.2
behavior (init handshake + control_request dispatch + run-id tracking).
Unit 1.3 expands it with tool-arg merging, seq_id stamping, and ring
buffer; Unit 1.4 adds subscriber fan-out.

See docs/plans/2026-04-20-001-feat-pa-web-ui-letta-code-migration-plan.md
(Unit 1.2 section) and docs/security/pa-web-ui-threat-model.md.
"""

from __future__ import annotations

import json
import os
import queue
import re
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------- config

DEFAULT_MAX_CONCURRENT = int(os.environ.get("PA_WEB_UI_MAX_SUBPROCESSES", "5"))
DEFAULT_INIT_TIMEOUT_S = float(os.environ.get("PA_WEB_UI_SPAWN_TIMEOUT_S", "60"))
DEFAULT_SEND_TIMEOUT_S = float(os.environ.get("PA_WEB_UI_SEND_TIMEOUT_S", "60"))
DEFAULT_CONTROL_TIMEOUT_S = float(os.environ.get("PA_WEB_UI_CONTROL_TIMEOUT_S", "30"))
DEFAULT_SHUTDOWN_GRACE_S = 5.0

# The letta-code CLI refuses to use tools in --disallowedTools, but some
# tools emit control_request (can_use_tool) even so. These are the tools
# we explicitly deny if a can_use_tool arrives for them — mirrors the
# SDK's INTERACTIVE_APPROVAL_TOOLS set.
INTERACTIVE_APPROVAL_TOOLS: Set[str] = {
    "AskUserQuestion",
    "EnterPlanMode",
    "ExitPlanMode",
}

# Tools disallowed at the CLI level (R4 / R4b in the plan).
#
# Originally disallowed: Task, TodoWrite, EnterPlanMode, AskUserQuestion.
# Status as of 2026-04-27:
#
# - Task: was disallowed pending upstream issue #3205 (subagent handle
#   resolution in self-hosted Letta). Fixed in our image via the
#   PATCH-3205 patch applied at Dockerfile build time
#   (letta-memfs-patches/patches/apply_letta_code_self_hosted_handle_fix.py).
#   R4 gate satisfied → unblocked.
# - TodoWrite: original block rationale was specific to LettaBot's
#   headless environment (interactive-approval hang). pa-web has a real
#   control protocol implementation (`_handle_control_request`) that
#   auto-allows non-INTERACTIVE_APPROVAL_TOOLS under --yolo, so the
#   LettaBot-stuck-session pattern doesn't apply here. Unblocked 2026-04-27.
# - EnterPlanMode / AskUserQuestion: stay blocked. These are
#   INTERACTIVE_APPROVAL_TOOLS that the control handler explicitly
#   denies (line ~1492). Unblocking would require new UI plumbing
#   (modal/prompt rendering + response endpoint).
DEFAULT_DISALLOWED_TOOLS: Tuple[str, ...] = (
    "EnterPlanMode",
    "AskUserQuestion",
)

DEFAULT_ALLOWED_TOOLS: Tuple[str, ...] = (
    "Bash",
    "Read",
    "Edit",
    "Write",
    "Glob",
    "Grep",
    "Task",
    "TodoWrite",
    "web_search",
    "conversation_search",
    "manage_todo",
)

DEFAULT_CWD = os.environ.get("PA_WEB_UI_SUBPROCESS_CWD", "/workspace-safe")
LETTA_BINARY = os.environ.get("PA_WEB_UI_LETTA_BINARY", "letta")
LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://letta:8283")

# Ring buffer byte cap — Unit 1.3. Per the plan's R7b, retain events back to
# the most recent completed turn or ~2MB whichever is smaller; clients below
# the floor receive `resync_required` and refetch via loadConversationHistory.
DEFAULT_RING_BUFFER_BYTES = int(
    os.environ.get("PA_WEB_UI_RING_BUFFER_BYTES", str(2_000_000))
)

# Per-subscriber queue depth. A subscriber that fails put_nowait this
# many consecutive times is force-unsubscribed (Unit 1.4).
DEFAULT_SUBSCRIBER_QUEUE_MAX = int(
    os.environ.get("PA_WEB_UI_SUBSCRIBER_QUEUE_MAX", "1000")
)
SLOW_SUBSCRIBER_FAILURE_THRESHOLD = int(
    os.environ.get("PA_WEB_UI_SLOW_SUBSCRIBER_THRESHOLD", "10")
)


# ---------------------------------------------------------------- helpers


def merge_tool_args(existing: str, incoming: str) -> str:
    """Port of lettabot session-manager.ts:629-638 mergeToolArgs.

    Handles both delta-style chunking (each chunk = bytes to append) and
    cumulative-style chunking (each chunk = full string up to that point).
    Exact semantics preserved so pa-web-ui renders tool_call args
    identically to LettaBot for every model.
    """
    if not incoming:
        return existing
    if not existing:
        return incoming
    if incoming == existing:
        return existing
    if incoming.startswith(existing):
        # Cumulative mode — new chunk contains all prior text plus more.
        return incoming
    if existing.endswith(incoming):
        # Old chunk is already a superset (redundant delta).
        return existing
    # Delta mode — concatenate.
    return existing + incoming


# ---------------------------------------------------------------- redactor


# Static regex patterns for common secret shapes. We compile once at module
# load. Order matters: longer / more specific patterns first so they don't
# get swallowed by the generic hex fallback.
_REDACT_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # More-specific patterns FIRST so they win over generic ones.
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "[REDACTED:anthropic-key]"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "[REDACTED:openai-key]"),
    (re.compile(r"xoxb-[A-Za-z0-9\-]{20,}"), "[REDACTED:slack-bot]"),
    (re.compile(r"xapp-[A-Za-z0-9\-]{20,}"), "[REDACTED:slack-app]"),
    (re.compile(r"xoxp-[A-Za-z0-9\-]{20,}"), "[REDACTED:slack-user]"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "[REDACTED:github-pat]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{10,}"), "Bearer [REDACTED]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:aws-access]"),
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[REDACTED:email]"),
    # Fallback: long hex tokens (API keys, hashes). Keep last so specific
    # patterns above match first.
    (re.compile(r"\b[a-f0-9]{40,}\b"), "[REDACTED:hex]"),
]


def load_env_deny_set(env_path: str = "/app/.env") -> Set[str]:
    """Read .env once at crash-log writer init and collect every NON-empty
    value as a literal redaction target. Safe if .env is masked to empty
    (container runs under R30 scrub); returns an empty set and logs nothing.
    """
    deny: Set[str] = set()
    try:
        with open(env_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                _key, _eq, value = line.partition("=")
                value = value.strip().strip('"').strip("'")
                if value and len(value) >= 8:
                    # Ignore very short values — too many false positives.
                    deny.add(value)
    except (OSError, FileNotFoundError):
        pass
    return deny


def redact_text(text: str, env_values: Optional[Iterable[str]] = None) -> str:
    """Run a defensive redaction pass over `text`.

    Applies in order:
    1. Pattern redactions (API keys, tokens, emails, long hex)
    2. Literal replacement of any known env-derived secret values

    Returns the scrubbed text. Empty / None input passes through.
    """
    if not text:
        return text
    out = text
    for pat, replacement in _REDACT_PATTERNS:
        out = pat.sub(replacement, out)
    if env_values:
        for value in env_values:
            if value and value in out:
                out = out.replace(value, "[REDACTED:env]")
    return out


# ---------------------------------------------------------------- crash writer


DEFAULT_CRASH_LOG_DIR = os.environ.get("PA_WEB_UI_CRASH_LOG_DIR", "/app/logs")
DEFAULT_CRASH_LOG_KEEP_PER_CONV = int(
    os.environ.get("PA_WEB_UI_CRASH_LOG_KEEP", "20")
)
DEFAULT_CRASH_LOG_TAIL_BYTES = int(
    os.environ.get("PA_WEB_UI_CRASH_LOG_TAIL_BYTES", str(64 * 1024))
)


def write_crash_log(
    *,
    conv_id: str,
    stdout_tail: str,
    stderr_tail: str,
    returncode: Optional[int],
    env_values: Optional[Iterable[str]] = None,
    log_dir: str = DEFAULT_CRASH_LOG_DIR,
    keep_per_conv: int = DEFAULT_CRASH_LOG_KEEP_PER_CONV,
) -> Optional[str]:
    """Write a redacted crash log for a dead subprocess handle.

    Returns the path written, or None on failure (IO errors are swallowed
    so a crash-during-crash doesn't cascade).
    """
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        return None

    safe_conv = re.sub(r"[^A-Za-z0-9._-]", "_", conv_id)
    ts = time.strftime("%Y%m%dT%H%M%S")
    path = os.path.join(log_dir, f"subprocess-{safe_conv}-{ts}.log")

    body = (
        f"conv_id: {conv_id}\n"
        f"returncode: {returncode}\n"
        f"timestamp: {ts}\n"
        f"\n--- stdout tail ---\n"
        f"{redact_text(stdout_tail, env_values)}\n"
        f"\n--- stderr tail ---\n"
        f"{redact_text(stderr_tail, env_values)}\n"
    )
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
    except OSError:
        return None

    # Rotate: keep at most keep_per_conv most-recent files per conv_id.
    try:
        files = sorted(
            (
                f for f in os.listdir(log_dir)
                if f.startswith(f"subprocess-{safe_conv}-") and f.endswith(".log")
            ),
            reverse=True,
        )
        for stale in files[keep_per_conv:]:
            try:
                os.remove(os.path.join(log_dir, stale))
            except OSError:
                pass
    except OSError:
        pass

    return path


# ---------------------------------------------------------------- ring buffer


class RingBuffer:
    """Byte-bounded event ring with turn-boundary awareness.

    - Events are appended with a monotonic seq_id and tracked size.
    - When total bytes exceed `max_bytes`, oldest events evict.
    - Turn boundaries (`is_turn_boundary=True` on append) are tracked so
      replay consumers can tell whether their requested `since` seq_id
      still lands inside a complete turn, or has been truncated below
      the buffer's retention window.

    Per-conversation thread safety via an internal lock; the reader
    thread is the single writer, Unit 1.4 subscribers are readers.
    """

    def __init__(self, max_bytes: int = DEFAULT_RING_BUFFER_BYTES) -> None:
        self.max_bytes = max_bytes
        self._items: Deque[Tuple[int, Dict[str, Any], int]] = deque()
        self._bytes_total: int = 0
        self._turn_boundary_seq_ids: List[int] = []
        self._lock = threading.Lock()

    def append(
        self, seq_id: int, event: Dict[str, Any], is_turn_boundary: bool = False
    ) -> None:
        size = len(json.dumps(event, separators=(",", ":")).encode("utf-8"))
        with self._lock:
            self._items.append((seq_id, event, size))
            self._bytes_total += size
            if is_turn_boundary:
                self._turn_boundary_seq_ids.append(seq_id)
            # Evict until under cap.
            while self._bytes_total > self.max_bytes and self._items:
                _, _, popped_size = self._items.popleft()
                self._bytes_total -= popped_size
            # Clean up turn-boundary markers that fell out of the buffer.
            if self._items:
                oldest_in_buffer = self._items[0][0]
                self._turn_boundary_seq_ids = [
                    b for b in self._turn_boundary_seq_ids if b >= oldest_in_buffer
                ]
            else:
                self._turn_boundary_seq_ids = []

    def events_since(
        self, since_seq: Optional[int]
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Return (events, resync_required).

        - If since_seq is None: return a fresh subscriber seed (empty list,
          no resync).
        - If since_seq is before the oldest retained seq_id: return empty
          and flag resync_required=True — client must refetch via
          loadConversationHistory().
        - Otherwise: return every event with seq_id > since_seq.
        """
        with self._lock:
            if since_seq is None:
                return [], False
            if not self._items:
                # Buffer empty: if client claims to be ahead, no replay needed.
                return [], False
            oldest_seq = self._items[0][0]
            if since_seq < oldest_seq - 1:
                # Client is behind the buffer's floor.
                return [], True
            return [ev for (s, ev, _sz) in self._items if s > since_seq], False

    def oldest_seq(self) -> int:
        with self._lock:
            return self._items[0][0] if self._items else 0

    def newest_seq(self) -> int:
        with self._lock:
            return self._items[-1][0] if self._items else 0

    @property
    def size_bytes(self) -> int:
        with self._lock:
            return self._bytes_total

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def snapshot_for_status(self) -> Dict[str, Any]:
        """Debug snapshot for /api/subprocess/status."""
        with self._lock:
            return {
                "count": len(self._items),
                "bytes": self._bytes_total,
                "oldest_seq": self._items[0][0] if self._items else None,
                "newest_seq": self._items[-1][0] if self._items else None,
                "turn_boundaries": list(self._turn_boundary_seq_ids),
            }


# ---------------------------------------------------------------- exceptions


class SpawnTimeoutError(Exception):
    """Raised when subprocess init does not complete within the timeout."""


class TurnLockedException(Exception):
    """Raised by send() when another turn is already in flight on the conv.

    Unit 1.5 converts this to HTTP 409 with the turn_locked SSE event.
    """

    def __init__(self, conv_id: str, current_device_id: Optional[str], seq_id: int):
        self.conv_id = conv_id
        self.current_device_id = current_device_id
        self.seq_id = seq_id
        super().__init__(
            f"conv {conv_id} is locked by device {current_device_id} at seq {seq_id}"
        )


class SubprocessDeadError(Exception):
    """Raised when an operation targets a handle whose subprocess has exited."""


# ---------------------------------------------------------------- subscriber


@dataclass
class Subscriber:
    """One attached SSE client's queue + bookkeeping.

    The reader thread publishes events to `queue` via put_nowait. On Full,
    a `slow_subscriber` marker is emitted for this subscriber (not
    silently dropped) and `failure_count` is incremented. After
    SLOW_SUBSCRIBER_FAILURE_THRESHOLD consecutive failures, the
    subscriber is force-unsubscribed so it cannot wedge the fan-out.
    """

    id: str
    queue: "queue.Queue"
    since_seq_id: Optional[int]
    subscribed_at: float = field(default_factory=time.time)
    failure_count: int = 0

    def put_nowait(self, item: Dict[str, Any]) -> None:
        self.queue.put_nowait(item)

    def get(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        return self.queue.get(timeout=timeout)

    def get_nowait(self) -> Dict[str, Any]:
        return self.queue.get_nowait()

    def qsize(self) -> int:
        return self.queue.qsize()


# ---------------------------------------------------------------- handle


@dataclass
class SubprocessHandle:
    """One letta-code subprocess + its bookkeeping state.

    Per the session-manager pattern: per-handle locks for stdin and state;
    a generation counter that bumps on invalidation (so in-flight spawns
    that race with invalidation fail cleanly); an in_flight flag gated by
    the turn lock; a ring buffer + subscriber list populated by later units.
    """

    conv_id: str
    agent_id: str
    process: subprocess.Popen
    init_event: threading.Event
    created_at: float
    generation: int

    # Populated when the subprocess emits its system/init event.
    init_state: Dict[str, Any] = field(default_factory=dict)

    # Synchronization.
    stdin_lock: threading.Lock = field(default_factory=threading.Lock)
    state_lock: threading.Lock = field(default_factory=threading.Lock)
    subscriber_lock: threading.Lock = field(default_factory=threading.Lock)

    # Turn lock (R7c).
    in_flight: bool = False
    in_flight_device_id: Optional[str] = None
    in_flight_started_at: float = 0.0

    # Fork lock (Phase 2 Unit 2.1). Set while a fork-from-this-conv
    # Letta round-trip is in flight; send() treats as turn-locked so
    # a concurrent tab can't start a new turn mid-fork (TOCTOU guard).
    forking: bool = False

    # Activity tracking.
    last_used_at: float = field(default_factory=time.time)
    current_seq_id: int = 0
    event_count: int = 0

    # Subscribers — one per attached SSE client (Unit 1.4).
    subscribers: List[Subscriber] = field(default_factory=list)

    # Ring buffer (Unit 1.3: byte-aware, turn-aware).
    ring_buffer: RingBuffer = field(default_factory=RingBuffer)

    # Tool-call batching (Unit 1.3). Keyed by tool_call_id; each entry
    # holds the partial accumulated args and the base event shape.
    # Flushed on any non-stream_event boundary — mirrors the TS
    # `mergeToolArgs` flush rule (session-manager.ts:691-694).
    pending_tool_calls: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Stale-run filtering. run_ids that have completed are dropped from
    # subsequent emissions (prevents late events from leaking across turns).
    last_completed_run_ids: Set[str] = field(default_factory=set)

    # Outstanding client-initiated control requests waiting for response.
    # request_id -> Future[response dict].
    control_waiters: Dict[str, Future] = field(default_factory=dict)

    # Reader thread.
    reader_thread: Optional[threading.Thread] = None
    alive: bool = True

    def mark_used(self) -> None:
        with self.state_lock:
            self.last_used_at = time.time()

    def bump_seq_id(self) -> int:
        """Monotonic seq_id per handle — stamps each emitted event."""
        with self.state_lock:
            self.current_seq_id += 1
            self.event_count += 1
            return self.current_seq_id

    def describe(self) -> Dict[str, Any]:
        """Snapshot for /api/subprocess/status (Unit 1.6)."""
        with self.state_lock:
            return {
                "conv_id": self.conv_id,
                "agent_id": self.agent_id,
                "pid": self.process.pid,
                "alive": self.alive,
                "generation": self.generation,
                "created_at": self.created_at,
                "last_used_at": self.last_used_at,
                "current_seq_id": self.current_seq_id,
                "event_count": self.event_count,
                "in_flight": self.in_flight,
                "in_flight_device_id": self.in_flight_device_id,
                "forking": self.forking,
                "subscriber_count": len(self.subscribers),
                "init_state": dict(self.init_state),
                "ring_buffer": self.ring_buffer.snapshot_for_status(),
            }

    # --------------- subscriber surface (Unit 1.4) ---------------

    def subscribe(
        self,
        since: Optional[int] = None,
        subscriber_id: Optional[str] = None,
        max_queue: int = DEFAULT_SUBSCRIBER_QUEUE_MAX,
    ) -> Subscriber:
        """Attach a new SSE subscriber.

        - `since=None`: no replay; receive live events only.
        - `since=<int>`: seed the queue with any ring-buffer events with
          seq_id > since. If the ring buffer has evicted events below
          `since`, seed the queue with a single `resync_required` marker
          so the client knows to refetch via loadConversationHistory()
          and resubscribe with since=None.
        - Returned Subscriber should be passed to unsubscribe() on
          disconnect (Flask GeneratorExit in Unit 1.5).
        """
        sub_id = subscriber_id or f"sub-{uuid.uuid4().hex[:8]}"
        q: "queue.Queue" = queue.Queue(maxsize=max_queue)
        subscriber = Subscriber(id=sub_id, queue=q, since_seq_id=since)

        # Seed the queue BEFORE adding to the subscribers list so we hold
        # the correct ordering: any live event that would publish to this
        # subscriber will only arrive after the seed is complete.
        with self.subscriber_lock:
            if since is not None:
                events, resync_required = self.ring_buffer.events_since(since)
                if resync_required:
                    try:
                        q.put_nowait({
                            "type": "resync_required",
                            "reason": "ring_buffer_evicted",
                            "oldest_available_seq_id": self.ring_buffer.oldest_seq(),
                            "_seq_id": 0,
                            "_emitted_at": time.time(),
                        })
                    except queue.Full:
                        # Unreachable on a fresh Queue, but defensive.
                        pass
                else:
                    for ev in events:
                        try:
                            q.put_nowait(ev)
                        except queue.Full:
                            break
            self.subscribers.append(subscriber)
        logger.info(
            "subscriber_attached",
            conv_id=self.conv_id,
            subscriber_id=sub_id,
            since=since,
            seeded_count=q.qsize(),
        )
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        """Detach a subscriber. Safe to call multiple times; safe to call
        on a subscriber that was force-removed by slow-subscriber logic.
        """
        with self.subscriber_lock:
            try:
                self.subscribers.remove(subscriber)
            except ValueError:
                return
        # Drain and close the queue so any final consumer loop exits.
        drained = 0
        while True:
            try:
                subscriber.queue.get_nowait()
                drained += 1
            except queue.Empty:
                break
        logger.info(
            "subscriber_detached",
            conv_id=self.conv_id,
            subscriber_id=subscriber.id,
            drained_count=drained,
        )


# ---------------------------------------------------------------- registry


class SubprocessRegistry:
    """Per-conversation letta-code subprocess pool.

    Thread-safe keyed-pool with creation-lock coalescing, generation-
    counter invalidation, LRU eviction with active-exclusion, and SIGTERM
    handling. Mirrors the semantics of lettabot/src/core/session-manager.ts.

    Dependencies injected at construction so tests can swap them out:
    - spawn_factory: builds the Popen (default: real Popen with the plan's
      CLI args + R30-compliant env dict)
    - reader_factory: builds the reader thread (Unit 1.2 ships a basic
      reader; Unit 1.3 swaps in the merged/seq-stamped reader)
    """

    def __init__(
        self,
        *,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        init_timeout_s: float = DEFAULT_INIT_TIMEOUT_S,
        send_timeout_s: float = DEFAULT_SEND_TIMEOUT_S,
        spawn_factory: Optional[Callable[..., subprocess.Popen]] = None,
        reader_factory: Optional[Callable[..., threading.Thread]] = None,
        cwd: str = DEFAULT_CWD,
        letta_binary: str = LETTA_BINARY,
        letta_base_url: str = LETTA_BASE_URL,
        allowed_tools: Tuple[str, ...] = DEFAULT_ALLOWED_TOOLS,
        disallowed_tools: Tuple[str, ...] = DEFAULT_DISALLOWED_TOOLS,
        yolo: bool = True,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.init_timeout_s = init_timeout_s
        self.send_timeout_s = send_timeout_s
        self._spawn_factory = spawn_factory or self._default_spawn_factory
        self._reader_factory = reader_factory or self._default_reader_factory
        self.cwd = cwd
        self.letta_binary = letta_binary
        self.letta_base_url = letta_base_url
        self.allowed_tools = allowed_tools
        self.disallowed_tools = disallowed_tools
        self.yolo = yolo

        self._lock = threading.Lock()
        self._handles: Dict[str, SubprocessHandle] = {}
        self._creation_locks: Dict[str, Tuple[Future, int]] = {}
        self._generations: Dict[str, int] = {}
        self._shutting_down = False
        # Load known env-secret values once so the crash-log redactor
        # can do literal replacements. Empty set if .env isn't readable
        # (e.g., under the R30 scrub — which is fine; pattern redactions
        # still apply to anything the subprocess printed).
        self._env_deny_values: Set[str] = load_env_deny_set()

    # ------------------------------------------------------------ ensure

    def ensure(
        self,
        agent_id: str,
        conv_id: str,
        disallowed_tools_override: Optional[Tuple[str, ...]] = None,
    ) -> SubprocessHandle:
        """Return a live handle for (agent_id, conv_id) — spawn if needed.

        Coalesces concurrent callers so exactly one spawn happens per
        new conv. Retries cleanly if an invalidation races with the spawn.

        Phase 3 (/btw): pass `disallowed_tools_override` to spawn this
        conv's subprocess with a stricter tool set (e.g., strip
        state-mutating tools from an ephemeral /btw fork so memory
        writes don't propagate to the parent). Only honored on
        first-spawn; existing handles keep their original tool list.
        """
        if self._shutting_down:
            raise SubprocessDeadError("registry is shutting down")

        # Fast path: cached handle.
        with self._lock:
            handle = self._handles.get(conv_id)
            if handle and handle.alive:
                handle.mark_used()
                return handle

            # Is another caller already spawning? Join their Future.
            existing = self._creation_locks.get(conv_id)
            if existing is not None:
                future, gen = existing
                current_gen = self._generations.get(conv_id, 0)
                if gen == current_gen:
                    # Join the in-flight spawn.
                    pass
                else:
                    # Stale lock from a prior generation — drop it.
                    self._creation_locks.pop(conv_id, None)
                    future = None
            else:
                future = None

            if future is None:
                # This caller is the lock holder.
                future = Future()
                current_gen = self._generations.get(conv_id, 0)
                self._creation_locks[conv_id] = (future, current_gen)
                is_holder = True
            else:
                is_holder = False

        if not is_holder:
            # Wait for the holder's spawn to complete and return its handle.
            try:
                return future.result(timeout=self.init_timeout_s + 5)
            except Exception:
                # Holder failed — retry from scratch so a fresh spawn starts.
                return self.ensure(agent_id, conv_id)

        # We are the holder — do the actual spawn.
        try:
            handle = self._spawn_and_initialize(
                agent_id,
                conv_id,
                current_gen,
                disallowed_tools_override=disallowed_tools_override,
            )
            future.set_result(handle)
            return handle
        except Exception as exc:
            future.set_exception(exc)
            raise
        finally:
            with self._lock:
                existing = self._creation_locks.get(conv_id)
                if existing and existing[0] is future:
                    self._creation_locks.pop(conv_id, None)

    def _spawn_and_initialize(
        self,
        agent_id: str,
        conv_id: str,
        birth_gen: int,
        disallowed_tools_override: Optional[Tuple[str, ...]] = None,
    ) -> SubprocessHandle:
        """Spawn a fresh subprocess, send the initialize control_request,
        and wait for the system/init event.

        Checks the generation counter at two points (pre-init, post-init)
        so an invalidation that races with the spawn cleanly kills the
        stale child and retries.
        """
        # Check 1: generation before spawn.
        with self._lock:
            if self._generations.get(conv_id, 0) != birth_gen:
                logger.warning(
                    "spawn_aborted_stale_generation_pre",
                    conv_id=conv_id,
                    birth_gen=birth_gen,
                )
                raise SubprocessDeadError("generation changed before spawn")

        effective_disallowed = (
            disallowed_tools_override
            if disallowed_tools_override is not None
            else self.disallowed_tools
        )
        process = self._spawn_factory(
            agent_id=agent_id,
            conv_id=conv_id,
            cwd=self.cwd,
            letta_binary=self.letta_binary,
            letta_base_url=self.letta_base_url,
            allowed_tools=self.allowed_tools,
            disallowed_tools=effective_disallowed,
            yolo=self.yolo,
        )

        handle = SubprocessHandle(
            conv_id=conv_id,
            agent_id=agent_id,
            process=process,
            init_event=threading.Event(),
            created_at=time.time(),
            generation=birth_gen,
        )

        # Start the reader thread BEFORE sending the initialize request —
        # the reader is the consumer that populates init_state when the
        # system/init event arrives on stdout.
        handle.reader_thread = self._reader_factory(handle, self)
        handle.reader_thread.start()

        # Send initialize request (client-initiated control_request).
        self._write_json(handle, {
            "type": "control_request",
            "request_id": f"init_{uuid.uuid4().hex[:12]}",
            "request": {"subtype": "initialize"},
        })

        # Wait for init event.
        if not handle.init_event.wait(timeout=self.init_timeout_s):
            logger.error(
                "spawn_init_timeout",
                conv_id=conv_id,
                timeout_s=self.init_timeout_s,
            )
            self._destroy_handle(handle)
            raise SpawnTimeoutError(
                f"init event not received within {self.init_timeout_s}s"
            )

        # Check 2: generation post-init.
        with self._lock:
            if self._generations.get(conv_id, 0) != birth_gen:
                logger.warning(
                    "spawn_aborted_stale_generation_post",
                    conv_id=conv_id,
                    birth_gen=birth_gen,
                )
                self._destroy_handle(handle)
                raise SubprocessDeadError("generation changed during init")

            self._handles[conv_id] = handle
            self._evict_if_over_limit(conv_id)

        logger.info(
            "subprocess_spawned",
            conv_id=conv_id,
            agent_id=agent_id,
            pid=process.pid,
            init_state=handle.init_state,
        )
        return handle

    # ------------------------------------------------------------ send

    def send(
        self, handle: SubprocessHandle, message: str, device_id: Optional[str] = None
    ) -> None:
        """Send a user message to a handle. Raises TurnLockedException if
        another turn is in flight (R7c).
        """
        if not handle.alive:
            raise SubprocessDeadError(f"handle for {handle.conv_id} is dead")

        with handle.state_lock:
            if handle.in_flight or handle.forking:
                raise TurnLockedException(
                    conv_id=handle.conv_id,
                    current_device_id=handle.in_flight_device_id,
                    seq_id=handle.current_seq_id,
                )
            handle.in_flight = True
            handle.in_flight_device_id = device_id
            handle.in_flight_started_at = time.time()

        try:
            self._write_json(handle, {
                "type": "user",
                "message": {"role": "user", "content": message},
            })
            handle.mark_used()
        except Exception:
            # On write failure, release the turn lock so the conversation
            # isn't permanently stuck.
            with handle.state_lock:
                handle.in_flight = False
                handle.in_flight_device_id = None
            raise

    def send_control_response(
        self, handle: SubprocessHandle, request_id: str, response: Dict[str, Any]
    ) -> None:
        """Write a control_response to the subprocess's stdin.

        Used by the reader thread when dispatching an incoming
        control_request. Does NOT affect the turn lock — control messages
        are out-of-band from user turns.
        """
        try:
            self._write_json(handle, {
                "type": "control_response",
                "response": {
                    "subtype": "success",
                    "request_id": request_id,
                    "response": response,
                },
            })
            logger.info(
                "control_response_sent",
                conv_id=handle.conv_id,
                request_id=request_id,
                subtype="success",
                response_summary=(
                    "allow" if response.get("behavior") == "allow"
                    else ("deny" if response.get("behavior") == "deny"
                          else "ack")
                ),
            )
        except Exception as exc:
            logger.error(
                "control_response_send_failed",
                conv_id=handle.conv_id,
                request_id=request_id,
                subtype="success",
                error=type(exc).__name__,
                detail=str(exc)[:300],
            )
            raise

    def send_control_response_error(
        self, handle: SubprocessHandle, request_id: str, error: str
    ) -> None:
        try:
            self._write_json(handle, {
                "type": "control_response",
                "response": {
                    "subtype": "error",
                    "request_id": request_id,
                    "error": error,
                },
            })
            logger.info(
                "control_response_sent",
                conv_id=handle.conv_id,
                request_id=request_id,
                subtype="error",
                error=error[:200],
            )
        except Exception as exc:
            logger.error(
                "control_response_send_failed",
                conv_id=handle.conv_id,
                request_id=request_id,
                subtype="error",
                error=type(exc).__name__,
                detail=str(exc)[:300],
            )
            raise

    # ------------------------------------------------------------ invalidate

    def invalidate(self, conv_id: str) -> None:
        """Mark a conversation's handle as stale and bump its generation.

        Next ensure() will spawn a fresh subprocess. Any in-flight spawn
        racing with this call will detect the generation mismatch at its
        post-init check and self-destruct cleanly.
        """
        with self._lock:
            handle = self._handles.pop(conv_id, None)
            self._generations[conv_id] = self._generations.get(conv_id, 0) + 1
        if handle:
            self._destroy_handle(handle)

    # ------------------------------------------------------------ eviction

    def _evict_if_over_limit(self, newly_created_conv_id: str) -> None:
        """LRU eviction excluding handles that are in-flight OR have subscribers.

        Caller must hold self._lock.
        """
        if len(self._handles) <= self.max_concurrent:
            return

        candidates: List[Tuple[float, str, SubprocessHandle]] = []
        for conv_id, handle in self._handles.items():
            if conv_id == newly_created_conv_id:
                continue
            with handle.state_lock:
                if handle.in_flight:
                    continue
            with handle.subscriber_lock:
                if handle.subscribers:
                    continue
            candidates.append((handle.last_used_at, conv_id, handle))

        if not candidates:
            # Transient overshoot — allowed per the session-manager pattern.
            logger.warning(
                "eviction_skipped_all_active",
                size=len(self._handles),
                max=self.max_concurrent,
            )
            return

        candidates.sort(key=lambda t: t[0])  # oldest first
        _, victim_conv_id, victim = candidates[0]
        logger.info("eviction_lru", victim_conv_id=victim_conv_id)
        self._handles.pop(victim_conv_id, None)
        self._generations[victim_conv_id] = (
            self._generations.get(victim_conv_id, 0) + 1
        )
        # Release the registry lock around destroy (destroy may block).
        # We are safely out of the handle map now.

    # ------------------------------------------------------------ shutdown

    def shutdown(self, grace_s: float = DEFAULT_SHUTDOWN_GRACE_S) -> None:
        """Gracefully terminate every subprocess. Flask SIGTERM handler
        calls this.
        """
        with self._lock:
            self._shutting_down = True
            handles = list(self._handles.values())
            self._handles.clear()

        if not handles:
            return

        logger.info("registry_shutdown_begin", count=len(handles))
        # TERM then wait; KILL if needed.
        for h in handles:
            try:
                h.process.terminate()
            except Exception:
                pass

        deadline = time.time() + grace_s
        for h in handles:
            remaining = max(0.0, deadline - time.time())
            try:
                h.process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    h.process.kill()
                except Exception:
                    pass
            h.alive = False

        logger.info("registry_shutdown_complete")

    def install_sigterm_handler(self) -> None:
        """Register SIGTERM → self.shutdown() on the current process."""
        def _handler(signum: int, frame: Any) -> None:
            logger.info("sigterm_received", signum=signum)
            self.shutdown()
            # After cleanup, re-raise default behavior (process exit).
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGTERM)

        try:
            signal.signal(signal.SIGTERM, _handler)
        except ValueError:
            # Not in main thread (e.g., tests) — skip silently.
            logger.debug("sigterm_handler_skipped_non_main_thread")

    # ------------------------------------------------------------ introspection

    def list_handles(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [h.describe() for h in self._handles.values()]

    # ------------------------------------------------------------ internals

    def _write_json(self, handle: SubprocessHandle, payload: Dict[str, Any]) -> None:
        """Serialize + write one JSON line to the subprocess's stdin.

        Held under handle.stdin_lock so concurrent writers (user message,
        control response) serialize cleanly.
        """
        with handle.stdin_lock:
            if not handle.alive or handle.process.poll() is not None:
                handle.alive = False
                raise SubprocessDeadError(f"stdin closed for {handle.conv_id}")
            try:
                line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
                handle.process.stdin.write(line)
                handle.process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                logger.warning(
                    "stdin_write_failed",
                    conv_id=handle.conv_id,
                    error=str(exc),
                )
                handle.alive = False
                raise SubprocessDeadError(str(exc)) from exc

    def _destroy_handle(self, handle: SubprocessHandle) -> None:
        handle.alive = False
        try:
            handle.process.terminate()
        except Exception:
            pass
        try:
            handle.process.wait(timeout=DEFAULT_SHUTDOWN_GRACE_S)
        except Exception:
            try:
                handle.process.kill()
            except Exception:
                pass

    # ------------------------------------------------------------ factories

    @staticmethod
    def _default_spawn_factory(
        *,
        agent_id: str,
        conv_id: str,
        cwd: str,
        letta_binary: str,
        letta_base_url: str,
        allowed_tools: Tuple[str, ...],
        disallowed_tools: Tuple[str, ...],
        yolo: bool,
    ) -> subprocess.Popen:
        """Build the subprocess with R30-compliant env dict.

        Explicitly does NOT inherit the container's env. The subprocess
        sees only the four vars listed here — no POSTGRES_PASSWORD,
        OPENAI_API_KEY, SLACK_BOT_TOKEN, etc.
        """
        # letta-code 0.23.8 quirk: --agent can only be combined with
        # --conversation when conv_id is the "default" alias. For a real
        # UUID, --conversation alone is sufficient (the conv already
        # knows its agent); passing --agent triggers
        # "Error: --conversation cannot be used with --agent".
        args: List[str] = [letta_binary]
        if conv_id == "default":
            args += ["--agent", agent_id, "--conversation", "default"]
        else:
            args += ["--conversation", conv_id]
        args += [
            "--output-format", "stream-json",
            "--input-format", "stream-json",
        ]
        # NOTE: --memfs is NOT passed. R5 in the plan assumed memfs was
        # universally available, but letta-code 0.23.8 gates it on Letta
        # Cloud (`--memfs is only available on Letta Cloud (api.letta.com)`).
        # On self-hosted Letta 0.16.7 the flag causes immediate subprocess
        # exit with returncode=1. Accept memfs_enabled=false and revisit
        # when self-hosted gains the capability.
        if yolo:
            args.append("--yolo")
        if allowed_tools:
            args += ["--allowedTools", ",".join(allowed_tools)]
        if disallowed_tools:
            args += ["--disallowedTools", ",".join(disallowed_tools)]

        env = {
            "LETTA_BASE_URL": letta_base_url,
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/root",
            "TERM": "dumb",
        }
        # Canonical-store access (Layer-1 reference + Layer-5 signals via
        # Gitea HTTP). MC reads/writes `agents-canonical/*` via Bash + curl
        # in its tool calls; without these, the subprocess sees empty
        # GITEA_MEMFS_TOKEN and falls into a credential-hunt spiral.
        # Per R30: still no broad container env inheritance — these are
        # explicit allowlist additions, not a wildcard pass-through.
        for k in ("GITEA_MEMFS_TOKEN", "GITEA_BASE_URL"):
            v = os.environ.get(k)
            if v:
                env[k] = v

        return subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

    def _default_reader_factory(
        self, handle: SubprocessHandle, registry: "SubprocessRegistry"
    ) -> threading.Thread:
        """Minimal reader — Unit 1.2 scope.

        Parses stdout line-by-line, handles init event and control_request
        dispatch, and appends all other events to the ring buffer. Unit
        1.3 swaps in a richer reader with seq_id stamping, tool-arg
        merging, and subscriber fan-out.
        """
        t = threading.Thread(
            target=_reader_loop,
            args=(handle, registry),
            name=f"subproc-reader-{handle.conv_id[:8]}",
            daemon=True,
        )
        return t


# ---------------------------------------------------------------- reader


def _reader_loop(handle: SubprocessHandle, registry: SubprocessRegistry) -> None:
    """Reader loop — parses stdout line-by-line and dispatches.

    Keeps a rolling tail of parsed-and-raw output so that if the
    subprocess crashes, Unit 1.6's crash-log writer can dump the last
    ~64KB of stdout (redacted) alongside stderr for debugging.
    """
    stdout = handle.process.stdout
    stderr = handle.process.stderr
    if stdout is None:
        logger.error("reader_no_stdout", conv_id=handle.conv_id)
        handle.alive = False
        handle.init_event.set()
        return

    # Rolling tail buffer for crash logging. We keep raw lines (pre-parse)
    # because the crash-time view is "what did the subprocess actually
    # emit?", not the filtered event stream.
    tail_lines: Deque[str] = deque(maxlen=512)

    for raw_line in iter(stdout.readline, b""):
        if not raw_line:
            break
        line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
        tail_lines.append(line)
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("reader_non_json", conv_id=handle.conv_id, line=line[:200])
            continue

        try:
            _dispatch_event(handle, registry, event)
        except Exception as exc:
            logger.exception(
                "reader_dispatch_error", conv_id=handle.conv_id, error=str(exc)
            )

    # Subprocess exited.
    handle.alive = False
    handle.init_event.set()
    for req_id, future in list(handle.control_waiters.items()):
        if not future.done():
            future.set_exception(SubprocessDeadError("subprocess exited"))

    returncode = handle.process.poll()

    # Collect stderr non-blocking (won't wait if empty).
    stderr_tail = ""
    if stderr is not None:
        try:
            stderr_bytes = stderr.read() or b""
            stderr_tail = stderr_bytes.decode("utf-8", errors="replace")
        except Exception:
            stderr_tail = ""

    stdout_tail = "\n".join(tail_lines)
    # Cap to the configured tail byte budget to keep crash logs bounded.
    if len(stdout_tail) > DEFAULT_CRASH_LOG_TAIL_BYTES:
        stdout_tail = stdout_tail[-DEFAULT_CRASH_LOG_TAIL_BYTES:]
    if len(stderr_tail) > DEFAULT_CRASH_LOG_TAIL_BYTES:
        stderr_tail = stderr_tail[-DEFAULT_CRASH_LOG_TAIL_BYTES:]

    # Only write a crash log for unclean exits (non-zero rc) or if we
    # never got the init event (indicates spawn failure).
    is_unclean = (returncode not in (None, 0)) or not handle.init_state
    if is_unclean:
        path = write_crash_log(
            conv_id=handle.conv_id,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            returncode=returncode,
            env_values=registry._env_deny_values,
        )
        logger.warning(
            "subprocess_crash_logged",
            conv_id=handle.conv_id,
            returncode=returncode,
            path=path,
        )
    logger.info(
        "reader_exit",
        conv_id=handle.conv_id,
        returncode=returncode,
    )


def _dispatch_event(
    handle: SubprocessHandle, registry: SubprocessRegistry, event: Dict[str, Any]
) -> None:
    """Route one parsed event to its appropriate handler.

    Ordering rules (from SDK study + plan):
    - system/init: populate init_state and signal init_event. Still emit
      to subscribers (UI may surface "connected").
    - control_request: dispatch + respond over stdin. Do NOT forward to
      subscribers (internal protocol).
    - control_response: match to a pending client-initiated request's
      Future. Do NOT forward.
    - stream_event: buffer tool-call chunks; do NOT emit until flush.
    - any other event: first flush pending tool-calls (merged into a
      single tool_call event), then emit the triggering event.
    - result: turn boundary. Release turn lock, absorb run_ids into
      last_completed_run_ids, mark a turn-boundary in the ring buffer.
    - stale-run events (run_id in last_completed_run_ids): drop.
    """
    event_type = event.get("type")

    # --- control plane: never forwarded to subscribers ---
    if event_type == "control_request":
        try:
            _handle_control_request(handle, registry, event)
        except Exception as exc:
            logger.error(
                "control_request_dispatch_crash",
                conv_id=handle.conv_id,
                request_id=event.get("request_id", ""),
                error=type(exc).__name__,
                detail=str(exc)[:300],
            )
            raise
        return

    if event_type == "control_response":
        resp = event.get("response", {})
        req_id = resp.get("request_id")
        waiter = handle.control_waiters.pop(req_id, None) if req_id else None
        if waiter and not waiter.done():
            waiter.set_result(resp)
        return

    # --- init handshake: also forward to subscribers ---
    if event_type == "system" and event.get("subtype") == "init":
        init_fields = {
            k: v for k, v in event.items() if k not in ("type", "subtype")
        }
        handle.init_state.update(init_fields)
        handle.init_event.set()
        _emit(handle, event, is_turn_boundary=False)
        return

    # --- stream_event: buffer tool-call deltas ---
    if event_type == "stream_event":
        _absorb_stream_event(handle, event)
        return

    # --- any non-stream_event: flush pending tool-calls first ---
    if handle.pending_tool_calls:
        _flush_pending_tool_calls(handle)

    # --- stale-run filter ---
    run_id = event.get("run_id")
    if run_id and run_id in handle.last_completed_run_ids:
        logger.debug("stale_event_dropped", conv_id=handle.conv_id, run_id=run_id)
        return

    # --- turn complete: mark boundary, release lock, absorb run_ids ---
    if event_type == "result":
        run_ids = event.get("run_ids") or []
        with handle.state_lock:
            handle.in_flight = False
            handle.in_flight_device_id = None
            for rid in run_ids:
                handle.last_completed_run_ids.add(rid)
        _emit(handle, event, is_turn_boundary=True)
        return

    _emit(handle, event, is_turn_boundary=False)


def _absorb_stream_event(handle: SubprocessHandle, event: Dict[str, Any]) -> None:
    """Buffer a tool-call-shaped stream_event into pending_tool_calls.

    letta-code's stream-json emits incremental `stream_event` wrappers that
    contain per-delta fragments of a tool_call being composed. We buffer
    those by tool_call_id and merge their argument chunks; a full tool_call
    event is yielded to subscribers when the next non-stream_event arrives.

    Event shape (best-effort inference from SDK; validated in Unit 1.3
    fixture tests). Typical fields observed:
      event.event_type == "tool_use_delta" | "tool_use_start" | ...
      event.tool_call_id
      event.tool_name
      event.arguments_delta   (delta mode)
      event.arguments         (cumulative mode)
      event.run_id
    Unknown shapes pass through untouched so we fail-safe on drift.
    """
    stream_inner = event.get("event") or event  # some emitters wrap
    tool_call_id = stream_inner.get("tool_call_id")
    if not tool_call_id:
        # Not a tool_call-shaped stream event — emit as-is (unknown
        # stream_event subtypes still go to subscribers so the frontend
        # can surface novel signals).
        _emit(handle, event, is_turn_boundary=False)
        return

    existing = handle.pending_tool_calls.get(tool_call_id)
    incoming_args = (
        stream_inner.get("arguments_delta")
        or stream_inner.get("arguments")
        or ""
    )
    if existing is None:
        handle.pending_tool_calls[tool_call_id] = {
            "type": "tool_call",
            "tool_call_id": tool_call_id,
            "tool_name": stream_inner.get("tool_name"),
            "run_id": stream_inner.get("run_id"),
            "arguments": incoming_args,
        }
    else:
        existing["arguments"] = merge_tool_args(
            existing.get("arguments", ""), incoming_args
        )
        # Prefer a populated tool_name if we didn't have one yet.
        if not existing.get("tool_name") and stream_inner.get("tool_name"):
            existing["tool_name"] = stream_inner.get("tool_name")


def _flush_pending_tool_calls(handle: SubprocessHandle) -> None:
    """Emit accumulated tool_call events and clear the buffer.

    Mirrors session-manager.ts:691-694's `flushPending()`. Each pending
    tool-call becomes one tool_call event on the subscriber stream.
    """
    for tool_call_id, partial in list(handle.pending_tool_calls.items()):
        _emit(handle, partial, is_turn_boundary=False)
    handle.pending_tool_calls.clear()


def _emit(
    handle: SubprocessHandle,
    event: Dict[str, Any],
    *,
    is_turn_boundary: bool,
) -> None:
    """Stamp the envelope, append to ring buffer, and (Unit 1.4) publish
    to subscribers.

    Envelope fields: seq_id (monotonic per handle), emitted_at (wall
    clock), request_id (if the source event supplied one, otherwise
    derived from run_id if available). These let the frontend correlate
    events across a conversation and lets subscribers deduplicate on
    resume.
    """
    seq = handle.bump_seq_id()
    stamped = dict(event)
    stamped["_seq_id"] = seq
    stamped.setdefault("_emitted_at", time.time())
    # request_id: prefer event-supplied, else run_id, else empty.
    request_id = event.get("request_id") or event.get("run_id") or ""
    if request_id:
        stamped.setdefault("_request_id", request_id)
    handle.ring_buffer.append(seq, stamped, is_turn_boundary=is_turn_boundary)
    _publish_to_subscribers(handle, stamped)


def _publish_to_subscribers(
    handle: SubprocessHandle, stamped: Dict[str, Any]
) -> None:
    """Fan out one stamped event to every attached subscriber.

    Error isolation: one slow subscriber does NOT affect others.
    On Queue.Full:
      - a `slow_subscriber` marker is pushed FOR THAT SUBSCRIBER ONLY
        (clients can surface "we're degrading")
      - failure_count increments
      - the event itself is dropped for that subscriber (but not others)
    After SLOW_SUBSCRIBER_FAILURE_THRESHOLD consecutive failures, the
    subscriber is force-unsubscribed so it cannot consume reader CPU
    indefinitely.
    """
    with handle.subscriber_lock:
        subs = list(handle.subscribers)

    to_unsubscribe: List[Subscriber] = []

    for sub in subs:
        try:
            sub.put_nowait(stamped)
            sub.failure_count = 0
        except queue.Full:
            sub.failure_count += 1
            logger.debug(
                "subscriber_full_drop",
                conv_id=handle.conv_id,
                subscriber_id=sub.id,
                failure_count=sub.failure_count,
                seq_id=stamped.get("_seq_id"),
            )
            # Best-effort: drop an earlier event to make room for the
            # slow_subscriber marker so the client hears about the
            # degradation. Tolerate further Full errors silently.
            marker = {
                "type": "slow_subscriber",
                "subscriber_id": sub.id,
                "conv_id": handle.conv_id,
                "dropped_seq_id": stamped.get("_seq_id"),
                "_seq_id": 0,
                "_emitted_at": time.time(),
            }
            try:
                # Drain one to make headroom, then push marker.
                try:
                    sub.queue.get_nowait()
                except queue.Empty:
                    pass
                sub.queue.put_nowait(marker)
            except queue.Full:
                pass  # Truly stuck; unsubscribe below will handle.
            if sub.failure_count >= SLOW_SUBSCRIBER_FAILURE_THRESHOLD:
                to_unsubscribe.append(sub)

    for sub in to_unsubscribe:
        logger.warning(
            "subscriber_force_unsubscribed",
            conv_id=handle.conv_id,
            subscriber_id=sub.id,
            failure_count=sub.failure_count,
        )
        handle.unsubscribe(sub)


def _handle_control_request(
    handle: SubprocessHandle, registry: SubprocessRegistry, event: Dict[str, Any]
) -> None:
    """Dispatch an incoming control_request.

    Known subtypes (from SDK study):
    - can_use_tool: tool approval. Under --yolo, allow non-INTERACTIVE
      tools. Deny INTERACTIVE_APPROVAL_TOOLS (they're disallowed anyway,
      but be defensive).
    - execute_external_tool: subprocess is asking the client to run a
      registered external tool. We don't register external tools in
      Phase 1, so this should never fire; return an error if it does.
    - recover_pending_approvals: subprocess may echo our own request back
      (unlikely as inbound); handle defensively.
    - interrupt: graceful abort request; acknowledge.
    - unknown: log warning, deny generically.

    Each request_id flows through three log lines:
      control_request_received → control_request_classified → control_response_sent
    A break in that chain (any of the three missing) is the diagnostic
    signal that the approval flow stranded the run.
    """
    request_id = event.get("request_id", "")
    request = event.get("request") or {}
    subtype = request.get("subtype")
    tool_name = request.get("tool_name", "") if subtype == "can_use_tool" else ""

    logger.info(
        "control_request_received",
        conv_id=handle.conv_id,
        request_id=request_id,
        subtype=subtype,
        tool_name=tool_name,
    )

    if not request_id:
        logger.warning(
            "control_request_missing_id",
            conv_id=handle.conv_id,
            request=request,
        )
        return

    if subtype == "can_use_tool":
        if tool_name in INTERACTIVE_APPROVAL_TOOLS:
            classification = "deny_interactive"
            logger.info(
                "control_request_classified",
                conv_id=handle.conv_id,
                request_id=request_id,
                classification=classification,
                tool_name=tool_name,
            )
            registry.send_control_response(
                handle, request_id, {"behavior": "deny", "message": "tool disallowed"}
            )
            return
        # Under --yolo, allow all other tool use.
        classification = "allow"
        logger.info(
            "control_request_classified",
            conv_id=handle.conv_id,
            request_id=request_id,
            classification=classification,
            tool_name=tool_name,
        )
        registry.send_control_response(
            handle, request_id, {"behavior": "allow"}
        )
        return

    if subtype == "execute_external_tool":
        logger.info(
            "control_request_classified",
            conv_id=handle.conv_id,
            request_id=request_id,
            classification="error_no_external_tools",
        )
        # We don't register external tools in Phase 1.
        registry.send_control_response_error(
            handle,
            request_id,
            "no external tools registered",
        )
        return

    if subtype == "interrupt":
        logger.info(
            "control_request_classified",
            conv_id=handle.conv_id,
            request_id=request_id,
            classification="interrupt_ack",
        )
        registry.send_control_response(handle, request_id, {})
        return

    # Unknown subtype — deny generically.
    logger.warning(
        "control_request_classified",
        conv_id=handle.conv_id,
        request_id=request_id,
        classification="error_unknown_subtype",
        subtype=subtype,
    )
    registry.send_control_response_error(
        handle, request_id, f"unknown subtype: {subtype}"
    )


# ---------------------------------------------------------------- main entrypoint


_registry_singleton: Optional[SubprocessRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> SubprocessRegistry:
    """Module-level singleton registry. Flask app.py calls this at import."""
    global _registry_singleton
    with _registry_lock:
        if _registry_singleton is None:
            _registry_singleton = SubprocessRegistry()
            _registry_singleton.install_sigterm_handler()
        return _registry_singleton


def reset_registry_for_tests() -> None:
    """Tests call this between cases to reset the singleton."""
    global _registry_singleton
    with _registry_lock:
        if _registry_singleton is not None:
            _registry_singleton.shutdown()
        _registry_singleton = None
