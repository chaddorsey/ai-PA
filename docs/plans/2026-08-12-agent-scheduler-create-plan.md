# Agent scheduler-create — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add `scheduler create` (full job creation, auto-tagged) and `scheduler cancel-all` (bulk-undo) to the local-agent `scheduler` CLI, so agents can schedule jobs and you can see/wipe what they scheduled.

**Architecture:** Pure additions to the existing bash CLI `scripts/scheduler` (symlinked to `~/.local/bin/scheduler`). No scheduler-service changes — the `POST /v1/jobs` endpoint is already open and script actions are already allow-list-guardrailed at execution. Payloads are built with `jq`; requests go through the CLI's existing `sched_curl` helper.

**Tech Stack:** bash, `jq`, `curl` (via `sched_curl`), scheduler-service REST at `${SCHEDULER_BASE_URL:-http://localhost:8087}`, endpoints under `/v1/jobs`.

**Design doc:** `docs/plans/2026-08-12-agent-scheduler-create-design.md`

## Global Constraints

- Edit ONLY `scripts/scheduler` (repo-tracked; `~/.local/bin/scheduler` symlinks to it — no separate deploy). NEVER `git add -A`.
- Reuse existing helpers verbatim: `sched_curl <METHOD> <path> [body]` (returns response body on 2xx, prints `ERROR (code): body` + non-zero on failure); base var `SCHED`; `jq` for all JSON.
- Job payload schema (verified against `scheduler-service`): `{"title","description","created_by","category","schedule":{"type","expression"[,"next_run_at","timezone"]},"actions":[{"action_type","config"}]}`.
- Enum values (exact): ScheduleType = `cron|interval|one_off|natural`; ActionType = `agent_message|script|http|webhook|lettabot_heartbeat`.
- Action config shapes: `agent_message` → `{"agent_id","message"}`; `script` → `{"script","args":[...],"env":{...}}`; `http` → `{"url","method","headers":{...},"body":...}`.
- **Auto-tag (mandatory):** every `create` sets `category` = `--category` value else `agent-created`, and `created_by` = `--created-by` value else `$SCHEDULER_CREATED_BY` else `agent`.
- Tests are live CLI invocations against the running scheduler-service (the CLI's `list` works today, so connectivity exists). Clean up test jobs via `cancel-all`/`archive` at the end of each test.
- Commit trailers on every commit:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01FrcfiaJfK8YFtrW9w3Scru`

## File Structure

- `scripts/scheduler` — **modify.** Add `cmd_create` + `cmd_cancel_all` bash functions, two `case` branches in the dispatcher, and two `--help` usage blocks. Everything lives in this one file (matches the existing single-file CLI).

---

## Task 1: `scheduler create`

**Files:** Modify `scripts/scheduler` (add `cmd_create`, dispatcher `create)` branch, `--help` entry).

**Interfaces:**
- Produces: `scheduler create --title T (--cron X|--every N|--at ISO|--when "…"|--schedule-json J) (--message M --to-agent ID | --script NAME [--args JSON] | --http URL [--method M] [--body B] | --action-json J) [--description D] [--category C] [--created-by U]` → POSTs to `/v1/jobs`, prints created job id + undo hint.

- [ ] **Step 1: Failing test — `create` subcommand doesn't exist yet**

Run: `scheduler create --title x --cron "0 6 * * *" --message hi --to-agent abc`
Expected: fails with `unknown subcommand: create` (current behavior).

- [ ] **Step 2: Add `cmd_create` and wire the dispatcher**

In `scripts/scheduler`, add this function (above the dispatcher `case`):
```bash
cmd_create() {
  local title="" desc="" category="" created_by=""
  local sched_type="" sched_expr_json="" next_run="" sched_json=""
  local act_type="" act_config_json="" act_json=""
  local http_method="POST" http_body="" script_args="[]" msg="" to_agent="" http_url="" script_name=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --title)         title="$2"; shift 2 ;;
      --description)   desc="$2"; shift 2 ;;
      --category)      category="$2"; shift 2 ;;
      --created-by)    created_by="$2"; shift 2 ;;
      --cron)          sched_type="cron";     sched_expr_json="$(jq -nc --arg c "$2" '{cron:$c}')"; shift 2 ;;
      --every)         sched_type="interval"; sched_expr_json="$(jq -nc --argjson s "$2" '{seconds:$s}')"; shift 2 ;;
      --at)            sched_type="one_off";  sched_expr_json="{}"; next_run="$2"; shift 2 ;;
      --when)          sched_type="natural";  sched_expr_json="$(jq -nc --arg t "$2" '{text:$t}')"; shift 2 ;;
      --schedule-json) sched_json="$2"; shift 2 ;;
      --message)       act_type="agent_message"; msg="$2"; shift 2 ;;
      --to-agent)      to_agent="$2"; shift 2 ;;
      --script)        act_type="script"; script_name="$2"; shift 2 ;;
      --args)          script_args="$2"; shift 2 ;;
      --http)          act_type="http"; http_url="$2"; shift 2 ;;
      --method)        http_method="$2"; shift 2 ;;
      --body)          http_body="$2"; shift 2 ;;
      --action-json)   act_json="$2"; shift 2 ;;
      *) echo "ERROR: unknown flag $1" >&2; return 2 ;;
    esac
  done
  [[ -z "$title" ]] && { echo "ERROR: --title required" >&2; return 2; }

  # Auto-tag
  [[ -z "$category" ]] && category="agent-created"
  [[ -z "$created_by" ]] && created_by="${SCHEDULER_CREATED_BY:-agent}"

  # Build schedule object
  local schedule
  if [[ -n "$sched_json" ]]; then
    schedule="$sched_json"
  elif [[ -n "$sched_type" ]]; then
    schedule="$(jq -nc --arg t "$sched_type" --argjson e "$sched_expr_json" \
                 --arg nr "$next_run" '{type:$t, expression:$e} + (if $nr=="" then {} else {next_run_at:$nr} end)')"
  else
    echo "ERROR: a schedule is required (--cron/--every/--at/--when/--schedule-json)" >&2; return 2
  fi

  # Build action config
  local action
  if [[ -n "$act_json" ]]; then
    action="$act_json"
  elif [[ "$act_type" == "agent_message" ]]; then
    [[ -z "$to_agent" ]] && { echo "ERROR: --message requires --to-agent" >&2; return 2; }
    action="$(jq -nc --arg a "$to_agent" --arg m "$msg" '{action_type:"agent_message", config:{agent_id:$a, message:$m}}')"
  elif [[ "$act_type" == "script" ]]; then
    action="$(jq -nc --arg s "$script_name" --argjson args "$script_args" '{action_type:"script", config:{script:$s, args:$args}}')"
  elif [[ "$act_type" == "http" ]]; then
    action="$(jq -nc --arg u "$http_url" --arg m "$http_method" --arg b "$http_body" \
               '{action_type:"http", config:({url:$u, method:$m} + (if $b=="" then {} else {body:$b} end))}')"
  else
    echo "ERROR: an action is required (--message+--to-agent / --script / --http / --action-json)" >&2; return 2
  fi

  local body
  body="$(jq -nc --arg t "$title" --arg d "$desc" --arg cb "$created_by" --arg cat "$category" \
            --argjson sch "$schedule" --argjson act "$action" \
            '{title:$t, description:$d, created_by:$cb, category:$cat, schedule:$sch, actions:[$act]}')"

  local out; out="$(sched_curl POST "/v1/jobs" "$body")" || return 1
  local jid; jid="$(echo "$out" | jq -r '.id // .job_id // empty')"
  echo "$out" | jq .
  echo "created job ${jid} (created_by=${created_by}, category=${category})" >&2
  echo "undo: scheduler cancel-all --category ${category}   # or: scheduler archive ${jid}" >&2
}
```
Add to the dispatcher `case` (next to `update)`/`delete)`):
```bash
  create)       shift; cmd_create "$@" ;;
```

- [ ] **Step 3: Verify the confident happy path against the live service**

Run:
```bash
scheduler create --title "TEST agent create" --cron "0 6 * * *" \
  --message "test ping" --to-agent "agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4"
```
Expected: prints a JSON job with `category:"agent-created"`, `created_by:"agent"`, `status:"scheduled"`, and the schedule; stderr shows `created job <id>` + undo hint. Then confirm it lands:
```bash
scheduler list --category agent-created --format table
```
Expected: the TEST job appears.

- [ ] **Step 4: Verify a `script` action + the `--at`/`--when` shapes empirically**

Create a script job (use any name already in the allow-listed scripts dir, or a dummy — creation succeeds regardless; execution is what enforces the allow-list):
```bash
scheduler create --title "TEST script" --every 3600 --script "noop.sh"
```
Expected: 201, job lands. Then probe the uncertain shapes and RECONCILE:
```bash
scheduler create --title "TEST at" --at "2030-01-01T06:00:00Z" --message hi --to-agent abc
scheduler create --title "TEST when" --when "every weekday at 6am" --message hi --to-agent abc
```
If either returns a 400, read the error body and adjust the `--at`/`--when` builder in `cmd_create` (e.g. `one_off` may want the datetime in `expression` rather than `next_run_at`; `natural` may want a bare string). If a shape can't be quickly confirmed, leave that shorthand routing through `--schedule-json` and note it in the `--help` text. Re-run until each either works or is documented as escape-hatch-only.

- [ ] **Step 5: Add the `--help` usage block**

Add a `create` section to the CLI's usage text mirroring the existing style (list the schedule flags, the action flags, `--title/--description/--category/--created-by`, and the escape hatches). Include the auto-tag note: "jobs are tagged category=agent-created + created_by unless overridden; undo with `scheduler cancel-all`."

- [ ] **Step 6: Clean up test jobs + commit**

```bash
scheduler cancel-all --category agent-created --yes 2>/dev/null || \
  for id in $(scheduler list --category agent-created --format json | jq -r '.[]?.id // (.jobs[]?.id)'); do scheduler archive "$id"; done
git add scripts/scheduler
git commit -m "feat(scheduler-cli): add 'create' subcommand (full job creation, auto-tagged)"
```

---

## Task 2: `scheduler cancel-all`

**Files:** Modify `scripts/scheduler` (add `cmd_cancel_all`, dispatcher `cancel-all)` branch, `--help` entry).

**Interfaces:**
- Consumes: the `category=agent-created` tag from Task 1; the existing `list` query params (`created_by_filter`, `category`) and the batch-cancel endpoint.
- Produces: `scheduler cancel-all [--created-by U] [--category C] [--yes]` → cancels all matching non-terminal jobs.

- [ ] **Step 1: Confirm the batch-cancel endpoint shape**

Run: `grep -nA12 'batch/cancel' scheduler-service/src/scheduler_service/routes/jobs.py`
Determine the request body shape (e.g. `{"job_ids":[...]}`). If a batch-cancel endpoint isn't usable, fall back to per-job `delete` (PATCH status→cancelled) in a loop. Record which you'll use.

- [ ] **Step 2: Failing test**

Run: `scheduler cancel-all --category agent-created`
Expected: `unknown subcommand: cancel-all` (current behavior).

- [ ] **Step 3: Implement `cmd_cancel_all` + wire dispatcher**

Add (using the endpoint shape confirmed in Step 1; example assumes `POST /v1/jobs/batch/cancel {"job_ids":[...]}`):
```bash
cmd_cancel_all() {
  local created_by="" category="agent-created" assume_yes=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --created-by) created_by="$2"; shift 2 ;;
      --category)   category="$2"; shift 2 ;;
      --yes|-y)     assume_yes=1; shift ;;
      *) echo "ERROR: unknown flag $1" >&2; return 2 ;;
    esac
  done
  local qs="?status_filter=scheduled"
  [[ -n "$created_by" ]] && qs+="&created_by_filter=${created_by}"
  [[ -n "$category" ]]   && qs+="&category=${category}"
  local jobs ids
  jobs="$(sched_curl GET "/v1/jobs${qs}")" || return 1
  ids="$(echo "$jobs" | jq -r '(. // .jobs // [])[].id')"
  local n; n="$(echo "$ids" | grep -c . || true)"
  if [[ "$n" -eq 0 ]]; then echo "0 matching jobs" >&2; return 0; fi
  if [[ "$assume_yes" -ne 1 ]]; then
    echo "About to cancel ${n} job(s) (created_by='${created_by:-*}' category='${category:-*}'). Ctrl-C to abort; Enter to proceed." >&2
    read -r _
  fi
  local ids_json; ids_json="$(echo "$ids" | jq -R . | jq -sc '{job_ids: .}')"
  sched_curl POST "/v1/jobs/batch/cancel" "$ids_json" | jq .
  echo "cancelled ${n} job(s)" >&2
}
```
Dispatcher: `  cancel-all)   shift; cmd_cancel_all "$@" ;;`

- [ ] **Step 4: Test end-to-end**

```bash
scheduler create --title "TEST cancelall 1" --cron "0 6 * * *" --message x --to-agent abc
scheduler create --title "TEST cancelall 2" --every 3600 --message y --to-agent abc
scheduler cancel-all --category agent-created --yes
scheduler list --category agent-created --status scheduled --format table
```
Expected: cancel-all reports `cancelled 2 job(s)`; the final list shows 0 scheduled agent-created jobs.

- [ ] **Step 5: Add `--help` + commit**

Add a `cancel-all` usage block. Then:
```bash
git add scripts/scheduler
git commit -m "feat(scheduler-cli): add 'cancel-all' bulk-undo for agent-created jobs"
```

---

## Task 3: Agent enablement note (lightweight)

**Files:** none in-repo necessarily — agent recipes live in per-agent memfs (not git-tracked).

- [ ] **Step 1:** Confirm `scheduler --help` now advertises `create` and `cancel-all` (done in Tasks 1–2), so agents discover the capability automatically.
- [ ] **Step 2:** Note for the human: to actively prompt an agent to use it, add a one-line pointer to the relevant agent's memfs recipe (e.g. tasks/MC): "You can schedule jobs with `scheduler create …` (auto-tagged; `scheduler cancel-all` to undo)." This is a runtime memfs edit, not a repo change — flagged, not automated here.

---

## Self-Review

- **Spec coverage:** `create` full-capability with all action types (Task 1: agent_message/script/http + escape hatches); auto-tag created_by+category (Task 1 Step 2); ergonomic schedule flags incl. empirically-verified at/when (Task 1 Step 4); `cancel-all` bulk-undo (Task 2); agent enablement (Task 3); no scheduler-service changes (constraint). Security posture unchanged (documented in design). Covered.
- **Placeholders:** none — real bash/jq in every step. The two genuinely-uncertain shapes (one_off/natural expression; batch-cancel body) are explicit empirical-verification steps against the live service, not guesses.
- **Consistency:** `cmd_create`/`cmd_cancel_all`, `category=agent-created`, `created_by` default `agent`, `sched_curl`, `/v1/jobs` — consistent across tasks.
