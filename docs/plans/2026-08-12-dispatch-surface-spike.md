# Task 1 Spike — App Server dispatch-surface decision record

**Date:** 2026-08-12
**Outcome:** ✅ **Use `POST /v1/responses`** (OpenAI-compatible route) against a `letta server --backend local --openai-api` App Server. Runs the full tool loop, stateless per call, no lock contention. The WS Appendix A is **not** needed.

## How the spike was run

Throwaway App Server, isolated loopback port, full creds env (mirrors `warm_pool._build_agent_env`):
```
letta server --backend local --listen ws://127.0.0.1:4577 --openai-api
```
Probed `tasks-agent-local` while the live warm resident (PID 61673) still held the same agent.

## Findings (each answers a plan open-question)

1. **`--backend local` is REQUIRED.** Without it, `--openai-api` routes hit the cloud `APIBackend` and fail: `Missing LETTA_API_KEY … getClient() called without credentials`. With it, `/v1/models` lists the 6 local agents as models.

2. **Model id = friendly agent name, NOT the `agent-local-*` id.** `/v1/models` → `Mission Control (local)`, `calendar-agent_copy-local`, `pulse-monitor-agent-local`, **`tasks-agent-local`**, `docs-and-transcripts-agent-local`, `email-agent-local`. Dispatch must map slug → friendly model name (enrichment uses `tasks-agent-local`).

3. **Tool loop RUNS server-side (Q2 ✅).** A `/v1/responses` request asking the tasks agent to call `fetch_source_content` returned `output: [{type:function_call, name:exec_command}, {type:function_call_output}, {type:message, text:"TOOL_OK[*** ANCHOR — EMAIL BODY ***]…"}]`. Tools auto-execute (no approval hang) and real DB/source content came back → **creds/env propagate (Q4 ✅)**.

4. **Stateless per call (Q3 ✅).** Call 1 "reply PONG" → `PONG`. Call 2 "what did I just ask?" → `NO_HISTORY`. Each `/v1/responses` call is a fresh, isolated conversation — per-task context isolation by construction.

5. **No lock contention.** All probes succeeded while resident 61673 held `agent-local-30c45759`. App Server and warm resident coexist on the same agent (matters only during migration).

6. **Response is a single JSON object (NOT streamed NDJSON):**
   ```json
   {"id":"resp_…","object":"response","status":"completed",
    "output":[ …, {"type":"message","content":[{"type":"output_text","text":"…"}]}],
    "usage":{"input_tokens":708,"output_tokens":27,"total_tokens":35167,
             "output_tokens_details":{"reasoning_tokens":0}}}
   ```
   Success = `status=="completed"` with a terminal `message`. `usage.input_tokens` is the per-task context size — **populated here** (unlike stream-json's hardcoded `null`), so it is our observability signal.

7. **Readiness banner:** `Listening on ws://127.0.0.1:4577` (also prints `WebSocket: …/ws` and `OpenAI:  http://…/v1`). NOT "App Server listening".

## Request/response contract for Task 4

- **Endpoint:** `POST {base}/v1/responses`, `Content-Type: application/json`.
- **Body:** `{"model": "<friendly agent name>", "input": "<enrichment prompt>"}` (non-streaming — simpler and returns `usage` directly).
- **Base url:** `http://127.0.0.1:<port>` (ws listen url with `ws://`→`http://`).
- **Parse:** JSON object. `status` (`completed`|`incomplete`), `output[]` (walk for the last `type=="message"` → `content[0].text`), `usage.input_tokens`, top-level `error`. A context-overflow surfaces as `error`/`incomplete` — treat non-`completed` as `status="error"`.
- **Success semantics:** `status="done"` means the run completed; the DB row flips via the agent's own `write_packet_info` call (unchanged).

## Corrections to the implementation plan (apply before Tasks 3–4)

- **Task 3 launch cmd:** add `--backend local` → `letta server --backend local --listen $APP_SERVER_LISTEN --openai-api`.
- **Task 3 `_is_ready_line`:** match `"listening on ws://"` (lowercased), not `"app server" + "listening"`.
- **Task 4:** replace `parse_stream_result(lines)` with `parse_responses_json(obj)` that walks `output[]` for the terminal message and reads `usage.input_tokens`; request is non-streaming; add slug→friendly-model-name mapping.
- **Appendix A (WS):** drop — not needed.

## Context-window observation (for the upstream compaction bug — see canary note)

`letta --backend local agents config --agent <tasks>` reports:
`model: lmstudio/gpt-5.2`, `model_settings.provider_type: openai-codex`, **`llm_config.context_window: 128000`** (not 272000). The `effective` block surfaces **no context window field**. Relevant to the Letta support agent's "unresolved effectiveContextWindow()" theory and the `2026-08-10-letta-code-byok-context-window-128k-default` followup. Does not affect our fix (per-task fresh conversations never approach either limit), but is captured for the upstream issue.
