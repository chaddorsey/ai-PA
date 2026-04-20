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
import signal
import subprocess
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

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
DEFAULT_DISALLOWED_TOOLS: Tuple[str, ...] = (
    "Task",
    "TodoWrite",
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
    "web_search",
    "conversation_search",
    "manage_todo",
)

DEFAULT_CWD = os.environ.get("PA_WEB_UI_SUBPROCESS_CWD", "/workspace-safe")
LETTA_BINARY = os.environ.get("PA_WEB_UI_LETTA_BINARY", "letta")
LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://letta:8283")


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

    # Activity tracking.
    last_used_at: float = field(default_factory=time.time)
    current_seq_id: int = 0
    event_count: int = 0

    # Subscribers (Unit 1.4 populates).
    subscribers: List["queue.Queue"] = field(default_factory=list)

    # Ring buffer (Unit 1.3 refines to byte-aware + turn-aware).
    ring_buffer: List[Dict[str, Any]] = field(default_factory=list)

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
                "subscriber_count": len(self.subscribers),
                "init_state": dict(self.init_state),
            }


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

    # ------------------------------------------------------------ ensure

    def ensure(self, agent_id: str, conv_id: str) -> SubprocessHandle:
        """Return a live handle for (agent_id, conv_id) — spawn if needed.

        Coalesces concurrent callers so exactly one spawn happens per
        new conv. Retries cleanly if an invalidation races with the spawn.
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
            handle = self._spawn_and_initialize(agent_id, conv_id, current_gen)
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
        self, agent_id: str, conv_id: str, birth_gen: int
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

        process = self._spawn_factory(
            agent_id=agent_id,
            conv_id=conv_id,
            cwd=self.cwd,
            letta_binary=self.letta_binary,
            letta_base_url=self.letta_base_url,
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
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
            if handle.in_flight:
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
        self._write_json(handle, {
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": request_id,
                "response": response,
            },
        })

    def send_control_response_error(
        self, handle: SubprocessHandle, request_id: str, error: str
    ) -> None:
        self._write_json(handle, {
            "type": "control_response",
            "response": {
                "subtype": "error",
                "request_id": request_id,
                "error": error,
            },
        })

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
        args: List[str] = [
            letta_binary,
            "--agent", agent_id,
            "--conversation", conv_id,
            "--output-format", "stream-json",
            "--input-format", "stream-json",
        ]
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
    """Unit 1.2 reader loop.

    Handles:
    - system/init event → populate init_state, signal init_event
    - control_request → dispatch per subtype, emit control_response
    - result/done → mark in_flight=False, absorb run_ids
    - everything else → append to ring buffer for later subscriber fan-out

    Unit 1.3 will refine this to include seq_id stamping, tool-arg merge,
    per-subscriber fan-out, and byte-bounded ring buffer.
    """
    stdout = handle.process.stdout
    if stdout is None:
        logger.error("reader_no_stdout", conv_id=handle.conv_id)
        handle.alive = False
        handle.init_event.set()
        return

    for raw_line in iter(stdout.readline, b""):
        if not raw_line:
            break
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
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
    # Unblock any callers waiting on init.
    handle.init_event.set()
    # Unblock any outstanding control waiters.
    for req_id, future in list(handle.control_waiters.items()):
        if not future.done():
            future.set_exception(SubprocessDeadError("subprocess exited"))
    logger.info(
        "reader_exit",
        conv_id=handle.conv_id,
        returncode=handle.process.poll(),
    )


def _dispatch_event(
    handle: SubprocessHandle, registry: SubprocessRegistry, event: Dict[str, Any]
) -> None:
    """Route one parsed event to its appropriate handler."""
    event_type = event.get("type")

    if event_type == "system" and event.get("subtype") == "init":
        # Capture the full init payload for introspection.
        init_fields = {
            k: v for k, v in event.items()
            if k not in ("type", "subtype")
        }
        handle.init_state.update(init_fields)
        handle.init_event.set()
        _append_to_ring(handle, event)
        return

    if event_type == "control_request":
        _handle_control_request(handle, registry, event)
        return

    if event_type == "control_response":
        # Response to a client-initiated control_request (e.g., our
        # recover_pending_approvals probe). Match by request_id.
        resp = event.get("response", {})
        req_id = resp.get("request_id")
        waiter = handle.control_waiters.pop(req_id, None) if req_id else None
        if waiter and not waiter.done():
            waiter.set_result(resp)
        return

    if event_type == "result":
        # Turn complete — release turn lock and absorb run_ids.
        run_ids = event.get("run_ids") or []
        with handle.state_lock:
            handle.in_flight = False
            handle.in_flight_device_id = None
            for rid in run_ids:
                handle.last_completed_run_ids.add(rid)
        _append_to_ring(handle, event)
        return

    # Stale-run filter: drop events belonging to a completed run.
    run_id = event.get("run_id")
    if run_id and run_id in handle.last_completed_run_ids:
        logger.debug(
            "stale_event_dropped", conv_id=handle.conv_id, run_id=run_id
        )
        return

    _append_to_ring(handle, event)


def _append_to_ring(handle: SubprocessHandle, event: Dict[str, Any]) -> None:
    """Minimal ring-buffer append — Unit 1.3 will replace with byte-aware
    turn-boundary ring.
    """
    seq = handle.bump_seq_id()
    stamped = {**event, "_seq_id": seq}
    handle.ring_buffer.append(stamped)
    # Cap at 500 events for now — Unit 1.3 replaces with ~2MB byte cap.
    if len(handle.ring_buffer) > 500:
        handle.ring_buffer.pop(0)


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
    """
    request_id = event.get("request_id", "")
    request = event.get("request") or {}
    subtype = request.get("subtype")

    if not request_id:
        logger.warning(
            "control_request_missing_id",
            conv_id=handle.conv_id,
            request=request,
        )
        return

    if subtype == "can_use_tool":
        tool_name = request.get("tool_name", "")
        if tool_name in INTERACTIVE_APPROVAL_TOOLS:
            registry.send_control_response(
                handle, request_id, {"behavior": "deny", "message": "tool disallowed"}
            )
            logger.info(
                "control_denied_interactive_tool",
                conv_id=handle.conv_id,
                tool_name=tool_name,
            )
            return
        # Under --yolo, allow all other tool use.
        registry.send_control_response(
            handle, request_id, {"behavior": "allow"}
        )
        return

    if subtype == "execute_external_tool":
        # We don't register external tools in Phase 1.
        registry.send_control_response_error(
            handle,
            request_id,
            "no external tools registered",
        )
        return

    if subtype == "interrupt":
        registry.send_control_response(handle, request_id, {})
        return

    # Unknown subtype — deny generically.
    logger.warning(
        "control_request_unknown_subtype",
        conv_id=handle.conv_id,
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
