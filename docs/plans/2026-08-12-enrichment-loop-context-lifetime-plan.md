# Enrichment-loop context-lifetime fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the tasks-agent enrichment subprocess from wedging on unbounded context by moving from one long-lived stream-json conversation to a warm App Server with a fresh conversation per enrichment task.

**Architecture:** The push-receiver supervises a resident `letta server --listen` App Server (loopback) as the warm runtime. Each `/push` opens a fresh conversation/session against the target agent, runs the enrichment tool chain, and discards the conversation — so context never accumulates across tasks. MemFS stays agent-wide. Cutover is behind a receiver flag with the existing stdin warm-pool as fallback until validated.

**Tech Stack:** Python 3.11 (letta-push-receiver, stdlib `urllib`/`http.client` + `pytest`), letta-code 0.30.19 App Server, PostgreSQL (`pa_web.tasks`), launchd.

**Design doc:** `docs/plans/2026-08-12-enrichment-loop-context-lifetime-design.md`

## Global Constraints

- **Runtime floor:** all warm runtimes MUST run verified letta-code **0.30.19** (installed 2026-08-12 03:00). Restart residents/App Server so they pick it up; never rely on a resident that predates the install.
- **Never** `PATCH /v1/agents/{id}` with `tool_ids`/`block_ids` (drops tools/blocks). Not needed here, but relevant if touching agents.
- **Never** `git add -A` in this repo (3390+ untracked). Stage exact paths only.
- **DB access from host:** `PA_WEB_POSTGRES_URL = postgresql://postgres:<POSTGRES_PASSWORD>@127.0.0.1:5433/postgres`; `psql` binary at `/opt/homebrew/opt/libpq/bin/psql`.
- **push-receiver:** launchd `com.ai-pa.letta-push-receiver`, port 8099, `POST /push {agent,source_ref,prompt,priority,source}`, `GET /status`. Restart via `launchctl kickstart -k gui/$(id -u)/com.ai-pa.letta-push-receiver`.
- **tasks agent:** `agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4` (slug `tasks`).
- **Enrichment success signal:** the agent's chain ends in `write_packet_info`, which flips `pa_web.tasks.enrichment_state` → `done`. The scanner (`scheduler-service/scripts/enrichment-scanner.py`) reverts to `pending` on dispatch failure and times out `in_progress` after 20 min (3 retries → `failed`).
- **Env every runtime needs** (from `warm_pool._build_agent_env`): `PATH` incl `~/.local/bin` + `/opt/homebrew/bin`, `HOME`, `LETTA_LOCAL_BACKEND_DIR=~/.letta/lc-local-backend`, `PA_AI_REPO_ROOT=/Volumes/main-drive/ai-PA`, `PA_WEB_POSTGRES_PORT=5433`, `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/Volumes/main-drive/ai-PA/gws-bridge/credentials.json`, `GMAIL_WATCH_SERVICE_URL`, `GITEA_BASE_URL=http://127.0.0.1:3030`, plus `POSTGRES_PASSWORD`, `GITEA_MEMFS_TOKEN`, `SLACK_MCP_XOXP_TOKEN`, `GITHUB_TOKEN`, `GRANOLA_API_KEY`, `GRANOLA_OAUTH_TOKEN` from `.env`.

---

## File Structure

- `letta-push-receiver/src/letta_push_receiver/app_server.py` — **new.** Supervises the resident `letta server --listen` process (spawn, readiness, restart-on-death, shutdown). One responsibility: App Server lifecycle.
- `letta-push-receiver/src/letta_push_receiver/app_server_client.py` — **new.** Per-task dispatch: create a fresh conversation/session for an agent, send the enrichment prompt, stream to completion, return a `DispatchResult`. One responsibility: one enrichment round-trip on an isolated conversation.
- `letta-push-receiver/src/letta_push_receiver/config.py` — **modify.** Add App Server settings (`APP_SERVER_ENABLED`, `APP_SERVER_URL`, port) and the cutover flag.
- `letta-push-receiver/src/letta_push_receiver/server.py` — **modify.** Route `/push` to `app_server_client` when the flag is on; else the existing `warm_pool` path (fallback).
- `letta-push-receiver/tests/test_app_server_client.py` — **new.** Unit tests for request building, completion parsing, failure handling, context sanity-check.
- `letta-push-receiver/tests/test_app_server.py` — **new.** Unit tests for supervision (readiness parse, restart-on-death).
- `scripts/requeue-failed-enrichment-orphans.sql` — **new.** One-time idempotent orphan requeue.
- `docs/plans/2026-08-12-dispatch-surface-spike.md` — **new.** Task 1 decision record.

---

## Task 1: Spike — resolve the App Server dispatch surface

**Rationale:** letta-code ships compiled (no App Server API docs in-tree). The exact per-task dispatch mechanism is the one genuine unknown and gates Tasks 3–4. This spike is time-boxed and produces a decision record + a verified minimal dispatch primitive. **Do NOT run the App Server against the live tasks agent while its warm resident is active** — use a disposable throwaway agent or run with the warm pool stopped, to avoid backend lock contention.

**Files:**
- Create: `docs/plans/2026-08-12-dispatch-surface-spike.md` (decision record)

**Interfaces:**
- Produces (for Tasks 3–4): the confirmed dispatch surface — one of
  `RESPONSES` (OpenAI-compatible `POST /v1/responses`), `CHAT` (`POST /v1/chat/completions`), or `WS` (WebSocket session-per-task) — plus the exact request body, how a **fresh conversation per call** is achieved, whether the **tool loop executes server-side**, and the confirmed launch flags/env.

- [ ] **Step 1: Launch a throwaway App Server on a loopback port**

```bash
cd /Volumes/main-drive/letta-launchpad 2>/dev/null || cd ~
# Use the SAME env block warm_pool builds (see Global Constraints). Loopback => no auth.
LETTA_LOCAL_BACKEND_DIR=~/.letta/lc-local-backend \
PA_AI_REPO_ROOT=/Volumes/main-drive/ai-PA \
/opt/homebrew/bin/letta server --listen ws://127.0.0.1:4577 --openai-api &
echo "app server pid $!"
sleep 3
```
Expected: process stays up; a WS listener on 127.0.0.1:4577 and (with `--openai-api`) HTTP OpenAI-compatible routes on the same bound port. Capture the exact bound URL it prints.

- [ ] **Step 2: Enumerate the OpenAI-compatible surface**

```bash
curl -s http://127.0.0.1:4577/v1/models | python3 -m json.tool | head -40
```
Expected: a model list where **each agent is a model** (per `--openai-api` help). Confirm `agent-local-30c45759...` (or the throwaway agent id) appears as a model id.

- [ ] **Step 3: Probe whether `/v1/responses` (then `/v1/chat/completions`) runs the tool loop and is stateless**

```bash
# Send a prompt that REQUIRES a tool call the enrichment chain uses.
curl -s http://127.0.0.1:4577/v1/responses \
  -H 'Content-Type: application/json' \
  -d '{"model":"<AGENT_ID>","input":"Call fetch_source_content(ref_id=\"__probe__\") and report the tool result verbatim."}' \
  | tee /tmp/probe1.json | python3 -m json.tool | head -60
# Repeat identically a second time:
curl -s http://127.0.0.1:4577/v1/responses -H 'Content-Type: application/json' \
  -d '{"model":"<AGENT_ID>","input":"What did I just ask you?"}' | python3 -m json.tool | head -30
```
Decision criteria — record all three in the decision doc:
1. **Tool loop:** did the response show a real tool invocation/result (not just a chat completion refusing/hallucinating)? YES → the route runs the agent.
2. **Statelessness:** did call 2 ("what did I just ask") show it had **no memory** of call 1? YES → each call is a fresh conversation (what we want).
3. If `/v1/responses` fails or is chat-only, repeat with `/v1/chat/completions` (`{"model":..,"messages":[{"role":"user","content":".."}]}`).

- [ ] **Step 4: If neither HTTP route runs the tool loop statelessly, probe the WS session path**

Inspect the WS protocol for a "create conversation/session" op (the Agent SDK `createSession(agentId)` shape). Minimum viable evidence: a documented or observed WS message that starts a **new** conversation for an agent and returns a conversation id, into which a user message can be sent and streamed to a `result`. Record the message shapes. (If WS is required, note whether a small Node/TS sidecar using the Agent SDK is simpler than a hand-rolled Python WS client.)

- [ ] **Step 5: Confirm env/creds reach tool execution**

In whichever route works, confirm a tool that needs gws (e.g. an email/Drive fetch) succeeds — i.e. the App Server process inherited `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` and postgres creds. If not, note that the App Server must be launched with the full env block (Global Constraints).

- [ ] **Step 6: Tear down and write the decision record**

```bash
kill %1 2>/dev/null   # stop the throwaway server
```
Write `docs/plans/2026-08-12-dispatch-surface-spike.md` recording: chosen surface (`RESPONSES`|`CHAT`|`WS`), exact request body + endpoint, how fresh-conversation-per-call is achieved, tool-loop confirmation, statelessness confirmation, env findings, and the exact `letta server` launch command. **This record is the contract Tasks 3–4 implement against.**

- [ ] **Step 7: Commit**

```bash
git add docs/plans/2026-08-12-dispatch-surface-spike.md
git commit -m "docs: dispatch-surface spike — App Server per-task conversation contract"
```

> **Gate:** Tasks 3–4 below are written for the **expected** outcome (`RESPONSES`, stateless, tool-loop runs — the Python-friendliest path). If the spike selects `WS`, implement Task 4 against **Appendix A** instead; Task 3 is unchanged except the launch flags.

---

## Task 2: One-time orphan-requeue remediation script

Dispatch-independent; safe to land first. Requeues the outage survivors so the (already-healthy) loop enriches them.

**Files:**
- Create: `scripts/requeue-failed-enrichment-orphans.sql`

**Interfaces:**
- Produces: a committed, idempotent SQL script run manually during rollout (Task 6).

- [ ] **Step 1: Write the requeue SQL**

Create `scripts/requeue-failed-enrichment-orphans.sql`:
```sql
-- Requeue tasks whose enrichment FAILED during the 2026-07/08 wedge but are
-- still live (extracted, not rejected/closed). Idempotent: re-running only
-- re-selects rows currently in the failed+extracted state.
-- Run: PGPASSWORD=... /opt/homebrew/opt/libpq/bin/psql -h 127.0.0.1 -p 5433 \
--        -U postgres -d postgres -f scripts/requeue-failed-enrichment-orphans.sql
UPDATE pa_web.tasks
   SET enrichment_state = 'pending',
       enrichment       = (COALESCE(enrichment, '{}'::jsonb) - 'retry_count'),
       updated_at       = NOW()
 WHERE enrichment_state = 'failed'
   AND status           = 'extracted'
   AND closed_at IS NULL
 RETURNING ref_id, source;
```

- [ ] **Step 2: Dry-run the SELECT to confirm the row count**

```bash
PGPASSWORD="$(grep -E '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2- | tr -d '"'\''')" \
/opt/homebrew/opt/libpq/bin/psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -qAX \
  -c "SELECT count(*) FROM pa_web.tasks WHERE enrichment_state='failed' AND status='extracted' AND closed_at IS NULL;"
```
Expected: ~26 (27 minus the canary already cleared). Do NOT run the UPDATE yet — that happens in Task 6 after cutover.

- [ ] **Step 3: Commit**

```bash
git add scripts/requeue-failed-enrichment-orphans.sql
git commit -m "feat(scripts): one-time requeue for wedge-orphaned enrichment tasks"
```

---

## Task 3: App Server supervision module

**Files:**
- Create: `letta-push-receiver/src/letta_push_receiver/app_server.py`
- Create: `letta-push-receiver/tests/test_app_server.py`
- Modify: `letta-push-receiver/src/letta_push_receiver/config.py`

**Interfaces:**
- Consumes: the env-builder pattern from `warm_pool._build_agent_env` (reuse it — do not duplicate the env logic; import/extract a shared `build_runtime_env()`).
- Produces:
  - `class AppServer` with `start() -> None` (spawn + await readiness), `is_alive() -> bool`, `ensure() -> None` (start if dead), `base_url: str`, `shutdown() -> None`.
  - `config.APP_SERVER_URL: str` (e.g. `http://127.0.0.1:4577`), `config.APP_SERVER_LISTEN: str` (e.g. `ws://127.0.0.1:4577`), `config.APP_SERVER_ENABLED: bool`.

- [ ] **Step 1: Write the failing readiness-parse test**

Create `letta-push-receiver/tests/test_app_server.py`:
```python
from letta_push_receiver.app_server import _is_ready_line

def test_ready_line_detects_listening_banner():
    # Task-1 spike confirmed the exact banner the server prints when ready.
    assert _is_ready_line("Listening on ws://127.0.0.1:4577") is True

def test_ready_line_ignores_noise():
    assert _is_ready_line("loading agent config...") is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd letta-push-receiver && poetry run pytest tests/test_app_server.py -v`
Expected: FAIL — `ImportError` / `app_server` not found.

- [ ] **Step 3: Implement `app_server.py` minimal readiness parse + supervision**

Create `letta-push-receiver/src/letta_push_receiver/app_server.py`:
```python
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
```
Also add to `config.py`:
```python
import os
APP_SERVER_LISTEN = os.environ.get("PA_APP_SERVER_LISTEN", "ws://127.0.0.1:4577")
APP_SERVER_URL    = APP_SERVER_LISTEN.replace("ws://", "http://", 1)
APP_SERVER_ENABLED = os.environ.get("PA_APP_SERVER_ENABLED", "0") == "1"
```
And extract the shared env builder in `warm_pool.py`: rename the body of `_build_agent_env` (minus the per-agent bits) into a module-level `build_runtime_env()` and have `_build_agent_env` call it, so `app_server.py` reuses exactly the same env (DRY — avoids the 2026-06-10 gws-creds regression).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd letta-push-receiver && poetry run pytest tests/test_app_server.py -v`
Expected: PASS (both readiness tests). Note: readiness banner string in `_is_ready_line` MUST match what Task 1 Step 1 actually observed — reconcile the substring with the spike's captured output before finalizing.

- [ ] **Step 5: Commit**

```bash
git add letta-push-receiver/src/letta_push_receiver/app_server.py \
        letta-push-receiver/src/letta_push_receiver/config.py \
        letta-push-receiver/src/letta_push_receiver/warm_pool.py \
        letta-push-receiver/tests/test_app_server.py
git commit -m "feat(push-receiver): App Server supervision module + shared runtime env"
```

---

## Task 4: Per-task dispatch client (primary path: OpenAI-compatible `/v1/responses`)

> **Task 1 spike RESOLVED this: use `POST /v1/responses` (non-streaming).** Confirmed the tool loop runs server-side, calls are stateless, and the response is a single JSON object. **Appendix A (WS) is not needed** — ignore it.

**Files:**
- Create: `letta-push-receiver/src/letta_push_receiver/app_server_client.py`
- Create: `letta-push-receiver/tests/test_app_server_client.py`

**Interfaces:**
- Consumes: `AppServer.base_url` (Task 3); the `/v1/responses` contract from `docs/plans/2026-08-12-dispatch-surface-spike.md`.
- Produces: `class AppServerClient` with `enrich(slug: str, prompt: str) -> DispatchResult` (slug is the receiver agent slug, e.g. `"tasks"`, mapped to the friendly model name), where `DispatchResult` is a dataclass `{status: str ("done"|"error"), context_tokens: int|None, detail: str}`. `status="done"` means the run completed (`status=="completed"`); the DB row flip is owned by the agent's own `write_packet_info` call, not this client. Also exports `parse_responses_json(obj: dict) -> DispatchResult` and `SLUG_TO_MODEL: dict`.

- [ ] **Step 1: Write the failing completion-parse test**

Create `letta-push-receiver/tests/test_app_server_client.py`:
```python
from letta_push_receiver.app_server_client import parse_responses_json

def test_parse_completed_extracts_text_and_context_tokens():
    # Shape confirmed by the Task-1 spike: single /v1/responses JSON object.
    obj = {
        "status": "completed",
        "output": [
            {"type": "function_call", "name": "exec_command"},
            {"type": "message", "content": [{"type": "output_text", "text": "ENRICHED: ref_id=x"}]},
        ],
        "usage": {"input_tokens": 35167},
    }
    r = parse_responses_json(obj)
    assert r.status == "done"
    assert r.context_tokens == 35167
    assert "ENRICHED" in r.detail

def test_parse_non_completed_is_error():
    obj = {"status": "incomplete", "output": [], "error": {"message": "context_window exceeded"},
           "usage": {"input_tokens": 271000}}
    r = parse_responses_json(obj)
    assert r.status == "error"
    assert "context_window" in r.detail
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd letta-push-receiver && poetry run pytest tests/test_app_server_client.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `app_server_client.py`**

Create `letta-push-receiver/src/letta_push_receiver/app_server_client.py`:
```python
"""Per-task enrichment dispatch against the warm App Server.

Each POST /v1/responses is a FRESH, isolated conversation (stateless —
confirmed in the Task 1 spike), so context never accumulates across tasks.
Non-streaming: the server returns one JSON object with output[] + usage.
"""
from __future__ import annotations
import json, urllib.request, urllib.error
from dataclasses import dataclass

# Task-1 spike: /v1/models exposes agents by FRIENDLY NAME, not agent-local-* id.
SLUG_TO_MODEL = {
    "tasks": "tasks-agent-local",
    "docs": "docs-and-transcripts-agent-local",
    "pulse": "pulse-monitor-agent-local",
    "email": "email-agent-local",
    "calendar": "calendar-agent_copy-local",
    "mc": "Mission Control (local)",
}

@dataclass
class DispatchResult:
    status: str          # "done" | "error"
    context_tokens: int | None
    detail: str

def parse_responses_json(obj: dict) -> "DispatchResult":
    usage = obj.get("usage") or {}
    ctx = usage.get("input_tokens")
    if obj.get("status") != "completed":
        err = obj.get("error") or {}
        detail = err.get("message") if isinstance(err, dict) else str(err)
        return DispatchResult("error", ctx, detail or f"status={obj.get('status')}")
    text = ""
    for item in obj.get("output", []):
        if item.get("type") == "message":
            content = item.get("content") or []
            if content:
                text = content[0].get("text", "")
    return DispatchResult("done", ctx, text)

class AppServerClient:
    def __init__(self, base_url: str, log_fn):
        self.base_url = base_url.rstrip("/")
        self.log = log_fn

    def enrich(self, slug: str, prompt: str) -> DispatchResult:
        model = SLUG_TO_MODEL.get(slug, slug)
        body = json.dumps({"model": model, "input": prompt}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/v1/responses", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                obj = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return DispatchResult("error", None, f"HTTP {e.code}: {e.read()[:200].decode('utf-8','replace')}")
        except Exception as e:
            return DispatchResult("error", None, f"unreachable: {e}")
        result = parse_responses_json(obj)
        # Observability sanity-check: a single fresh-conversation task should be
        # nowhere near the window. Flag pathological single-task growth.
        if result.context_tokens and result.context_tokens > 200_000:
            self.log(f"WARN pathological single-task context={result.context_tokens} slug={slug}")
        return result
```
> **Note:** `enrich(slug, prompt)` now takes the receiver **slug** (maps to the friendly model name), not the raw `agent_id` — update Task 5's call site accordingly. Timeout is 300s (enrichment tool chains can be slow).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd letta-push-receiver && poetry run pytest tests/test_app_server_client.py -v`
Expected: PASS (both parse tests).

- [ ] **Step 5: Commit**

```bash
git add letta-push-receiver/src/letta_push_receiver/app_server_client.py \
        letta-push-receiver/tests/test_app_server_client.py
git commit -m "feat(push-receiver): per-task App Server dispatch client (fresh conversation per enrichment)"
```

---

## Task 5: Cut `/push` over behind a flag (App Server path, warm-pool fallback)

**Files:**
- Modify: `letta-push-receiver/src/letta_push_receiver/server.py`

**Interfaces:**
- Consumes: `config.APP_SERVER_ENABLED`, `AppServer` (Task 3), `AppServerClient.enrich` (Task 4).
- Produces: `/push` dispatches to the App Server when enabled; otherwise the existing `warm_pool.dispatch` (unchanged fallback).

- [ ] **Step 1: Wire the App Server into the receiver startup and `/push` handler**

In `server.py`, where the `WarmPool` is constructed, add (guarded by the flag):
```python
from .config import APP_SERVER_ENABLED
from .app_server import AppServer
from .app_server_client import AppServerClient

app_server = None
app_client = None
if APP_SERVER_ENABLED:
    app_server = AppServer(log)
    app_server.ensure()
    app_client = AppServerClient(app_server.base_url, log)
```
In the `/push` handler, resolve the agent id (existing `source`/`agent` routing → `spec.agent_id`), then branch:
```python
if APP_SERVER_ENABLED and app_client is not None:
    app_server.ensure()                       # restart-on-death
    result = app_client.enrich(slug, prompt)  # slug -> friendly model name (SLUG_TO_MODEL)
    return {"status": "queued", "agent": slug, "dispatch": "app-server",
            "result_status": result.status, "context_tokens": result.context_tokens}
# else: existing warm_pool.dispatch(slug, prompt) path unchanged
```
Keep the fire-and-forget contract: `enrich()` is synchronous but the scanner already expects a 202-style ack; run it on the request thread (the scanner dispatches one row per 30s, so serialization is fine) OR hand to a worker thread and return immediately. Match the existing handler's async shape — if the current handler returns before completion, submit `enrich` to a `ThreadPoolExecutor(max_workers=1)` per agent and return the queued ack.

- [ ] **Step 2: Add `shutdown` wiring**

Where `warm_pool.shutdown()` is called on receiver stop, also call `app_server.shutdown()` if present.

- [ ] **Step 3: Manual smoke test with the flag ON (throwaway)**

```bash
# In a scratch shell, run the receiver with the flag and hit /push for one requeued task.
PA_APP_SERVER_ENABLED=1 poetry run python -m letta_push_receiver &   # scratch instance on an alt port if needed
curl -s -XPOST http://127.0.0.1:8099/push -H 'Content-Type: application/json' \
  -d '{"agent":"tasks","source_ref":"<REF>","prompt":"<enrich prompt>","priority":"normal"}'
```
Expected: ack with `"dispatch":"app-server"`; the target row reaches `enrichment_state='done'`; the App Server log shows a **new conversation id per push**.

- [ ] **Step 4: Commit**

```bash
git add letta-push-receiver/src/letta_push_receiver/server.py
git commit -m "feat(push-receiver): route /push to App Server behind PA_APP_SERVER_ENABLED flag"
```

---

## Task 6: E2E validation, cutover, remediation, and stdin-path removal

**Files:**
- Modify: launchd plist env for `com.ai-pa.letta-push-receiver` (add `PA_APP_SERVER_ENABLED=1`) — **note:** plists are NOT git-tracked (per project ops rules); edit in place and document the change in the spike/decision doc.
- Modify (final): `letta-push-receiver/src/letta_push_receiver/warm_pool.py` + `server.py` — remove the stdin path after steady-state.

- [ ] **Step 1: E2E — flat per-task context across several tasks**

Requeue 3–4 orphans; dispatch them through the App Server path; assert **each** reaches `done` AND each run's `usage_statistics.context_tokens` starts near baseline (~30–60k), i.e. **context does not grow task-over-task** (the core proof the wedge is gone). Capture the App Server log showing distinct conversation ids per task.

- [ ] **Step 2: Enable the flag in launchd and restart the receiver**

```bash
# add <key>PA_APP_SERVER_ENABLED</key><string>1</string> to the plist EnvironmentVariables
launchctl kickstart -k gui/$(id -u)/com.ai-pa.letta-push-receiver
curl -s http://127.0.0.1:8099/status | python3 -m json.tool | head
```
Expected: receiver healthy; App Server child running 0.30.19.

- [ ] **Step 3: Run the one-time orphan requeue (Task 2 script)**

```bash
PGPASSWORD="$(grep -E '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2- | tr -d '"'\''')" \
/opt/homebrew/opt/libpq/bin/psql -h 127.0.0.1 -p 5433 -U postgres -d postgres \
  -f scripts/requeue-failed-enrichment-orphans.sql
```
Expected: ~26 rows returned; watch them drain to `done` over subsequent scanner cycles (one per 30s). Verify: `SELECT enrichment_state, count(*) FROM pa_web.tasks WHERE created_at > now()-interval '60 days' GROUP BY 1;` — `failed` count drops toward 0.

- [ ] **Step 4: Soak, then remove the stdin warm-pool path**

After a clean multi-day steady state (no `failed` enrichments, App Server context flat), delete the stdin `dispatch`/`_spawn`/`_read_stdout` machinery from `warm_pool.py` and the fallback branch from `server.py`, keeping only `build_runtime_env()` (now shared). Update `warm_pool.py`'s module docstring.
```bash
git add letta-push-receiver/src/letta_push_receiver/warm_pool.py \
        letta-push-receiver/src/letta_push_receiver/server.py
git commit -m "refactor(push-receiver): remove stdin warm-pool path — App Server is the sole runtime"
```

- [ ] **Step 5: File the upstream compaction bug**

Post the payload assembled in the design doc's "Upstream follow-up" section to the Letta support agent / GitHub so the missing meaningful-progress guard is tracked.

---

## Appendix A: WS session-per-task dispatch (OBSOLETE — Task 1 chose `/v1/responses`)

> **Not needed.** The Task 1 spike confirmed `POST /v1/responses` runs the tool loop statelessly against local agents. This appendix is retained only as a record of the contingency. Do not implement it.

If the spike had shown the OpenAI-compatible routes do NOT run the tool loop statelessly, implement `AppServerClient.enrich()` over the WebSocket App Server instead, preserving the same signature and `DispatchResult`:
1. Connect once (persistent WS) to `APP_SERVER_LISTEN`; loopback needs no auth.
2. Per task: send the "create conversation/session" op for `agent_id` (shape captured in Task 1 Step 4), receive the new `conversation_id`.
3. Send the enrichment prompt as a user message into that conversation; read stream-json events to the terminal `result` (reuse `parse_stream_result` verbatim — it is transport-agnostic).
4. Close/abandon the conversation.
If a hand-rolled Python WS client proves heavy, run a minimal Node sidecar using the Agent SDK `createSession(agentId)` and have the Python receiver POST to the sidecar — decide in Task 1 Step 4.

---

## Self-Review

- **Spec coverage:** App Server + per-task conversation (Tasks 3–5); observability sanity-check (Task 4 Step 3); orphan requeue (Tasks 2, 6.3); runtime-0.30.19 requirement (Global Constraints, Task 6.2); migration behind flag with fallback (Task 5); stdin removal (Task 6.4); upstream bug (Task 6.5); dispatch-surface unknown (Task 1 spike). Covered.
- **Placeholders:** none — the one genuine unknown (dispatch surface) is a scoped spike whose output is a written contract; primary-path code is concrete OpenAI-compatible, with a real WS appendix.
- **Type consistency:** `DispatchResult{status,context_tokens,detail}`, `AppServerClient.enrich(agent_id, prompt)`, `AppServer.{ensure,base_url,shutdown,is_alive}`, `build_runtime_env()`, `parse_stream_result(lines)` — used consistently across Tasks 3–6 and Appendix A.
- **Risk flagged inline:** readiness banner substring (Task 3 Step 4) and request framing SSE-vs-NDJSON (Task 4 Step 3) must reconcile with the Task 1 spike before finalizing.
