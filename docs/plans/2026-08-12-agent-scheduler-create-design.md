# Agents creating scheduler jobs — design

**Date:** 2026-08-12
**Status:** Approved design, pre-implementation
**Component:** `~/.local/bin/scheduler` (local-agent CLI) → `scheduler-service` REST (`POST /jobs`)

## Problem

Local-mode agents have a `scheduler` CLI (list/search/get/update/delete/archive/executions/trigger) but **no `create`** — it was scoped read-and-manage only. An agent that "found the scheduler tool" correctly reported it "didn't have create permissions": there is literally no create path in the CLI. The service's create endpoint is otherwise open (see Security below).

Goal: let agents **create** scheduler jobs, with a clean audit trail and one-shot revocability.

## Decisions (from brainstorming)

1. **Scope: full job creation.** Agents may create any action type — `agent_message`, `script`, `http` — on any schedule (cron / interval / one-off / natural).
2. **Guardrail posture: auto-tag + bulk-undo.** Not restriction — visibility + revocability.
3. **Permission model: full, rely on audit only.** Job execution privileges do NOT inherit the creating agent's capability (see Security); this is accepted for a single-user home server. No action-type is blocked.

## Security model (explicit, since it's the crux)

- **No per-agent gate at create time.** The `POST /jobs` endpoint is unauthenticated on `pa-internal` (the `SCHEDULER_API_KEY` setting exists but is not wired to any route). The CLI does not verify agent identity; `created_by` is a self-declared stamp.
- **Execution uses the scheduler-service's privileges, not the agent's.** Actions run inside the scheduler-service container, decoupled from the agent sandbox. Pre-existing guardrails bound this:
  - `script` actions are confined to a **human-curated, read-only allow-listed dir** (`settings.allowlist_script_dir`); `_resolve_allowlisted_script()` rejects path escapes and requires the file to pre-exist; run via **`exec`, not a shell**. Enforced at execution regardless of creator → agents can only *trigger pre-vetted scripts*, never inject code.
  - `agent_message` is bounded (messages an agent).
  - `http` is the **one open vector**: a job can call any URL from the internal network. **Accepted risk** per decision 3.
- **`ActionConfig.allow_list_tag`** is a latent per-action-class permission hook in the schema — noted as a FUTURE lever if the HTTP surface ever needs restricting; not built now (YAGNI).

## Design

Pure CLI addition (`~/.local/bin/scheduler`, bash) — no scheduler-service changes.

### `scheduler create`
Ergonomic flags so agents build valid jobs without hand-rolling JSON:
- **Schedule (one of):** `--cron "0 6 * * *"` | `--every <seconds>` | `--at <ISO8601>` | `--when "<natural language>"`.
- **Action (one of):** `--message "<text>" --to-agent <id>` | `--script <name> [--args "<json array>"]` | `--http <url> [--method POST] [--body "<json>"]`.
- **Meta:** `--title "<t>"` (required), `--description "<d>"`.
- **Escape hatches:** `--schedule-json '{...}'`, `--action-json '{...}'` for anything the shorthands don't cover.
- **Auto-stamped:** `category` = `--category` else **`agent-created`**; `created_by` = `--created-by` else `$SCHEDULER_CREATED_BY` env else `agent`.
- POSTs the assembled payload `{title, description, created_by, category, schedule{type,expression}, actions[{action_type,config}]}` to `{SCHEDULER_URL}/jobs`.
- On success prints the new job id **and** the exact undo command.

### `scheduler cancel-all` (the revocability lever)
- `scheduler cancel-all --created-by <x>` and/or `--category <c>` (default filter `category=agent-created`).
- Lists matching **non-terminal** jobs, shows a count, cancels/archives them. `--yes` to skip the confirm (for agent use); interactive confirm otherwise.
- This is what makes "let agents schedule freely" safe: wipe an agent's scheduled jobs in one command.

### Agent enablement
Once `create` exists, agents discover it via `scheduler --help`. Add a one-line pointer to the relevant agent recipes/memfs (e.g. tasks/MC) so they know the capability exists — small follow-on.

## Error handling
- Missing required flag (title, or no schedule/action) → clear usage error, non-zero exit.
- Bad `--*-json` → validation error before POST.
- Service rejects payload (400) → surface the service error body.
- `cancel-all` with no matches → report "0 jobs" and exit 0.

## Testing
- `scheduler create` an `agent_message` job (`--message ... --to-agent ...`, `--cron`) → assert 201, job lands with `created_by`/`category=agent-created`, correct schedule.
- `scheduler create` a `script` job (`--script <an allow-listed script>`) → assert it lands; (optionally `trigger` it → executes).
- Negative: `--script ../../etc/passwd` style → job creates but execution would reject (allow-list) — assert the allow-list holds if triggered.
- `scheduler cancel-all --category agent-created --yes` → assert the created jobs move to cancelled/archived and a re-list shows none.
- Run against the live scheduler-service.

## Out of scope / future
- Restricting the HTTP vector via `allow_list_tag` (deferred — accepted risk).
- Per-agent capability mapping (deferred).
- Quotas/rate limits on agent-created jobs (deferred; `cancel-all` + tagging cover the practical need).
