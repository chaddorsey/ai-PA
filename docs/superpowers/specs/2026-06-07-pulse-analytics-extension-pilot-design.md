---
date: 2026-06-07
status: design (approved in brainstorm; pending spec review)
topic: pulse-analytics extension-tool pilot
related:
  - docs/followups/2026-06-07-letta-code-0276-capabilities-migration-fit.md
  - docs/followups/2026-06-07-letta-server-tools-migration-stock.md
letta_bug: LET-9147
---

# Pilot: re-home `collect_analytics_snapshot` as a Letta Code extension tool

## Goal

Prove that a local Letta Code **extension tool** can run the analytics-snapshot
logic **deterministically** — pinned Python interpreter + explicit env —
eliminating the LET-9147 non-determinism (server tool runs under a random
interpreter: venv 3.13 / CLT 3.9 / `/root` sandbox). Surface the extension
boundaries/idiosyncrasies that **template the broader server-tool migration**.

## Decisions (from brainstorm)

1. **Scope:** the snapshot tool only.
2. **Interpreter:** a dedicated, reproducible `pa-tools` venv (not the pulse-cli
   pipx venv).
3. **Naming:** distinct `collect_analytics_snapshot_ext`, coexisting with the
   live server tool (zero disruption to the daily cron).

## Architecture / flow

```
agent → collect_analytics_snapshot_ext(date?)
      → extension (Node) execFile( pa-tools venv python, _ext_run.py,
                                    module, func, json-args, env+PYTHONPATH )
      → entry imports existing collect_analytics_snapshot + helpers, prints JSON
      → extension returns JSON to the agent
```

The extension fully controls interpreter, PYTHONPATH, and env on every call →
deterministic, regardless of how letta-code would otherwise pick an interpreter.

## Components

### 1. `pa-tools` venv — canonical migrated-tool interpreter
- Location: `~/.letta/pa-tools-venv/` (runtime, not committed), Python 3.13.
- Tracked `letta/pulse-tools/ext-tools-requirements.txt`: `psycopg[binary]`,
  `pytz` (admin-reports path is stdlib `urllib`).
- Created reproducibly: `python3.13 -m venv` + `pip install -r requirements.txt`.

### 2. Generic entry script — `letta/pulse-tools/_ext_run.py` (template element)
- Contract: `_ext_run.py <module> <func> <json-kwargs>` → imports `<module>`,
  calls `<func>(**kwargs)`, prints result (`str` as-is, else `json.dumps`).
- Reusable for **every** migrated tool — not snapshot-specific.

### 3. Extension — `~/.letta/extensions/pa-tools.ts`
- `activate(letta)`, guarded by `letta.capabilities.tools`, returns a disposer.
- Registers tool `collect_analytics_snapshot_ext`:
  - params: `{ date?: string (YYYY-MM-DD) }`, `additionalProperties:false`.
  - `requiresApproval:false`, `parallelSafe:false` (it writes a DB row).
  - `run(ctx)`: `execFile(VENV_PY, [ENTRY, "collect_analytics_snapshot",
    "collect_analytics_snapshot", JSON.stringify(date?{date}:{})],
    { env: {...loadEnvFile(), PYTHONPATH}, timeout: 300000, maxBuffer })`,
    return `stdout.trim()`; surface stderr on non-zero exit.
  - `PYTHONPATH = /Volumes/main-drive/ai-PA/letta/pulse-tools:/Volumes/main-drive/ai-PA/letta`.
- Structured so adding more migrated tools later is a few lines each.

### 4. Env/secrets file — `~/.letta/pa-tools.env` (gitignored, 600)
- Secrets: `SUPABASE_SERVICE_KEY`, `PA_WEB_POSTGRES_URL`, `GITEA_MEMFS_TOKEN`.
- Config: `SUPABASE_REST_URL=http://localhost:8000`,
  `GITEA_BASE_URL=http://localhost:3030`, `LETTA_BASE_URL=http://localhost:8283`,
  `ADMIN_REPORTS_CREDENTIALS_FILE=/Users/.../.gmail-mcp/admin-reports.credentials.json`,
  `MY_EMAIL=cdorsey@concord.org`.
- The extension parses it and passes as the `execFile` env — keeps secrets out
  of extension code (a template pattern).

## Test plan

- **Phase 1 (no agent / no model):** run `_ext_run.py` via the venv directly for
  a workday (2026-06-05) → confirm real snapshot JSON (Drive 3711, Email 2368,
  DB write success). Proves the pinned path deterministically.
- **Phase 2 (agent-level):** `/reload`; have the pulse agent call
  `collect_analytics_snapshot_ext` **repeatedly (≥5×)** → confirm green every
  run (vs. the server tool's ~50% flakiness). Uses the working model
  (`openai-codex/gpt-5.4`; quota reset). Model switch is independent (below).

## Learning goals (the migration-template payoff — document after)

- Does an extension tool surface to a server-tool-based local agent's toolset,
  and how is it selected vs. the server tool?
- Reliability across N runs (the core thesis).
- Mutating-tool **approval** semantics in the headless runner path.
- `/reload` vs. runner-restart behavior; error propagation; capability guards.
- Best pattern for secret/env provisioning to `execFile`.
- Coexistence with the same-purpose server tool (agent confusion?).

## Model switch (separate, not blocking)

Switching the pulse agent to Kimi (`litellm/kimi-k2p6`) is its own piece: it
needs a **provider extension** (`letta.providers.register`, `openai-completions`,
`baseUrl=http://localhost:4000/v1`, `apiKey="LITELLM_MASTER_KEY"`) + setting the
agent's `model`/`model_settings` (no `letta agents update` CLI — hand-edit the
local agent JSON) + the key in the runner env + restart. litellm serves
`kimi-k2p6` and `gpt-5.4-mini` (confirmed live). Quota reset means the pilot can
run on the existing model now; the provider switch is a clean fast-follow and a
second extension-exploration data point.

## Rollback / safety

- Distinct tool name → zero impact on the live server tool / daily cron.
- Extensions load on start/`/reload`; recover via `letta --no-extensions` or
  `LETTA_DISABLE_EXTENSIONS=1`.
- New files only (venv, entry script, extension, env file); nothing existing
  modified. Server tool untouched.

## Pilot results & findings (2026-06-07) — PASSED

**Phase 1 (deterministic, no agent):** `_ext_run.py` via the pa-tools venv →
Drive 3711, Email 2368, DB write success. Clean (only the expected upstream
"Slack: no silver data for 2026-06-05").

**Phase 2 (agent-level):** **5/5 green** agent invocations on the user's new
`lmstudio/kimi-k2p6` model. Extension loaded with **0 diagnostics errors**.

### Findings → migration template
- **Extension tools surface to a server-tool-based local agent.** The agent
  called `collect_analytics_snapshot_ext` (an extension tool) even though its
  toolset is otherwise server-defined. No registration on the Letta server.
- **Reliability:** green every run. The interpreter is pinned by construction
  (extension always execFiles `~/.letta/pa-tools-venv/bin/python`), so the
  LET-9147 non-determinism cannot occur. This is the core win.
- **`.ts` extensions load natively** — no build step; `~/.letta/extensions/*.ts`
  works directly.
- **Headless/runner path loads extensions on each fresh `letta --backend local`
  invocation** — no `/reload` needed for the cron/runner path (only the
  long-lived TUI needs `/reload`).
- **`requiresApproval:false` ran the mutating tool unattended** through the
  runner — good for cron; for interactive/risky tools, set approval per tool.
- **Secret/env via a 600 env file + execFile `env`** works cleanly and keeps
  secrets out of extension code.
- **Coexistence:** the extension tool and the same-purpose server tool coexist
  fine under distinct names; the agent calls whichever the prompt/description
  points to. (Real migration: remove/rename the server tool so the agent
  defaults to the extension one.)
- **Generic `_ext_run.py` + pinned venv is a clean, reusable template** for any
  Python server tool: declare deps in the venv, set PYTHONPATH, execFile.

### Idiosyncrasies / boundaries to carry into the migration
- Extension hardcodes absolute paths (`VENV_PY`, `ENTRY`, `PYPATH`); for the
  fleet template these should be derived/configurable.
- Tool selection between coexisting server+extension tools is prompt-driven;
  cleanest migration removes the server tool to avoid ambiguity.
- Mutating-tool approval policy is a per-tool decision (cron vs interactive).
- Source-of-truth: the extension lives in `~/.letta/extensions/` (runtime).
  Tracked copy committed to `letta/extensions/pa-tools.ts`; keep them in sync
  (or symlink) so the repo stays canonical.

## Out of scope

- The other ~200 server tools (templated later from this pilot's findings).
- Overriding/removing the server `collect_analytics_snapshot`.
- The model provider switch (separate fast-follow, see above).
- Desktop-app surface evaluation.
