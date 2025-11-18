# PBI-21: Scheduling Orchestration Tool

## Overview
Deliver **one** custom Letta tool, `orchestrate_scheduling`, that embeds DSPy for robust language→JSON extraction and clingo for optimal scheduling on a 15‑minute grid. Letta supplies events via **Get_Events**; on success, the tool returns **ready‑to‑schedule** slot proposals. On failure (UNSAT), it returns clear relaxations.

[View in Backlog](../backlog.md#user-content-21)

## Problem Statement
Multi‑party scheduling across calendars fails with heuristics; we need a **sound optimizer** (ASP) invoked through a **single** robust call, because Letta struggles with long tool chains. Current approaches require multiple tool invocations and manual coordination, leading to suboptimal scheduling decisions and user frustration.

## User Stories
- As an executive, I want Letta to understand my natural language scheduling requests and automatically find optimal meeting times that respect my preferences and minimize disruption to my calendar.
- As a Letta agent, I need a single reliable tool that takes calendar events and a scheduling request, then returns ready-to-schedule proposals with clear explanations.
- As a user, I want the scheduling tool to respect my hard constraints (no double bookings, working hours) while optimizing for my preferences (focus blocks, minimal disruption).

## Technical Approach
- **Letta Integration**: One tool with typed signature/docstring (or Pydantic schema) so Letta generates a tool schema automatically. Tool code lives in `letta/scheduling_orchestrator/` directory.
- **DSPy**: In‑tool `Predict`/`ChainOfThought` for extraction; `BestOfN/Refine` + schema validator for reliability. Used for converting natural language requests into structured JSON and generating human-readable explanations.
- **ASP (clingo)**: Python API `Control.ground/solve`; `#minimize` with levels; grid‑time encoding at 15 minutes. Handles constraint satisfaction and lexicographic optimization.
- **Dependencies**: DSPy and clingo installed in Letta container's Python environment via `letta/requirements.txt`. These are shared dependencies for future tools.
- **Policy/Configuration**: Policy/rule data passed in and out as JSON via `context_json` parameter, not edited directly inside ASP code.

## UX Flow (Agent)
1. Agent calls **Get_Events** for the desired horizon (per participants).
2. Agent calls **orchestrate_scheduling** with `utterance + events_by_participant + context_json`.
3. Agent picks `proposals[0]` and creates the event(s); if `unsat`, it presents relaxations to the user.

## Functional Requirements
1. **Input**: `utterance` (str), `events_by_participant` (dict with expanded instances within a horizon), optional `context_json` (dict).
2. **Output**: `status` (ok/unsat/bad_input), `proposals[]` (title, participants, `start_utc`, `end_utc`, moved‑events), `explanation` (str), `debug` (dict with ASP stats).
3. **Hard constraints (ASP)**: no overlaps; respect windows/work hours/min gaps; honor hard‑locked events.
4. **Soft constraints (ASP, lexicographic)**: protect "protected" events; minimize total moved minutes; maximize long focus blocks; incorporate participant preferences.
5. **UNSAT handling**: Provide ranked relaxations (e.g., widen window, allow off‑hours up to X).
6. **Latency**: complete within agreed budget for a typical 2–3 week horizon and <10 participants.

## Goals & Non‑Goals
- **Goals**: 
  - One tool interface; 15‑min grid; lexicographic objectives; focus‑block maximization; move‑cost minimization; participant preference handling; UNSAT relaxations; concise, schedulable output.
- **Non‑Goals**: 
  - Direct Google Calendar writes (delegated to Letta agent)
  - Separate classical "expand calendars" or "commit plan" tools (delegated to Letta)
  - Real-time calendar synchronization (assumes Get_Events provides snapshot)

## Acceptance Criteria
- End‑to‑end scenario demos: common slot finding; maximize focus blocks; recurring cadence with small jitter costs.
- Produces **single best** proposal with explanation under lexicographic optimization.
- On missing events input, returns `bad_input` + a concrete Get_Events query spec.
- Tool schema renders correctly in Letta; manual test call succeeds.
- Tool completes within time budget for typical 2-3 week horizons with <10 participants.

## Dependencies
- Letta agent with Get_Events capability (assumed to exist)
- DSPy library (`dspy-ai`) installed in Letta container
- clingo library (`clingo`) installed in Letta container
- LLM API keys configured via Letta tool environment variables

## Open Questions
- What is the target latency budget for typical scheduling requests?
- Should the tool support multiple meeting proposals in a single call, or always return a single best option?
- How should recurring meeting patterns be handled in the initial version?

## Related Tasks
- [Back to task list](./tasks.md)
- Tasks tracked in `docs/delivery/21/tasks.md` with detailed files:
  - 21-1 Define orchestration tool interface & schemas
  - 21-2 Event payload normalizer → 15-min grid
  - 21-3 ASP encoding (grid, hard constraints)
  - 21-4 ASP soft constraints & lexicographic objectives
  - 21-5 clingo wrapper & model extraction
  - 21-6 DSPy extraction program
  - 21-7 UNSAT explanation & relaxation suggestions
  - 21-8 Assemble orchestrate_scheduling tool
  - 21-9 Letta registration & schema verification
  - 21-10 Scenario tests & evaluation metrics
  - 21-11 Observability & audit logs
  - 21-12 Security & configuration

