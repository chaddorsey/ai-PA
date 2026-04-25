---
date: 2026-04-24 (updated 2026-04-25 with registry refresh + Q3 confirmation)
status: ROOT CAUSE CONFIRMED — fix path locked
issue: https://github.com/letta-ai/letta/issues/3205
letta-server: 0.16.7
letta-code: 0.24.2
supersedes:
  - ./2026-04-24-letta-issue-3205-diagnosis.md
  - ./2026-04-24-letta-issue-3205-wire-capture.md
related:
  - ./2026-04-24-letta-issue-3205-wire-capture.md (debugging method + milestone approach)
patch-draft: ../letta-memfs-patches/patches/letta_code_self_hosted_handle_fix.md
sql-stopgap: ../scripts/letta-handle-stopgap/
---

## VALIDATED 2026-04-25 — Path C works end-to-end

Patch built and applied to project-local letta-code at `~/code/letta-code-memfs/node_modules/@letta-ai/letta-code/letta.js`. Both `createAgent` sites carry the patch (8 `[PATCH-3205]` marker comments verified). Binary parses, runs, reports `0.24.2 (Letta Code)`.

End-to-end Task validation against a fresh pilot agent with `llm_config.handle = "litellm/gpt-4.1-mini"` (matches our production agent shape):

```
$ LETTA_CODE_BIN=<wrapper> letta --agent <pilot> -p "Use Task subagent_type=general-purpose to write 'PATH-C-WORKS-V2' to /tmp/path-c-test.txt"

→ subagent_status=success
→ subagent agent-id created
→ /tmp/path-c-test.txt written with correct content
→ no HandleNotFoundError in server logs
→ no PATCH-3205 errors
→ duration: 20s end-to-end
```

The subagent task log shows the proper success state (vs prior runs that all showed `subagent_status=error`):

```
[Task started: Write and read back test file for PATH-C-WORKS-V2]
[subagent_type: general-purpose]
subagent_status=success agent_id=agent-56805376-...
1. Summary: I wrote the string "PATH-C-WORKS-V2" to the file...
[Task completed]
```

This proves:
- The patch correctly inherits parent's `llm_config` and `embedding_config`
- POST /v1/agents/ succeeds because `llm_config` is non-None → bypasses handle resolution
- The subagent's spawn-chain inherits `LETTA_CODE_BIN` and uses our patched copy
- `compaction_settings.model = parent.handle` works (no warnings observed)
- Compaction graceful-fallback held even though we're on a self-hosted agent with `letta/auto`-resolution disabled — no errors fired

**Path C is production-ready** pending: (a) tests of TodoWrite, EnterPlanMode, AskUserQuestion (the other `INTERACTIVE_APPROVAL_TOOLS`); (b) regression test that pa-web-ui's normal flow is unaffected; (c) sustained workload (5+ chained Task calls).

## Update 2026-04-25 — Two material refinements

1. **Registry was stale, not empty.** Initial diagnosis noted "must be one of []" suggesting empty registry. On inspection: 123 active `provider_models` rows present, but the BYOK `openai-proxy` provider's last sync was 2026-03-14 — over a month stale. Triggered the sanctioned `PATCH /v1/providers/{id}/refresh` endpoint; registry went 23→39 active openai-proxy rows, picking up `kimi-k2p6`, `kinara`, `glm-5p1`, all the gpt-5.4 family, claude-* mappings, fireworks models, etc. Zero unintended deletions. **This step alone does NOT fix Task** because our agents use `litellm/X` handles (custom convention from initial wiring), and those don't exist in the registry under any provider — LiteLLM's `/v1/models` returns bare model names like `kimi-k2p6` which Letta prefixes with the provider's name (`openai-proxy`), never `litellm/`.

2. **Q3 answered: server's POST handler does NOT validate the inner handle of a copied `llm_config` object.** The guard at `server.py:540` (`if request.llm_config is None:`) short-circuits the entire handle-resolution block when a full `llm_config` object is sent. Inner `handle` field is stored verbatim. Path C (letta-code patch sending `llm_config: <object>` instead of `model: <handle>`) is therefore the clean structural fix and does NOT require also rewriting handles inside the object.

## Final Path Decision

**Path C is the chosen fix.** Three sub-paths exist, in order:

- **Path A (SQL stopgap)** — INSERT `litellm/X` mirror rows in `provider_models`. Drafted at `scripts/letta-handle-stopgap/`. Not executed. Operationally fragile (re-application needed after each provider refresh).
- **Path B (rename agent handles)** — Update 20 agents + pa-web-ui MC_MODEL_PRESETS + LettaBot config to use canonical `openai-proxy/X` handles. Wide blast radius. Rejected.
- **Path C (letta-code patch)** — Patch project-local letta-code to send `llm_config: parentAgent.llm_config` verbatim on subagent POST. Vendored alongside memfs patches. Drafted at `letta-memfs-patches/patches/letta_code_self_hosted_handle_fix.md`. Not applied.

Path A available as interim if Task needs to work before Path C is built.

---


# #3205 Root Cause — Final Diagnosis

## Summary (one paragraph)

Our self-hosted Letta's `POST /v1/agents/` endpoint validates the `model` field against a handle registry that is effectively **empty** for our configuration — it resolves zero handles to the LLM config lookup path. This causes every letta-code subagent spawn (which always goes through `POST /v1/agents/`) to fail with `HandleNotFoundError: NOT_FOUND: Handle <X> not found, must be one of []`. The subagent process exits silently, the parent's stdout parser receives nothing, letta-code reports `Failed to parse subagent output: Unexpected end of JSON input`. The LLM observes the error, retries, eventually gives up. The entire `Task tool is broken` symptom traces to this single handle-registry mismatch.

The bug is **not** in the Letta server's approval-state handling (wire capture proved the server processes approval responses correctly). The bug is **not** in `letta-code`'s `--new-agent -p` headless mode per se (it's headless-mode-specific only because the failure surface is quieter in headless than in TUI — TUI would show the error).

#3205's originally-reported symptom (`Cannot process approval response: No tool call is currently awaiting approval`) may be a separate real bug that was fixed upstream (per Letta team's note on commit `c22eab7`, Mar 25), but it's not what's blocking us.

## The Evidence Chain

### Step 1: Subagent POST is the failing call

Direct instrumentation via `LETTA_DEBUG_TIMINGS=1` showed:
```
[timing] MILESTONE CLI_START at +0ms
[timing] MILESTONE SETTINGS_LOADED at +1ms
[timing] MILESTONE CREDENTIALS_VALIDATED at +40ms
[timing] MILESTONE HEADLESS_MODE_START at +40ms
[timing] MILESTONE TOOLS_LOADED at +40ms
[timing] MILESTONE HEADLESS_CLIENT_READY at +0ms
[timing] GET /v1/models/ -> 179ms (status: 200)
[timing] POST /v1/agents/ -> 5ms (status: 404)
```

No milestone after `HEADLESS_CLIENT_READY` — the process exits after `POST /v1/agents/` returns 404 (5ms), silently, with no error surfaced to stdout.

### Step 2: Server-side traceback identifies the handle

Server log captured the exact error:
```
File "/app/letta/server/server.py", line 1513, in get_llm_config_from_handle_async
File "/app/letta/services/provider_manager.py", line 988, in get_llm_config_from_handle
    raise NoResultFound(f"Auto mode not enabled for handle='{handle}'")
letta.errors.HandleNotFoundError: NOT_FOUND: Handle letta/auto not found, must be one of []
```

Initial observation: `letta/auto` (Cloud-only auto-routing handle) was being submitted.

### Step 3: Reproduce via real parent agent — different handle, same failure

Running Task through a real parent letta-code session (parent agent uses `litellm/gpt-4.1-mini` via MC's pattern), the subagent tried to INHERIT the parent's model handle:
```
letta.errors.HandleNotFoundError: NOT_FOUND: Handle litellm/gpt-4.1-mini not found, must be one of []
```

So it's not specifically `letta/auto` — the **POST validator rejects multiple handles that the rest of the server accepts**.

### Step 4: Empirical handle-acceptance probe

Three POST /v1/agents/ tries with different model handles:
| Handle | HTTP |
|---|---|
| `openai-proxy/gpt-4.1-mini/rover` | 200 ✅ |
| `litellm/gpt-4.1-mini` | 404 ❌ |
| `letta/auto` | 404 ❌ |

But **PATCH** /v1/agents/{id} with `llm_config.handle=litellm/gpt-4.1-mini` succeeds. So POST's handle validator is stricter than PATCH's.

The server's `provider_manager.get_llm_config_from_handle` at line 988 rejects based on "Auto mode not enabled" even though the handle in question isn't an auto handle (`litellm/gpt-4.1-mini` is a literal handle, not `letta/auto`). The `must be one of []` empty list suggests the validator is looking in a context-specific handle table that's empty on our server.

## Why This Wasn't Caught Earlier

Three layers of confusion:

1. **The forum thread's framing pointed at the server approval flow.** That framing pattern-matched to #3205's original symptom (which is a different bug). Wire capture showed the approval flow is fine.
2. **The subagent silent-exit had no visible failure mode.** Without `LETTA_DEBUG_TIMINGS=1`, the subagent process exits after a failed POST with only the `secrets` warning on stderr. No indication of which step failed. With the env var, the truth became immediately obvious.
3. **`letta-code` never emits the underlying 404 to the user.** `executeSubagent`'s try/catch catches the thrown error, returns `{success:false, error: getErrorMessage2(error)}`, but in headless stream-json mode this rolls up as an empty `result` event rather than an explicit error.

## Fix Options (ordered by feasibility)

### Option 1: Register `letta/auto` and similar handles on self-hosted Letta

If `provider_manager` has a configuration surface for registering auto-handle aliases, we could map `letta/auto → openai-proxy/gpt-4.1-mini/rover` (or a similar real handle). Pros: no letta-code patch. Cons: unclear how to activate; would need to pin the aliased model (which may not match the parent's model tier preference).

**Investigation needed**: what exactly "Auto mode" is on the server side, whether there's a server config or Postgres table that enables it, and whether we can populate it ourselves.

### Option 2: Patch letta-code to use `--model` override with a known-good handle

In `executeSubagent` (or the preceding `resolveSubagentModel`), default to a handle we know works on our server when the auto-routing handle fails. Simplest patch: when `parentModelHandle` exists and is valid on the server, use it. When it isn't (as in our test case), fall back to `openai-proxy/gpt-4.1-mini/rover` or equivalent.

This is a small client-side patch (~10-20 lines). Vendored alongside the memfs patches.

### Option 3: Patch letta-code to not send `compaction_settings.model`

One line: replace `compaction_settings: {model: DEFAULT_SUMMARIZATION_MODEL}` with `compaction_settings: undefined`. Tested via REST: creating an agent without `compaction_settings` works fine. However, this alone doesn't fix the 404 because the primary `model` field (not `compaction_settings.model`) is what the server rejects. So this patch helps but isn't sufficient.

### Option 4: Server-side patch — make POST /v1/agents/ more permissive

Modify the handler to accept any handle that PATCH accepts (or to fall back to a default model if the handle is unresolvable). This is a server-side change analogous to the external-memfs server patches. More invasive than letta-code patch.

### Option 5: Add a LiteLLM-level alias

Map `letta/auto` → some real model in our LiteLLM config (`litellm/config.yaml`). Would require Letta to route auto handles through LiteLLM, which it doesn't.

## Recommendation

**Combine Option 1 investigation with Option 2 as a backstop:**

1. **Short-term**: Investigate Option 1 — determine whether self-hosted Letta has a mechanism to register `letta/auto` + the `litellm/*` handles to pass POST validation. If yes: add that to our Letta setup docs and move on.
2. **If Option 1 doesn't have a clean path**: Apply Option 2 as a vendored letta-code patch. The patch does three things:
   - In `resolveSubagentModel`, prefer `parentModelHandle` over `letta/auto`/`letta/auto-fast` when self-hosted (detectable via `LETTA_BASE_URL !== https://api.letta.com`)
   - Pre-validate the chosen handle via `GET /v1/models/?handle=X` before submitting POST; if invalid, fall back to a known-good handle
   - Strip `compaction_settings` from the POST body if `compaction_settings.model` would be `letta/auto` and auto-mode isn't configured
3. **Ship it** alongside the existing memfs patches in the same vendored toolchain.

## What This Means for Our Migration Plan

Phase -1 needs another revision. The previous version correctly identified `--new-agent -p` silent failure as the blocker, but mis-characterized the root cause as a headless-mode bug. It's actually a **handle-registry mismatch between letta-code and self-hosted Letta**.

The scope of Path B expands slightly: the patch isn't just replacing `--new-agent`, it's also ensuring the subagent uses a handle the server will accept. Still small (~20-30 lines of JS to reach in), still client-side, still vendor-able.

## Questions for the Letta Agent

1. **"Confirmed: our Task tool failure is `POST /v1/agents/` returning 404 because the server's `provider_manager.get_llm_config_from_handle` at `services/provider_manager.py:988` raises `NoResultFound(f'Auto mode not enabled for handle=<X>')` for both `letta/auto` AND `litellm/*` handles, with `must be one of []` (empty list). PATCH with the same handle works. What enables/populates the handle registry that POST validates against? Is there a server-side config, env var, or Postgres table we need to populate?"**

2. **"Is 'Auto mode' the specific feature that registers `letta/auto` mappings on self-hosted? If we can't enable it, what's the sanctioned workaround — pre-create agents via API and attach letta-code, or patch letta-code to use an explicit real handle?"**

3. **"Are we the first to hit this with self-hosted? Given letta-code defaults to `letta/auto` for compaction_settings regardless of deployment type, every self-hosted user running Task subagents must hit this. Unless there's a setup step we're missing."**

4. **"If Option 2 (letta-code patch) is the practical path, what's the safest heuristic for picking a fallback handle? The parent's handle (if valid), then a configured default, then a hardcoded known-cloud handle?"**

5. **"The thing the Letta team could fix upstream most cleanly is letta-code falling back to a PATCH after a POST 404, since PATCH accepts handles POST rejects. Would that be a reasonable upstream PR?"**

## Files Inspected

- `/app/letta/services/provider_manager.py:988` (server — the raiser)
- `/app/letta/server/server.py:1513` (server — the caller)
- `/app/letta/server/rest_api/routers/v1/agents.py:626` (server — endpoint entry)
- `/opt/homebrew/lib/node_modules/@letta-ai/letta-code/letta.js` multiple locations:
  - `72247` (`getPrimaryAgentModelHandle`)
  - `72288` (`resolveSubagentModel`)
  - `34077` (`DEFAULT_SUMMARIZATION_MODEL = "letta/auto"`)
  - `38430` (`compaction_settings: {model: DEFAULT_SUMMARIZATION_MODEL}`)
  - `72554-72570` (`buildSubagentArgs`)
  - `72610-72800` (`executeSubagent`)
  - `167045+` (`main()` + milestones)
