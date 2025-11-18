# Tasks for PBI 21: Scheduling Orchestration Tool

This document lists all tasks associated with PBI 21.

**Parent PBI**: [PBI 21: Scheduling Orchestration Tool](./prd.md)

## Task Summary

| Task ID | Name | Status | Description |
| :------ | :----------------------------------------------- | :------- | :----------------------------------------------- |
| 21-1 | [Define orchestration tool interface & schemas](./21-1.md) | Proposed | Specify the single Letta tool orchestrate_scheduling with typed args/docstring or Pydantic models. Define input/output schemas. |
| 21-2 | [Event payload normalizer → 15-min grid](./21-2.md) | Proposed | Transform events_by_participant (from Get_Events) into discrete 15-minute slot facts over the planning horizon. |
| 21-3 | [ASP encoding (grid, hard constraints)](./21-3.md) | Proposed | Write the clingo logic for selecting one start slot per request, occupying D slots, no overlaps, windows, work hours, min gaps. |
| 21-4 | [ASP soft constraints & lexicographic objectives](./21-4.md) | Proposed | Add weak constraints with levels (lexicographic): L1 Protect protected events; L2 minimize total moved minutes; L3 maximize focus blocks; L3 respect participant preferences. |
| 21-5 | [clingo wrapper & model extraction](./21-5.md) | Proposed | Inside the tool, build the wrapper that compiles facts, grounds, solves, extracts start/2, occurs/2, computes move deltas and objective scores, and collects stats. |
| 21-6 | [DSPy extraction program](./21-6.md) | Proposed | Define ExtractSchedulingRequest(utterance, context_json) -> problem_delta_json signature; use BestOfN/Refine with a JSON validator for reliability. |
| 21-7 | [UNSAT explanation & relaxation suggestions](./21-7.md) | Proposed | If UNSAT, turn blocking facts/assumptions into human-readable causes and ranked relaxations. Optionally use DSPy to verbalize. |
| 21-8 | [Assemble orchestrate_scheduling tool](./21-8.md) | Proposed | Combine tasks 21-2..21-7 into the single tool. Ensure internal steps are deterministic and bounded. |
| 21-9 | [Letta registration & schema verification](./21-9.md) | Proposed | Register the tool in Letta ADE/SDK, verify the JSON schema, display names/docs, and run a manual test call with sample events. |
| 21-10 | [Scenario tests & evaluation metrics](./21-10.md) | Proposed | Create scenario scripts for: (a) common slot finding, (b) focus-block day reflow, (c) recurring cadence with jitter. Metrics: total moved minutes, longest focus block, preference satisfaction %. |
| 21-11 | [Observability & audit logs](./21-11.md) | Proposed | Log inputs, chosen objective values, proposals, and explanations. Redact PII as configured. |
| 21-12 | [Security & configuration](./21-12.md) | Proposed | Set timeouts, memory limits; handle secrets (LM keys) via Letta tool configuration; document allowed horizon sizes. Add dependencies to letta/requirements.txt. |

