---
title: letta-code caps every litellm/BYOK model at 128k → reasoning models die with max_tokens_exceeded
date: 2026-08-10
status: immediate fix applied to MC; durable fix (litellm native-models facade) proposed
owner: Chad
related: 2026-08-10-letta-code-0.30.15-fleet-upgrade.md
---

# letta-code defaults proxy/BYOK models to a 128k context window

## Symptom
On MC (kinara), selecting **Deepseek Pro** (`lmstudio/deepseek-v4-pro`) produced one token
then `⚠ error … stop_reason: max_tokens_exceeded`. Same for **kimi-k2p6** and any other
model routed through the litellm proxy. GPT-5.5 worked.

## Root cause (confirmed end-to-end)
Nothing is wrong with the model, the Fireworks key (`fw_HNW…`, correct), or the proxy —
`deepseek-v4-pro` returns HTTP 200 through litellm via the exact path Kinara uses. The break
is a **context-window cap** inside letta-code:

- letta-code's `lmStudioDiscover` fetches models from the "lmstudio" provider (which is really
  the litellm proxy at `http://localhost:4000/v1`). It tries **`{nativeBaseURL}/api/v0/models`**
  (LM Studio native format — includes `max_context_length` / `loaded_context_length` per model)
  FIRST; only if that fails does it fall back to **`/v1/models`**.
- litellm serves `/v1/models` (returns only `{id,object,created,owned_by}` — **no context length**)
  and **404s `/api/v0/models`**. So discovery always falls back and stamps **every** proxy model
  with letta-code's `DEFAULT_CONTEXT_WINDOW_LIMIT = 128000`.
- deepseek-v4-pro's real Fireworks window is **1,048,576 (1M)**, invisible to letta-code.
- MC's conversation is **~264,000 tokens** (1,786 messages — the "/doctor: system prompt is large"
  warning). 264k prompt against a 128k cap ⇒ zero room for output ⇒ the reasoning model emits one
  token and trips `max_tokens_exceeded`. GPT-5.5 only worked because its config sets
  `context_window_limit = 272000` (openai-codex provider), which *just* fits 264k.

Effective window logic in letta-code:
`agentRecord.context_window_limit` (if a number) → else `conversation.context_window_limit`
→ else `DEFAULT_CONTEXT_WINDOW_LIMIT` (128000).

## Immediate fix (applied 2026-08-10, verified)
Edited the MC agent record `~/.letta/lc-local-backend/agents/<base64 mc id>.json`
(backup in scratchpad `mc-agent-record.bak.json`):
- `model` → `lmstudio/deepseek-v4-pro`
- `model_settings.context_window_limit` → **1000000**
- `model_settings.max_output_tokens` / `max_tokens` → 128000 (kept `reasoning.reasoning_effort: medium`)

Then restarted MC (external `kill -9` of the letta child; `agent-supervise` auto-relaunched,
resumed `--conversation default`). Verified: a test turn completed with reasoning + answer
("deepseek-ok"), no `max_tokens_exceeded`. Turn latency ~1m5s (264k prefill on a reasoning model).

## Two caveats this leaves
1. **Slow + costly:** 264k tokens re-read every turn on a reasoning model. The real remedy is to
   **shrink the conversation** (`/compact`, `/doctor`, or a fresh conversation). Under ~100k, the
   128k default is enough for *all* models and none of this per-model hacking is needed.
2. **`/model` switches revert it.** Selecting a model in the TUI re-stamps `context_window_limit`
   from discovery (128k) — re-breaking large-conversation turns. Affects kimi, glm, qwen too (all
   inherit the 128k default). Until the durable fix, switch models via the helper approach below.

## How to switch models (until the durable fix lands)
- **Preferred:** `/compact` the conversation first. Then `/model` works normally — every model fits
  the 128k default, nothing to reapply.
- **If keeping the big conversation:** don't rely on `/model` alone (it resets the window). Use a
  helper that sets model + the right `context_window_limit` + restarts MC. Proposed:
  `~/bin/mc-set-model <litellm-model-name>` → edits the agent record (model + window from a
  model→context map) → `kill -9` the letta child so the supervisor relaunches. (Not yet built.)

## Durable fix — litellm "native models" facade (proposed, not built)
Make discovery see real context lengths so `/model` just works for every proxy model.

- `nativeBaseURL` is derived from the provider base URL (host, `/v1` stripped), so the native
  endpoint must live on the **same host:port** as `/v1`. litellm can't serve `/api/v0/models`,
  so put a thin facade in front of it:
  - A small service (e.g. FastAPI, ~30 lines) on a new port, e.g. **4001**:
    - `GET /api/v0/models` → LM Studio native JSON: `{data:[{id, state:"loaded",
      max_context_length:<real>, loaded_context_length:<real>}, …]}`, context values from a
      model→window map (deepseek-v4-pro/flash = 1048576; fill kimi/glm/qwen/gemini from each
      provider's real limits — Fireworks reports `context_length` in its own `/v1/models`).
    - everything else → reverse-proxy to litellm `:4000`.
  - Repoint the "lmstudio" provider in `~/.letta/lc-local-backend/providers/auth.json` from
    `http://localhost:4000/v1` → `http://localhost:4001/v1`.
  - Result: `lmStudioDiscover` hits the facade's `/api/v0/models`, reads true windows, and every
    `/model` selection (including switches) gets the correct `context_window_limit` automatically.
- Run the facade under launchd alongside litellm. One map to maintain; add a model → add a line.

Alternative considered & rejected: hand-setting `context_window_limit` per agent record (what the
immediate fix does) — works but reverts on `/model` and must be repeated per agent/model.

## Verification commands (for reference)
```bash
# proxy has the model + returns 200 via Kinara's exact key/path:
LMKEY=$(python3 -c "import json;print(json.load(open('$HOME/.letta/lc-local-backend/providers/auth.json'))['providers']['lmstudio']['auth']['key'])")
curl -s http://localhost:4000/v1/chat/completions -H "Authorization: Bearer $LMKEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-v4-pro","messages":[{"role":"user","content":"say ok"}],"max_tokens":128000}'
# litellm 404s the native endpoint (the whole reason for the 128k fallback):
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:4000/api/v0/models -H "Authorization: Bearer $LMKEY"
```
