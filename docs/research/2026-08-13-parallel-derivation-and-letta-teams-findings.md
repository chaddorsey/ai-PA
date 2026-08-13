---
title: "Parallel derivation, model-backend contention, SDK & letta-teams — findings"
type: findings
status: complete
date: 2026-08-13
related:
  - docs/plans/2026-08-13-fleet-fanout-orchestrator-sketch.md
  - docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md
  - docs/plans/2026-08-12-multi-surface-ws-spike-findings.md
---

# Findings: parallel agent derivation on the sole-owner App Server

Lightweight bullets. Decision rationale behind the fleet fan-out orchestrator sketch.

## Question
- Should we fan out derivation across the local fleet in parallel and synthesize back to Kinara? Which transport — raw App Server, the Agent SDK, or letta-teams?

## Model routing reality (corrects an earlier assumption)
- Local fleet agents send model calls to a proxy at `http://localhost:4001/v1` (litellm), which routes to **cloud** providers: `deepseek-v4-flash` → **Fireworks**; `gpt-4.1-mini/*`, `gpt-5-mini/*` → **OpenAI**, each agent with its **own API key** (per-agent cost tracking in `litellm/config.yaml`).
- The `lmstudio/...` prefix on the agent model string is a naming artifact; **LM Studio (`:1234`) is not running**. There is **no single local GPU bottleneck** — the earlier worry was wrong.

## Benchmark (2026-08-13, `/v1/responses`, benign "count to 30" prompt, utility agents)
- Single-agent baseline (docs): **~3.1s** median.
- Same-agent ×4 concurrent (fresh convs): **4.0s** wall = **×1.3** of one call → ~parallel, ~30% overhead (no ×4 serialization).
- Cross-agent 5 sequential: **10.9s**. Cross-agent 5 concurrent: **4.5s** = ≈ the **slowest single agent** (docs @4.5s).
- Verdict: **near-ideal parallelism.** Concurrent wall tracks max(individual), not sum. Fan-out is worth it.
- Caveats: N≤5, cheap no-tool prompts. Real derivation (long gen, tool calls) costs more/call but keeps the parallelism property; ceiling = per-provider/per-key rate limits (raised by spreading across keys/providers), not local hardware.

## Transport decision
| Need | Tool | Note |
|------|------|------|
| Stateless parallel/batch derivation | OpenAI `/v1/responses` shim (reuse `AppServerClient`) | proven-parallel; ~30-line orchestrator |
| Stateful interactive continuity (mirror live) | continuity-core raw `/ws` (Unit 4, built) | one ordered connection, `event_seq` |
| Throwaway non-continuity chat demo | `@letta-ai/letta-agent-sdk` (optional, pinned) | not worth adopting broadly |

- **SDK verdict:** a partial, churning wrapper (24 versions/7 weeks) over a *subset* of the WS protocol we already own — no conversation CRUD, approvals, `update_subagent_state`; drops foreign `turn_finished`; no auto-replay. Decisive blocker for a hybrid: **`event_seq` is per-connection**, so SDK-for-chat + raw-WS-for-continuity on one conversation = two `event_seq` domains = the merge race the single-connection design removes. Squeezed out from both sides (HTTP is simpler for stateless; raw WS is complete for stateful).

## letta-teams (`.skills/letta-teams` + `.lteams/` + daemon `:9774`)
- **What it is:** a native multi-agent orchestration CLI/daemon — `spawn`, `broadcast`, `dispatch A=.. B=.. -w` (fan-out + wait), `dashboard`, self-report `todo/work/progress`. A mature implementation of exactly the fan-out/fan-in pattern.
- **Why not for us (runtime):**
  1. **Bound to Docker Letta (`:8283`)** — hardcodes `LETTA_BASE_URL=http://localhost:8283` and drives the full Letta REST/SDK. The sole-owner App Server (`:4577`) returns **404 on `/v1/agents` and `/v1/conversations`** (no native Letta REST — only `/ws` + OpenAI shim). So letta-teams **cannot run against the App Server**; it's coupled to the backend M1 is consolidating away from.
  2. **Generic teammates** — `spawn <name> <role>` creates fresh generic agents (observed: a "researcher", `agent-a71365ed`, not on our local backend). The value of *our* fan-out is the **specialized** fleet (docs=Drive RAG, calendar=schedule, pulse=analytics), which generic teammates lack.
- **Value:** (a) validates the pattern is first-class in the ecosystem; (b) a good **design reference** for our orchestrator's UX (dispatch/broadcast/dashboard/progress). Borrow design, not runtime.
- **Housekeeping:** its daemon (`:9774`) is another always-on, Docker-Letta-coupled surface — note it in the eventual Docker-Letta retirement accounting (separate from the lc-local-backend single-writer set).

## Recommendation
- Build a thin **fleet fan-out orchestrator** on `/v1/responses` over the real specialized fleet (sketch: sibling doc). Aligned with the sole-owner architecture, proven-parallel, reuses `AppServerClient`/`DEFAULT_AGENTS`, synthesizes into Kinara (stateless or via continuity-core).
- Keep the SDK and letta-teams out of the runtime path; mine letta-teams for UX only.
