---
title: "Scheduler job inventory — LETTA_CALLBACK_URL re-point dispositions (C7 prerequisite)"
type: assessment
status: NEEDS-OPERATOR-REVIEW
date: 2026-08-16
origin: docs/plans/2026-08-15-006-feat-continuity-controller-plan.md (Unit C7 → consumed by C10b)
---

# Scheduler job inventory — the `LETTA_CALLBACK_URL` re-point (C7 cutover prerequisite)

Queried live from scheduler-service (`:8087/v1/jobs`, 2026-08-16): **2212 jobs total, 26
active** (`scheduled`). Routing is decided per-action in `actions.py`: `agent_message` with
`route` unset/`letta` POSTs to `LETTA_CALLBACK_URL`; `route=local` goes to the local runner
(`:8920`); `http`/`script` actions never touch the callback URL.

## The headline finding

**Zero active jobs use `route=letta`.** Every historical `route=letta`/unset-route job (the
Docker-agent era, including the daily-schedule agent's one-offs) is `cancelled`. Re-pointing
`LETTA_CALLBACK_URL` at the controller ingress therefore changes the behaviour of **no active
job** — it is a forward-looking re-point, not a migration.

## Active-job dispositions

| Jobs | Action / route | Uses LETTA_CALLBACK_URL? | Disposition |
|---|---|---|---|
| 2 (`6afa76c3` tasks-agent self-check, `1ccfae03` calendar-agent self-check) | `agent_message` / `local` | No (local runner :8920) | **Unchanged.** Optional future migration to controller ingress is an operator decision, not a cutover requirement. |
| 17 (Drive RAG/staleness ×8, Curator Radar ×5, Granola ×3, OmniFocus snapshot) | `http` | No | Unchanged. |
| 7 (analytics bronze/silver, enrichment scanner, stall monitor, signals heartbeat, steward rollup, memfs soak) | `script` | No | Unchanged. |

Agent-id mapping (the 2026-08-12 spike's Docker→local concern): the two active
`agent_message` jobs already target LOCAL agent ids (`agent-local-30c45759…`,
`agent-local-cd5ed5cd…`). No per-job id rewrite is needed.

## Cutover consequences (folded into the runbook)

1. `LETTA_CALLBACK_URL` → `http://host.docker.internal:<ingress-port>/…` with the shared
   secret. Two secret presentations exist; **the bearer header requires a scheduler-side code
   change** (actions.py's `_send_via_letta` sets no headers), while the **path-token form
   (`/t/<secret>/v1/agents/{agent_id}/messages`) is config-only** but leaks the secret into
   scheduler logs (actions.py logs the full URL on info AND error). Operator call at cutover;
   default recommendation: path-token now (config-only, logs are local), header once
   actions.py is next touched.
2. New `route=letta` jobs created after cutover deliver through the controller: 202-on-accept,
   scheduler executions = delivery records, turn outcome = controller journal (semantics change
   documented in the runbook).
3. The one-off rehearsal job `e054f4b5` ("C7 10:55 clone rehearsal") has fired and is done;
   archive at leisure.

**NEEDS-OPERATOR-REVIEW**: the route=local migration question (row 1) and the secret
presentation choice (consequence 1).
