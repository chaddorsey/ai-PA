---
date: 2026-04-24
topic: memory-consolidation-patterns
sibling: docs/brainstorms/2026-04-24-memfs-upgrade-requirements.md
implementing-plan: TBD (created after this brainstorm converges)
---

# Memory Consolidation Patterns for the ai-PA Ecosystem

## Problem Frame

The ai-PA Letta ecosystem has ~20 agents that today operate without any explicit, intentional memory consolidation discipline. Memory accrues passively in agent blocks (and post-memfs, in markdown files), but there is no scheduled reflection that asks "what did I learn this week, what should I forget, what cross-agent patterns are emerging?" — neither per-agent nor cross-agent.

Letta Code 0.23.7 ships infrastructure that makes this addressable. A 2026-04-24 Letta forum thread (Ezra ↔ DC9753) clarified the actual mechanics:

- **`fork: true` subagents inherit the parent's full canonical history**, cross-client (Telegram, Slack, REST, TUI). The `recall` built-in is one such subagent.
- **The reflection trigger path is hardcoded to `subagentType: "reflection"`** but the markdown body at `~/.letta/agents/reflection.md` overrides the built-in, letting us customize role and tools while keeping the auto-injected transcript payload + parent-memory snapshot.
- **Custom subagents declared in `~/.letta/agents/<name>.md` get any tool surface their frontmatter declares**, including bash + Edit + Read — meaning a "consolidator subagent" with filesystem tools can write memfs files even when the parent agent doesn't have those tools itself.
- **`Task(subagent_type: "...")` invocations come from anywhere** — letta-code TUI sessions, REST API messages, scheduler-service cron jobs.

This unlocks two patterns that didn't seem reachable a week ago:

1. **Per-agent consolidation cadence** for every agent in the ecosystem (not just letta-code-attached MC), via a custom consolidator subagent invoked by scheduler-service or pulse-monitor.
2. **Cross-agent organizational memory** via an `org-observer` agent that uses `recall` (or direct `letta messages search` API) to fetch each domain agent's recent activity, correlates events across them, and curates a shared organizational state that surfaces back into MC and other agents.

Doing this well requires intentional design — what each agent consolidates, how often, into what structure, what's shared across agents, and how the consolidation cadence interacts with the existing sleeptime / pulse-monitor patterns we already have but use only lightly.

This brainstorm captures **what** consolidation should look like for this ecosystem. Implementation plans (per-agent consolidators, org-observer rollout) come later.

## Requirements

### Per-agent consolidation
- **R1.** Every memfs-enabled agent has a consolidator subagent that runs on a defined cadence and produces curated memfs file edits.
- **R2.** The consolidator's role/persona/instructions live in a markdown file at `~/.letta/agents/<agent-role>-consolidator.md` (per-host) or `.letta/agents/<agent-role>-consolidator.md` (per-project), version-controlled where appropriate.
- **R3.** Consolidator cadence is appropriate to agent role — examples: tasks daily, calendar hourly during workday, pulse-monitor more continuously, MC at multiple cadences (transcript-triggered + nightly).
- **R4.** Consolidator output is auditable via `git log` in the agent's memfs repo — every consolidation pass produces a commit attributable to the consolidator subagent.
- **R5.** Consolidators have fallback/escape behavior when transcript or `recall` results are insufficient — they may shell out to `letta messages search` or read attached awareness blocks rather than inventing content.

### Cross-agent organizational memory
- **R6.** An `org-observer` agent or subagent observes activity across the ecosystem (MC, Tasks, Calendar, Email, Pulse, Media, etc.) and curates an organizational-state document that summarizes "what's active across the org right now."
- **R7.** Org-observer runs on a cadence appropriate for ai-PA's pace (likely 2–4×/day, NOT real-time).
- **R8.** Org-observer output is consumable by any agent via either: a shared awareness block attached to relevant agents, OR a dedicated memfs file in MC's `system/org-state.md`, OR both.
- **R9.** Org-observer scope is explicit and bounded — it summarizes activity, threads, commitments, deadlines, and patterns; it does NOT replace any agent's domain-specific consolidator.

### Consolidation infrastructure
- **R10.** Consolidator invocation paths from scheduler-service or pulse-monitor are documented and tested. The mechanism (`POST /v1/agents/{id}/messages` instructing a `Task(subagent_type: "...")` call vs. some more direct invocation) must be empirically verified.
- **R11.** Consolidation activity is observable — there exists a place to read "when did this agent last consolidate, what did it produce, did it succeed."
- **R12.** Failed consolidations don't silently leave the agent in a degraded state — failures surface either via logs scheduler-service can act on, or via a dedicated awareness block, or both.

### Channel coverage
- **R13.** Consolidators see cross-channel activity (not just letta-code TUI sessions). For agents without a primary letta-code session (most production agents), this means using fork-based recall against the canonical server-side history rather than the reflection transcript path.
- **R14.** When MC is involved, consolidation must cover all four MC client paths: pa-web-ui letta-code subprocess, LettaBot Telegram letta-code subprocess, scheduling-orchestrator REST, and direct API calls.

### Compatibility with existing patterns
- **R15.** New consolidation patterns coexist with existing sleeptime agents (e.g. `companion-sleeptime_copy`, `pulse-monitor-agent_copy`, `tasks-agent-sleeptime`, etc.) — the existing copies are not removed by this work.
- **R16.** The six shared-queue Postgres blocks (R20 in sibling doc) remain untouched — consolidators do not write to them. They're external-writer IPC, not consolidation territory.
- **R17.** Consolidator pattern does not interfere with the patched-server / Gitea infrastructure being stood up in the sibling memfs upgrade plan. It builds on top of memfs once that is stable for the relevant agents.

## Success Criteria

- Every memfs-enabled production agent has a defined consolidator with documented cadence, persona, and tool surface — and the consolidator has run successfully at its native cadence for ≥ 1 week without intervention.
- An `org-observer` exists, runs on a cadence, and produces an organizational state document MC can reference. MC visibly behaves with awareness of cross-agent activity (e.g. mentioning an Email-agent-flagged thread when relevant in pa-web-ui).
- Consolidator activity is auditable via `git log` for memfs agents and via a dedicated observability surface for non-memfs.
- No regressions in the six preserved Postgres queue blocks, no regressions in existing sleeptime agents.

## Scope Boundaries

- **Not building**: a generic "consolidation framework" abstraction. Each consolidator is a small, role-specific markdown file. We add abstraction only when concrete duplication forces it.
- **Not migrating**: existing sleeptime `_copy` agents into the new consolidator pattern in this round. They keep doing whatever they're doing today; consolidators are *additive*.
- **Not changing**: the six Postgres queue blocks. Their writers are external services, not consolidators.
- **Not extending**: consolidation to non-Letta surfaces (raw Slack channels, Drive directly, etc.). The consolidator inputs are agent activity (via recall) and memfs files. Extending to raw channels is a separate problem.
- **Not creating**: a permanent persistent "consolidator" agent for any role. All consolidators are stateless ephemeral subagents per Letta's model — they exist only for the duration of the Task call.

## Key Decisions

- **Per-agent consolidator pattern (Option C/D from forum thread) is the default.** Each agent that needs consolidation gets a custom subagent with `~/.letta/agents/<role>-consolidator.md`, invoked via `Task(subagent_type: "...")` from a cadence-driver.
- **Reflection-path overrides (Option A/D) are only used for agents with live letta-code sessions.** For ai-PA, that's primarily MC via pa-web-ui and LettaBot. Other agents are REST-only and need cron-driven invocation.
- **Org-observer is a peer agent, not a subagent of MC.** It runs as a standalone Letta agent so its cadence is independent of MC's activity, and so multiple agents (not just MC) can read its output.
- **Recall is the canonical cross-channel history primitive.** Anywhere a consolidator needs cross-client history, it invokes `Task(subagent_type: "recall", prompt: "...")` rather than inventing its own search.
- **Consolidator outputs are markdown files in memfs (for memfs agents) and labeled awareness blocks (for REST-only agents).** Both are first-class — we don't try to force REST-only agents through memfs prematurely.
- **Cadence ownership lives in scheduler-service**, not in any agent. Scheduler is the system clock; agents react.

## Dependencies / Assumptions

- **HARD DEPENDENCY: letta issue #3205 (Task tool disablement) reconciled.** Every consolidation pattern in this brainstorm depends on `Task(...)` invocations working. Currently Task is in `--disallowedTools` because of self-hosted bugs at our Letta version. This is the foundational gate; without it, this brainstorm is non-implementable. Resolution work is sequenced in sibling plan Phase -1. If Phase -1 cannot reach a resolution, the entire consolidation work is paused and we ship "Path A" (memfs without consolidators) only.
- The sibling memfs upgrade plan reaches C5 (consolidator canary) success before any consolidator work begins on production agents. C5 specifically tests scheduler-service-driven Task invocation, which is the load-bearing mechanism here.
- The empirical question from sibling Phase 4 C3 (do REST writes to a memfs-enabled agent's blocks behave correctly?) is answered. The answer determines whether REST-only agents migrate via memfs or stay on Postgres blocks with awareness-block-based consolidation.
- The C4 multi-channel verdict tells us how MC-shaped agents handle concurrent multi-client writes. Consolidator design depends on this.
- Each agent's Migration Impact Analysis (sibling Phase 4.5) for that agent is signed off before its consolidator goes live.
- Letta Code's behavior holds stable enough across minor versions that consolidator markdown files don't need rewriting per upgrade. We'll re-verify on each letta-code bump.

## Outstanding Questions

### Resolve Before Planning
- **[Affects R3, R6, R7][User decision]** What is the desired cadence shape per agent? Draft proposal:
  - MC: reflection-path on every letta-code TUI session step-count + nightly fork-based deeper consolidation
  - Tasks: daily morning consolidation summarizing yesterday's task flow
  - Calendar: hourly during workday (8–18 ET), summarizing changes
  - Email: daily evening consolidation of email-derived context
  - Pulse: continuous (existing pulse-monitor cadence preserved)
  - Media: weekly
  - Org-observer: 2–4×/day at fixed times
  - Needs user confirmation or revision.
- **[Affects R6, R8][User decision]** Should `org-observer` be a brand-new agent, or repurpose an existing under-used agent (e.g. one of the `companion-sleeptime_copy` or one of the `MC-rogue-*` forks)? If new: needs naming, model selection, persona scope.
- **[Affects R8, R14][User decision]** Where does `org-observer` output live? Three options: (a) shared awareness block attached to MC + relevant agents; (b) dedicated `system/org-state.md` in MC's memfs only; (c) both, with the awareness block as fallback for REST-only agents and the memfs file as primary for MC. (c) is my draft preference.

### Deferred to Planning
- **[Affects R10][Needs research]** Concrete invocation mechanism for cron-driven Task calls: does `POST /v1/agents/{id}/messages` with a message instructing a Task tool call work cleanly, or does scheduler-service need a more direct path? Empirical verification in sibling Phase 4 test 7.
- **[Affects R2][Technical]** Where do consolidator markdown files live in version control? `~/.letta/agents/` is per-host; `.letta/agents/` per-project. For shared/reproducible deployment we likely want a `letta/consolidators/` directory in the repo and a deploy step that rsyncs it into `~/.letta/agents/` on the host.
- **[Affects R4, R11][Technical]** Observability surface for consolidator runs: `git log` in memfs repos covers memfs agents; for REST-only agents we need a `consolidator_runs` table or a structured log target.
- **[Affects R12][Technical]** Failure handling: what does scheduler-service do when a consolidator Task call fails? Retry policy, alerting, dead-letter, etc.
- **[Affects R6, R9][Needs research]** Org-observer scope and frontmatter: tools (probably Bash + Read + Write + Task for nested recall calls), `fork: true` or not (probably not — it should iterate across agents, not inherit one), model (probably gpt-5-mini or similar).
- **[Affects R13][Technical]** Recall costs at scale: each consolidator invoking recall forks the parent conversation server-side. For frequent cadences (calendar hourly), is this affordable in latency / Postgres load? Needs measurement once Phase 4 is alive.

## Next Steps

→ Sibling memfs upgrade plan Phase -1 (Task reconciliation) MUST complete first; without it this brainstorm is non-implementable.
→ Sibling memfs upgrade plan C2–C5 canary results inform the planning here.
→ Resolve the three blocking questions above through user discussion in parallel with sibling work, but do not start `/ce:plan` until sibling Phase 4.5 (impact analysis template) exists — per-agent consolidator rollout planning depends on it.
