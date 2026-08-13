---
title: "Fleet fan-out orchestrator — parallel derivation → Kinara (sketch)"
type: sketch
status: draft — for another agent to flesh out
date: 2026-08-13
related:
  - docs/research/2026-08-13-parallel-derivation-and-letta-teams-findings.md   # the "why"
  - docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md      # continuity-core (Unit 4)
---

# Fleet fan-out orchestrator (sketch)

Lightweight bullets only. The decision rationale + benchmark live in the sibling findings doc.

## One-liner
- Fan out one derivation task to N specialized local agents **in parallel**, collect results, synthesize back into a single Kinara/MC turn. Aligned with the sole-owner App Server; no SDK, no letta-teams runtime.

## Why this shape (proven, not assumed)
- Benchmark 2026-08-13: cross-agent concurrent wall ≈ slowest single agent (near-ideal parallelism); models are **cloud-served** via litellm (Fireworks + OpenAI, per-agent keys) → no local-GPU bottleneck. See findings doc.
- `/v1/responses` is stateless (fresh conversation per call) → trivially parallel, no session/`event_seq` bookkeeping.

## Where it lives (proposed)
- `clients/fleet-orchestrator/` (TS) OR a small module under `letta-push-receiver/` if it should share the enrichment client directly. Decide based on whether it needs to be a standalone CLI vs a library the receiver/clients import.
- Ship a thin CLI (`fleet-derive`) + a library entry so both a human and Kinara-via-tool can call it.

## Reuse (do NOT re-derive)
- `letta-push-receiver/.../app_server_client.py::AppServerClient.enrich(slug, prompt)` — the `/v1/responses` call (`{"model": <friendly name>, "input": prompt}`, 300s timeout). Stateless fresh conv.
- `letta-push-receiver/.../config.py::DEFAULT_AGENTS` + `app_server_client.SLUG_TO_MODEL` — slug → friendly model name (tasks/email/pulse/docs/calendar/mc).
- `clients/letta-continuity-core/` — to inject the synthesized result into Kinara's **live** conversation (if the answer must render on the surfaces) via `ContinuityCore.send()`.
- `PA_APP_SERVER_URL` / base_url = the sole-owner App Server (`:4577`).

## Core flow
- Input: `{ prompt, agents?: slug[], synthesizer?: slug="mc" }`.
- Step 1 — fan out: `Promise.all` (bounded concurrency) of `enrich(slug, prompt)` over the selected agents. Each is independent + stateless.
- Step 2 — collect: gather `{slug, result, latency, status}`; keep partials on failure.
- Step 3 — synthesize: build one prompt = original ask + labeled per-agent findings; send to the synthesizer (Kinara). Two delivery modes (pick per caller):
  - **stateless**: `enrich("mc", synthesisPrompt)` → return the string (for scripts/tools).
  - **continuity**: `ContinuityCore.send(synthesisPrompt)` → lands in the live Kinara conversation so it renders on terminal/web (needs the pointer file from Unit 8).

## Concurrency / safety
- Bounded concurrency (e.g. cap 5–6 = fleet size; make it a param). Ceiling is per-provider/per-key rate limits, not local hardware.
- Per-call timeout (reuse enrich's 300s or tighten). No unbounded waits.
- Partial failure = first-class: one agent erroring/timing out must NOT sink the batch; pass its status through to synthesis ("agent X: no result").
- MC/Kinara is the **synthesizer/orchestrator**, not a fan-out load target (don't hammer it in the parallel step).
- Benign by construction, but derivation prompts may invoke tools → cost/latency higher than the benchmark's no-tool calls; surface per-agent cost/latency.

## Design refs (borrow UX, not runtime)
- `letta-teams` (`.skills/letta-teams`): `dispatch A=.. B=..`, `broadcast`, `dashboard`, self-report `todo/work/progress`. Good ergonomics template. **Do not** use its daemon — it's bound to Docker Letta `:8283` (see findings). Reimplement the dispatch surface against `/v1/responses`.

## Tests
- Unit: fan-out returns one result per agent; a thrown/timed-out agent yields a status entry, not a batch failure; synthesis prompt includes all labeled findings.
- Integration (opt-in, live `:4577`, benign no-tool prompt, utility agents only): 3-agent fan-out completes with concurrent wall ≈ slowest agent.

## Open questions (for the fleshing-out agent)
- Delivery: should synthesis default to stateless (`enrich("mc")`) or land in Kinara's live conversation (continuity)? Depends on whether R3/continuity cutover (Unit 8) has happened.
- Does Kinara need the **raw** per-agent results too (transcript), or only the synthesis? (Affects context size + cost.)
- Routing intelligence: static agent list vs. a relevance step that picks which agents to ask (foreshadows R12–R15 relevance-routing — keep out of scope for v1).
- Dedup/merge of overlapping findings across agents — v1 can punt to the synthesizer LLM.
- Streaming: `/v1/responses` is batch; if live progress is wanted, mirror to a surface via continuity-core.

## Explicitly NOT in scope
- No `@letta-ai/letta-agent-sdk` (redundant subset; per-connection `event_seq` blocks the hybrid).
- No letta-teams runtime (Docker-`:8283`-bound; App Server has no native Letta REST).
- No relevance-routing / N-live-conversation arbitration (rail-milestone concerns).
