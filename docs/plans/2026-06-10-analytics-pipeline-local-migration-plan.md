# Analytics Pipeline → Local Migration + Backfill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. This is **ops/infra work** (launchd + CLI orchestration + DB job changes + a Slack-posting backfill), not TDD code — "tests" are live verification gates. Execute **inline** (controller observes live Slack-DM timing, DB, launchd) rather than via parallel subagents.

**Goal:** Restore the daily Slack/Drive/Email analytics pipeline by moving its 5 dead `agent_message`→Docker-pulse-agent stages to local `pulse` CLI + local-pulse-agent invocations (mirroring the 2026-06-07 schedule-briefing migration), then backfill the 2026-05-31→06-10 gap.

**Architecture:** A single dispatcher `scripts/run-analytics-stage.sh <stage>` sets the proven runner-style env (`PATH` incl. `~/.local/bin`, `PYTHONPATH=$LETTA_LOCAL_BACKEND_DIR/tool-deps`, sourced `~/.letta/pa-tools.env`) and runs the right `pulse` command(s) (mechanical stages) or POSTs to the local-runner `:8920` to invoke the local pulse agent `agent-local-d48b128a` (qualitative stages: vibe-check, mentions). One launchd plist per stage at the original ET times (HOME logs — the EX_CONFIG lesson). The `script`-action ingest stages (Bronze/Silver) and the slackbot CSV-capture listener are intact and untouched. After a clean verified run, the 6 Docker `agent_message` jobs are archived.

**Tech Stack:** `pulse` CLI (`~/.local/bin/pulse`, poetry script), launchd, scheduler DB (`scheduler_service`/`scheduler.jobs`+`.actions`), letta-local-runner `:8920`, `scripts/backfill-slack-analytics.sh`, Gitea canonical signals.

**Permission note:** User granted formal permission (2026-06-10) to trigger Slack CSV exports + posts. The backfill posts ~10 days × {channels,members} CSVs to the admin DM (USLACKBOT).

## EXECUTION UPDATE (2026-06-10) — scope reduced after restart
Verification (Task 2) revealed the scheduler-service had stopped firing **all** cron jobs (475 historical execs, 0 since ~05-31) — it lost its calendar-job registrations after a restart. **`docker restart scheduler-service` revived them** (32 jobs re-registered; a cron job fired immediately). Consequences:
- **Bronze/Silver `script` legs self-heal in Docker** (revived scheduler runs them at 7am) — NOT migrated. Verified manually: bronze poll captured the fresh CSVs (06-07, ids 50/51), silver parsed (channels 268 rows / members 202), `pulse snapshot --date 2026-06-07` → `slack_collected:true, slack_messages:231`, compose produced a briefing **with a Slack section**.
- **Export trigger bug fixed:** `trigger_slack_analytics_export` defaulted to Docker host `slack-analytics-mcp-server:8087` (unresolvable from host). Added `SLACK_ANALYTICS_EXPORT_URL=http://127.0.0.1:8097/trigger-export` to `~/.letta/pa-tools.env` (gitignored host env).
- **Remaining migration scope = the `agent_message` legs only** (export/snapshot/vibe/recollect/compose/mentions → local launchd, Tasks 3–4). Tasks 1–2 done. Snapshot reads the **silver table** (not files.list).

---

## Invariants (read first)
- **Stages + original ET schedule + mapping:**
  | Stage | ET cron | Local action |
  |---|---|---|
  | export | `0 2 * * 1-5` | `pulse slack-trigger --analytics-type channels` then `--analytics-type members` |
  | snapshot | `30 2 * * 1-5` | `pulse snapshot` |
  | vibe | `0 3 * * 1-5` | runner→local pulse agent (LLM): write `system/daily_vibe_check_<ET-yday>.md` |
  | recollect | `0 4 * * 1-5` | `pulse snapshot` (re-run, picks up late-arriving data) |
  | compose | `0 6 * * 1-5` | `pulse compose-briefing` |
  | mentions | `*/15 8-18 * * 1-5` | runner→local pulse agent (LLM): rolling 48h @Chad mentions |
- **Critical path:** export(2:00) → Slack DMs CSV → `snapshot`(2:30, reads the file via `files.list`) → `compose`(6:00). The 30-min gaps are the delivery buffer (preserve them).
- **Env every stage needs** (proven 2026-06-10): `PATH=$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin`, `PYTHONPATH=$HOME/.letta/lc-local-backend/tool-deps`, and `set -a; . ~/.letta/pa-tools.env; set +a`.
- **Local pulse agent:** `agent-local-d48b128a-b3a8-4930-a27f-b4127c96fe3a`. Runner invoke: `POST http://127.0.0.1:8920/invoke {agent_id, message, timeout}`.
- **launchd:** StandardOut/ErrorPath MUST be under `~/Library/Logs/` (NOT /Volumes — EX_CONFIG/78). System TZ is ET, so `StartCalendarInterval` Hour/Minute = ET. Weekdays = 5 entries (Weekday 1..5).
- **6 Docker jobs to archive (only after Task 5 verifies the local path):** `dc913a67`(export) `d955e69f`(snapshot) `eafe44e5`(vibe) `dc52c731`(recollect) `111217cc`(compose) `0232024b`(mentions).
- **Untouched (working):** Bronze `script` job + Silver `script` job + slackbot `analytics_csv_capture.py` listener.

---

## Task 1: Dispatcher script `scripts/run-analytics-stage.sh`

**Files:** Create `scripts/run-analytics-stage.sh`

- [ ] **Step 1: Write the dispatcher**

```bash
#!/usr/bin/env bash
# run-analytics-stage.sh — local driver for the daily analytics pipeline.
# Replaces the Docker pulse-agent agent_message scheduler jobs (dead since
# 2026-05-31) with host-local pulse CLI + local-pulse-agent invocations.
# Usage: run-analytics-stage.sh <export|snapshot|vibe|recollect|compose|mentions>
set -uo pipefail

STAGE="${1:?usage: run-analytics-stage.sh <export|snapshot|vibe|recollect|compose|mentions>}"
export HOME="${HOME:-/Users/dorseyhomeserver}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="$HOME/.letta/lc-local-backend/tool-deps"
set -a; . "$HOME/.letta/pa-tools.env" 2>/dev/null; set +a

LOG_DIR="$HOME/Library/Logs/analytics-pipeline"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${STAGE}.log"
ts(){ date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log(){ echo "[$(ts)] $*" | tee -a "$LOG"; }

AGENT="agent-local-d48b128a-b3a8-4930-a27f-b4127c96fe3a"
RUNNER="http://127.0.0.1:8920/invoke"

invoke_agent(){ # $1=message $2=timeout
  python3 - "$AGENT" "$RUNNER" "$1" "$2" <<'PY'
import json,sys,urllib.request
aid,url,msg,to=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4])
req=urllib.request.Request(url,data=json.dumps({"agent_id":aid,"message":msg,"timeout":to}).encode(),
    headers={"Content-Type":"application/json"},method="POST")
r=json.load(urllib.request.urlopen(req,timeout=to+20))
print("runner_status:",r.get("status"),"exit:",r.get("letta_exit"),"dur:",r.get("duration_seconds"))
print((r.get("agent_response") or "")[:400])
PY
}

log "stage=$STAGE start"
rc=0
case "$STAGE" in
  export)
    pulse slack-trigger --analytics-type channels 2>&1 | tee -a "$LOG" || rc=$?
    pulse slack-trigger --analytics-type members  2>&1 | tee -a "$LOG" || rc=$?
    ;;
  snapshot|recollect)
    pulse snapshot 2>&1 | tee -a "$LOG" || rc=$?
    ;;
  compose)
    pulse compose-briefing 2>&1 | tee -a "$LOG" || rc=$?
    ;;
  vibe)
    invoke_agent "Generate the daily Slack vibe check for yesterday (ET) across the top channels. After summarizing each channel, write the per-channel and combined summary to your memfs at system/daily_vibe_check_<YYYY-MM-DD>.md using yesterday's ET date. Then reply DONE." 600 2>&1 | tee -a "$LOG" || rc=$?
    ;;
  mentions)
    invoke_agent "Intra-day mentions refresh (rolling 48h, today+yesterday ET): find @-mentions directed AT Chad in DMs and channels, update your stored mentions view. Reply DONE." 400 2>&1 | tee -a "$LOG" || rc=$?
    ;;
  *) log "unknown stage: $STAGE"; exit 2 ;;
esac
log "stage=$STAGE done rc=$rc"
exit $rc
```

- [ ] **Step 2: chmod +x + smoke-test a no-side-effect stage path (env loads, pulse resolves)**

Run:
```bash
chmod +x /Volumes/main-drive/ai-PA/scripts/run-analytics-stage.sh
# dry env check (compose is read-mostly; if it errors on missing data that's OK — we're testing env/import)
/Volumes/main-drive/ai-PA/scripts/run-analytics-stage.sh compose 2>&1 | tail -15
```
Expected: log shows `stage=compose start`, `pulse compose-briefing` runs (may warn if today's snapshot is stale — fine), `stage=compose done rc=...`. No `pulse: command not found`, no Python ImportError.

- [ ] **Step 3: Commit**
```bash
cd /Volumes/main-drive/ai-PA && git add scripts/run-analytics-stage.sh
git commit -m "feat(analytics): local dispatcher for the analytics pipeline (replaces Docker agent_message jobs)"
```

---

## Task 2: Verify the critical path end-to-end (one clean run)

**Files:** none (live verification; uses the granted Slack-export permission)

- [ ] **Step 1: Trigger a real export + confirm success**
```bash
/Volumes/main-drive/ai-PA/scripts/run-analytics-stage.sh export 2>&1 | tail -20
```
Expected: both `pulse slack-trigger` calls report success ("CSV will be available in Slack shortly"). If a call fails with an auth error, STOP — the Slack admin session needs refresh (slack_auth_state.json).

- [ ] **Step 2: Confirm the export logged success in the container + the CSV reached the DM (ingest)**
```bash
sleep 60
docker logs --since 5m slack-analytics-mcp-server 2>&1 | grep -iE "export succeeded|export failed" | tail
docker exec supabase-db psql -U postgres -d postgres -c \
 "SELECT count(*), max(created_at) FROM analytics_raw.raw_artifacts WHERE created_at > now() - interval '15 min';" 2>&1 | head
```
Expected: at least one "export succeeded"; raw_artifacts count > 0 (slackbot listener captured the CSV → bronze).

- [ ] **Step 2b: If raw_artifacts did NOT increase**, the slackbot file_shared listener may be down. Verify slackbot is running + check its logs:
```bash
docker ps --format '{{.Names}} {{.Status}}' | grep -i slackbot
docker logs --since 5m slackbot 2>&1 | grep -iE "analytics|file_shared|raw_artifacts|csv" | tail
```
Record the finding; the export still succeeded (CSV in DM) even if capture lags.

- [ ] **Step 3: Run snapshot, confirm it reads today's Slack data**
```bash
/Volumes/main-drive/ai-PA/scripts/run-analytics-stage.sh snapshot 2>&1 | tail -20
```
Expected: `pulse snapshot` completes; output mentions Slack metrics (channels/members), not just Drive/Email.

- [ ] **Step 4: Compose + confirm the briefing now has a Slack section**
```bash
/Volumes/main-drive/ai-PA/scripts/run-analytics-stage.sh compose 2>&1 | tail -15
set -a; . ~/.letta/pa-tools.env; set +a
D=$(date +%F)
curl -s -H "Authorization: token $GITEA_MEMFS_TOKEN" \
 "http://127.0.0.1:3030/api/v1/repos/agents/agents-canonical/raw/signals/$D/analytics-morning.md" 2>/dev/null | grep -iE "slack|channel|vibe" | head
```
Expected: the composed briefing references Slack (a Slack section / channel metrics). **This is the decision gate** — if Slack data flows through to the briefing, the local path works.

---

## Task 3: launchd jobs (one per stage, ET times, HOME logs)

**Files:** Create `~/Library/LaunchAgents/com.ai-pa.analytics-<stage>.plist` ×6 + tracked reference copies in `deployment/launchd/`

- [ ] **Step 1: Create the 6 plists + load each**
```bash
mkdir -p ~/Library/Logs/analytics-pipeline /Volumes/main-drive/ai-PA/deployment/launchd
python3 - <<'PY'
import plistlib, os
home=os.path.expanduser("~")
SH="/Volumes/main-drive/ai-PA/scripts/run-analytics-stage.sh"
# stage: (Hour, Minute, weekday_only, extra minutes list for intraday)
stages={
 "export":   (2,0),
 "snapshot": (2,30),
 "vibe":     (3,0),
 "recollect":(4,0),
 "compose":  (6,0),
}
def cal(h,m): return [{"Hour":h,"Minute":m,"Weekday":d} for d in range(1,6)]  # Mon-Fri
for stage,(h,m) in stages.items():
    lbl=f"com.ai-pa.analytics-{stage}"
    d={"Label":lbl,"ProgramArguments":["/bin/bash",SH,stage],
       "WorkingDirectory":"/Volumes/main-drive/ai-PA","RunAtLoad":False,
       "ProcessType":"Background","StartCalendarInterval":cal(h,m),
       "StandardOutPath":f"{home}/Library/Logs/analytics-pipeline/{stage}.stdout.log",
       "StandardErrorPath":f"{home}/Library/Logs/analytics-pipeline/{stage}.stderr.log"}
    for path in (f"{home}/Library/LaunchAgents/{lbl}.plist",
                 f"/Volumes/main-drive/ai-PA/deployment/launchd/{lbl}.plist"):
        plistlib.dump(d, open(path,"wb"))
    print("wrote", lbl)
# mentions: every 15 min, 8-18 ET, Mon-Fri
lbl="com.ai-pa.analytics-mentions"
cal_m=[{"Hour":h,"Minute":mm,"Weekday":d} for h in range(8,19) for mm in (0,15,30,45) for d in range(1,6)]
d={"Label":lbl,"ProgramArguments":["/bin/bash",SH,"mentions"],
   "WorkingDirectory":"/Volumes/main-drive/ai-PA","RunAtLoad":False,"ProcessType":"Background",
   "StartCalendarInterval":cal_m,
   "StandardOutPath":f"{home}/Library/Logs/analytics-pipeline/mentions.stdout.log",
   "StandardErrorPath":f"{home}/Library/Logs/analytics-pipeline/mentions.stderr.log"}
for path in (f"{home}/Library/LaunchAgents/{lbl}.plist",
             f"/Volumes/main-drive/ai-PA/deployment/launchd/{lbl}.plist"):
    plistlib.dump(d, open(path,"wb"))
print("wrote", lbl)
PY
for s in export snapshot vibe recollect compose mentions; do
  launchctl unload ~/Library/LaunchAgents/com.ai-pa.analytics-$s.plist 2>/dev/null
  launchctl load ~/Library/LaunchAgents/com.ai-pa.analytics-$s.plist
done
echo "loaded:"; launchctl list | grep analytics-
```
Expected: 6 jobs listed, last-exit `-` or `0` (NOT 78).

- [ ] **Step 2: kickstart-test the two safe read stages under launchd (confirms env+logpath work via launchd)**
```bash
for s in snapshot compose; do launchctl kickstart -k "gui/$(id -u)/com.ai-pa.analytics-$s"; done
sleep 20
for s in snapshot compose; do
  echo "$s last-exit: $(launchctl list | grep analytics-$s | awk '{print $2}')"
  tail -3 ~/Library/Logs/analytics-pipeline/$s.log
done
```
Expected: exit 0; fresh log lines (proves launchd runs the dispatcher with correct env + HOME logs).

- [ ] **Step 3: Commit the tracked plist copies**
```bash
cd /Volumes/main-drive/ai-PA && git add deployment/launchd/com.ai-pa.analytics-*.plist
git commit -m "feat(analytics): launchd jobs for local analytics pipeline (ET schedule, HOME logs)"
```

---

## Task 4: Archive the dead Docker agent_message jobs

**Files:** none (scheduler DB) — **only after Task 2 gate passed**

- [ ] **Step 1: Archive the 6 jobs so they stop phantom-scheduling**
```bash
docker exec supabase-db psql -U postgres -d scheduler_service -c "
UPDATE scheduler.jobs SET status='archived', updated_at=now()
WHERE job_id IN ('dc913a67-7dd1-475a-a3d2-d7071b5b6618','d955e69f-b8a7-47a8-8b76-299bff179f67',
 'eafe44e5-402a-450a-ac46-5da8d9a1e7f4','dc52c731-df9b-46c8-9152-cbe00af04fed',
 '111217cc-d389-4acf-83e6-1727b2de35b4','0232024b-38d2-479f-8c9c-d3b7444fb768')
  AND status='scheduled';"
```
Expected: `UPDATE 6`.

- [ ] **Step 2: Confirm none remain scheduled**
```bash
docker exec supabase-db psql -U postgres -d scheduler_service -tc "
SELECT count(*) FROM scheduler.jobs j JOIN scheduler.actions a ON a.job_id=j.job_id
WHERE j.status='scheduled' AND a.action_type='agent_message' AND lower(j.title) ~ 'analytic|mention';"
```
Expected: `0`.

---

## Task 5: Backfill 2026-05-31 → 06-10

**Files:** none (uses `scripts/backfill-slack-analytics.sh`; granted Slack-post permission)

- [ ] **Step 1: Run the backfill (posts ~10 days × channels+members to the admin DM)**
```bash
cd /Volumes/main-drive/ai-PA
TRIGGER_URL="http://127.0.0.1:8097/trigger-export" \
  bash scripts/backfill-slack-analytics.sh 2026-05-31 2026-06-10 2>&1 | tail -30
```
Expected: per-day "triggering channels/members" with ok results. Note any days that fail (Slack analytics retention may cap how far back; record the earliest day that succeeds).

- [ ] **Step 2: Confirm backfilled CSVs ingested to bronze**
```bash
sleep 30
docker exec supabase-db psql -U postgres -d postgres -c \
 "SELECT count(*), min(created_at), max(created_at) FROM analytics_raw.raw_artifacts WHERE created_at > now() - interval '30 min';"
```
Expected: count climbed by ~ (#days × 2). If 0, the listener isn't capturing — investigate (Task 2 Step 2b).

- [ ] **Step 3: Re-collect snapshots for the backfilled dates** (so the briefing DB catches up)
```bash
for d in 2026-05-31 2026-06-01 2026-06-02 2026-06-03 2026-06-04 2026-06-05 2026-06-06 2026-06-07 2026-06-08 2026-06-09; do
  echo "== snapshot $d =="; pulse snapshot --date "$d" 2>&1 | tail -2
done
```
(Run with the Task-1 env. Skip weekend dates if snapshot rejects them.) Expected: each completes; analytics DB now has rows for the gap.

---

## Task 6: Docs + memory + final commit

- [ ] **Step 1: Record in the daily-briefing / pipeline docs + memory**
Update `~/.claude/.../memory/` with: analytics pipeline migrated to local (dispatcher + 6 launchd jobs), Docker agent_message jobs archived, backfill done. Update `project_*` analytics memory if present.

- [ ] **Step 2: Final commit**
```bash
cd /Volumes/main-drive/ai-PA && git add -A scripts/ deployment/launchd/ docs/plans/
git commit -m "docs(analytics): pipeline local-migration plan + completion notes"
```

---

## Rollback
- Re-enable Docker jobs: `UPDATE scheduler.jobs SET status='scheduled' WHERE job_id IN (...6 ids...);`
- Disable local jobs: `launchctl unload ~/Library/LaunchAgents/com.ai-pa.analytics-*.plist` + remove the plists.
- The dispatcher script + Bronze/Silver/listener are non-destructive; no data rollback needed.

## Success criteria
- A composed `analytics-morning.md` contains a **Slack section** (Task 2 gate).
- 6 launchd jobs loaded, HOME logs, exit 0 on kickstart (no EX_CONFIG).
- 6 Docker agent_message jobs archived; zero analytics `agent_message` jobs scheduled.
- Backfill ingested for the recoverable date range; gap snapshots re-collected.

---
## STATUS: COMPLETE (2026-06-10)
All tasks done. Local launchd drives export/snapshot/vibe/recollect/compose/mentions; Docker scheduler (restarted) runs bronze/silver; 6 Docker agent_message jobs archived; backfill 05-31→06-10 ingested (slack=True all dates; 06-09 single-day self-fills via cron). End-to-end gate passed (briefing has Slack section).
