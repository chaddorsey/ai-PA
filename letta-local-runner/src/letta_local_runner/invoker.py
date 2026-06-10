"""Subprocess invocation with per-agent serialization.

Forks `letta --backend local --agent <id> --conversation <id> -p <message>`,
holds a per-agent asyncio.Lock for the duration. Detects the empirically-
verified race-loss condition (exit 0 + empty stdout) and retries once.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, Optional

import structlog

from letta_local_runner.settings import Settings

log = structlog.get_logger()


@dataclass
class InvokeRequest:
    agent_id: str
    message: str
    conversation_id: Optional[str] = None  # accepted for API forward-compat; ignored
                                            # by current letta-code (which rejects
                                            # --conversation with --agent). Each
                                            # invocation gets --new. Memfs supplies
                                            # all durable state.
    timeout: Optional[int] = None          # default: settings.default_timeout_seconds


@dataclass
class InvokeResult:
    status: str                # "success" | "race_recovered" | "timeout" | "error"
    agent_response: str
    duration_seconds: float
    letta_exit: int
    retried: bool
    stdout_truncated: str
    stderr_truncated: str
    log_path: str


_STDOUT_TRUNCATE = 2048
_STDERR_TRUNCATE = 2048
_RECENT_HISTORY = 20


class Invoker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._agent_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._recent: Deque[dict] = deque(maxlen=_RECENT_HISTORY)
        self._inflight: Dict[str, float] = {}    # agent_id -> started_at epoch

    # ---- introspection -------------------------------------------------------

    def status(self) -> dict:
        now = time.time()
        return {
            "inflight": {
                aid: round(now - started, 1)
                for aid, started in self._inflight.items()
            },
            "recent": list(self._recent),
        }

    # ---- main entry point ----------------------------------------------------

    async def invoke(self, req: InvokeRequest) -> InvokeResult:
        timeout = req.timeout or self.settings.default_timeout_seconds
        lock = self._agent_locks[req.agent_id]

        async with lock:
            self._inflight[req.agent_id] = time.time()
            try:
                # pull-on-start: bring the agent's memfs up to date with the hub
                # before it acts on (possibly stale) local memory. Best-effort.
                if self.settings.memfs_sync_enabled:
                    await self._memfs_sync_pull(req.agent_id)

                result = await self._spawn_once(req, timeout)
                if self._looks_like_race_loss(result):
                    log.warning("race_loss_detected", agent_id=req.agent_id)
                    await asyncio.sleep(self.settings.race_recovery_delay_seconds)
                    result = await self._spawn_once(req, timeout)
                    result.retried = True
                    if result.status == "success":
                        result.status = "race_recovered"
            finally:
                self._inflight.pop(req.agent_id, None)

            # push-on-write: letta-code committed any memfs changes locally; push
            # them to the hub (with rebase-retry on contention). Best-effort —
            # never fails the agent run, which already completed.
            if self.settings.memfs_sync_enabled:
                await self._memfs_sync_push(req.agent_id)

            self._record(req, result)
            return result

    # ---- internals -----------------------------------------------------------

    async def _spawn_once(
        self, req: InvokeRequest, timeout: int
    ) -> InvokeResult:
        env = os.environ.copy()
        env["LETTA_LOCAL_BACKEND_DIR"] = str(self.settings.backend_dir)

        # Always create a new conversation (--new). letta-code rejects
        # --conversation when combined with --agent (verified 2026-05-25,
        # letta-code 0.26.1). Conversation continuity is not needed here —
        # the durable memory is memfs (shared across all conversations).
        cmd = [
            self.settings.letta_bin,
            "--backend",
            "local",
            "--new",
            "--agent",
            req.agent_id,
            "-p",
            req.message,
        ]

        log.info(
            "letta_invoke_start",
            agent_id=req.agent_id,
            message_chars=len(req.message),
            timeout=timeout,
        )

        started_at = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd="/tmp",
            )
        except FileNotFoundError as e:
            return InvokeResult(
                status="error",
                agent_response="",
                duration_seconds=0.0,
                letta_exit=-1,
                retried=False,
                stdout_truncated="",
                stderr_truncated=f"letta binary not found: {e}",
                log_path=str(self._log_file_for_today()),
            )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            log.error("letta_invoke_timeout", agent_id=req.agent_id, timeout=timeout)
            proc.kill()
            await proc.wait()
            return InvokeResult(
                status="timeout",
                agent_response="",
                duration_seconds=time.time() - started_at,
                letta_exit=-9,
                retried=False,
                stdout_truncated="",
                stderr_truncated=f"timed out after {timeout}s; process killed",
                log_path=str(self._log_file_for_today()),
            )

        duration = time.time() - started_at
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        log.info(
            "letta_invoke_done",
            agent_id=req.agent_id,
            duration_seconds=round(duration, 2),
            exit=proc.returncode,
            stdout_bytes=len(stdout_b),
        )

        return InvokeResult(
            status="success" if proc.returncode == 0 else "error",
            agent_response=stdout.strip(),
            duration_seconds=round(duration, 2),
            letta_exit=proc.returncode or 0,
            retried=False,
            stdout_truncated=stdout[:_STDOUT_TRUNCATE],
            stderr_truncated=stderr[:_STDERR_TRUNCATE],
            log_path=str(self._log_file_for_today()),
        )

    @staticmethod
    def _looks_like_race_loss(result: InvokeResult) -> bool:
        """The empirically-observed race-loss signature: exit 0, empty stdout."""
        return (
            result.status == "success"
            and result.letta_exit == 0
            and not result.agent_response.strip()
        )

    # ---- memfs Gitea sync (Option C wrapper) --------------------------------

    def _memfs_dir(self, agent_id: str) -> Path:
        return self.settings.backend_dir / "memfs" / agent_id / "memory"

    def _git_env(self) -> dict:
        """Env for git ops. Ensure an identity exists so rebase (during a
        push-retry) can replay commits even without global git config."""
        env = os.environ.copy()
        env.setdefault("GIT_AUTHOR_NAME", "letta-local-runner")
        env.setdefault("GIT_AUTHOR_EMAIL", "runner@localhost")
        env.setdefault("GIT_COMMITTER_NAME", "letta-local-runner")
        env.setdefault("GIT_COMMITTER_EMAIL", "runner@localhost")
        return env

    async def _run_git(self, args: list[str], cwd: Path) -> tuple[int, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(cwd), *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._git_env(),
            )
        except FileNotFoundError as e:
            return (-1, "", f"git not found: {e}")
        try:
            out_b, err_b = await asyncio.wait_for(
                proc.communicate(), timeout=self.settings.git_timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return (-9, "", f"git timed out after {self.settings.git_timeout_seconds}s")
        return (
            proc.returncode or 0,
            out_b.decode("utf-8", errors="replace"),
            err_b.decode("utf-8", errors="replace"),
        )

    async def _has_memfs_remote(self, agent_id: str) -> bool:
        """True only if the agent's memfs is a git repo with the configured
        remote. Agents not yet seeded to Gitea are skipped (no error)."""
        mem = self._memfs_dir(agent_id)
        if not (mem / ".git").exists():
            return False
        rc, out, _ = await self._run_git(["remote"], mem)
        return rc == 0 and self.settings.memfs_remote in out.split()

    async def _pull_rebase(self, agent_id: str, mem: Path) -> bool:
        """pull --rebase --autostash. On failure (e.g. a true same-file
        conflict), abort the rebase so the working copy is left CLEAN for the
        next run rather than stuck mid-rebase. Returns True only on clean pull."""
        remote, branch = self.settings.memfs_remote, self.settings.memfs_branch
        rc, _o, err = await self._run_git(
            ["pull", "--rebase", "--autostash", remote, branch], mem)
        if rc == 0:
            return True
        # Restore a clean state. rebase --abort is a no-op (nonzero) if no
        # rebase is in progress; that's fine — we just want the tree clean.
        await self._run_git(["rebase", "--abort"], mem)
        log.warning("memfs_rebase_failed_aborted", agent_id=agent_id,
                    err=err.strip()[:300])
        return False

    async def _memfs_sync_pull(self, agent_id: str) -> None:
        try:
            if not await self._has_memfs_remote(agent_id):
                return
            if await self._pull_rebase(agent_id, self._memfs_dir(agent_id)):
                log.info("memfs_pull_ok", agent_id=agent_id)
        except Exception as e:  # never let sync break an invocation
            log.warning("memfs_pull_exception", agent_id=agent_id, error=str(e))

    async def _memfs_sync_push(self, agent_id: str) -> None:
        try:
            if not await self._has_memfs_remote(agent_id):
                return
            mem = self._memfs_dir(agent_id)
            remote, branch = self.settings.memfs_remote, self.settings.memfs_branch
            rc, _o, err = await self._run_git(["push", remote, branch], mem)
            if rc == 0:
                log.info("memfs_push_ok", agent_id=agent_id)
                return
            # Most likely a non-fast-forward (the hub advanced from another
            # instance). Rebase onto the remote and retry once.
            log.warning("memfs_push_rejected_retrying", agent_id=agent_id,
                        err=err.strip()[:300])
            if not await self._pull_rebase(agent_id, mem):
                # true conflict: local commit stays unpushed (clean tree), the
                # hub keeps the other instance's edit. No data loss; surfaced
                # for reconciliation. Retried automatically on the next run.
                log.error("memfs_push_retry_pull_failed", agent_id=agent_id)
                return
            rc3, _o3, err3 = await self._run_git(["push", remote, branch], mem)
            if rc3 == 0:
                log.info("memfs_push_ok_after_rebase", agent_id=agent_id)
            else:
                log.error("memfs_push_failed_after_rebase", agent_id=agent_id,
                          err=err3.strip()[:300])
        except Exception as e:
            log.warning("memfs_push_exception", agent_id=agent_id, error=str(e))

    # ---- logging -------------------------------------------------------------

    def _log_file_for_today(self) -> Path:
        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        return self.settings.log_dir / f"{datetime.now().date().isoformat()}.jsonl"

    def _record(self, req: InvokeRequest, result: InvokeResult) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": req.agent_id,
            "conversation_id": req.conversation_id,
            "message_chars": len(req.message),
            "result": asdict(result),
        }
        self._recent.appendleft(
            {k: entry[k] for k in ("timestamp", "agent_id", "conversation_id")}
            | {"status": result.status, "duration_seconds": result.duration_seconds}
        )
        try:
            with self._log_file_for_today().open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            log.warning("log_write_failed", error=str(e))
