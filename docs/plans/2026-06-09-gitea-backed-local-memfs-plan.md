# Gitea-backed Local-Agent memfs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each local-runner agent's per-agent memfs a Gitea-hosted git repo (the hub) so every letta-code instance shares one canonical memory per agent — proven on a low-stakes canary (`docs`) first, with the contended-push behavior characterized before rolling the fleet.

**Architecture:** Gitea is the source of truth; each agent gets `agents/agent-local-<id>`; instances pull-on-start + push-on-write via `LETTA_MEMFS_GIT_URL` env. Durability-critical, so every agent is **backed up → seeded to Gitea → then configured → verified against backup**, never the reverse.

**Tech Stack:** git, Gitea HTTP API (`127.0.0.1:3030`), letta-code (`letta --backend local`), letta-local-runner (launchd `com.ai-pa.letta-local-runner.plist`), the pinned `~/.letta/pa-tools.env` for `GITEA_MEMFS_TOKEN`.

**Design:** `docs/plans/2026-06-09-gitea-backed-local-memfs-design.md` (Approach A). Conversation-history/search is OUT of scope (notes only in the design).

---

## Invariants (read before any task)
- **Canary agent:** `docs` = `agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a`.
- **Working copy:** `~/.letta/lc-local-backend/memfs/<agent-id>/memory` — real git repo, branch `main`, currently NO remote.
- **Gitea:** base `http://127.0.0.1:3030` (NEVER `localhost` — IPv6 trap; Gitea is IPv4-only). Token: `GITEA_MEMFS_TOKEN` in `~/.letta/pa-tools.env`. Org `agents`.
- **Order is safety:** backup → create empty repo → push full history → configure env → verify. Configuring before seeding can let letta-code's startup pull from an empty remote wipe memory.
- **Runner invocation:** `letta-local-runner/src/letta_local_runner/invoker.py` forks `letta --backend local --agent <id> --new -p <msg>` with `env=env`. memfs-git is enabled by **env** (`LETTA_MEMFS_GIT_URL`, `LETTA_MEMFS_LOCAL=1`); `--memfs-startup blocking` is added to the invoker cmd ONLY if env-alone doesn't pull-on-start (Task 6).
- **Canary stays runner-only** until contended-push is characterized (do not also let pa-web run it mid-migration).
- Set env for ad-hoc commands: `cd /Volumes/main-drive/ai-PA && set -a; . ~/.letta/pa-tools.env; set +a` (gives `GITEA_MEMFS_TOKEN`, `GITEA_BASE_URL=http://127.0.0.1:3030`).

---

## Phase 0 — Pre-flight & backup (no live config changes)

### Task 1: Pre-flight checks
**Files:** none (read-only verification)

- [ ] **Step 1: Confirm Gitea reachable + token can create org repos**

Run:
```bash
cd /Volumes/main-drive/ai-PA && set -a; . ~/.letta/pa-tools.env; set +a
curl -s -o /dev/null -w "gitea version -> %{http_code}\n" "http://127.0.0.1:3030/api/v1/version"
curl -s -o /dev/null -w "orgs/agents -> %{http_code}\n" -H "Authorization: token $GITEA_MEMFS_TOKEN" "http://127.0.0.1:3030/api/v1/orgs/agents"
```
Expected: both `200`.

- [ ] **Step 2: Confirm the canary working copy exists, is git, branch main, no remote**

Run:
```bash
MEM=~/.letta/lc-local-backend/memfs/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/memory
git -C "$MEM" rev-parse --abbrev-ref HEAD; git -C "$MEM" remote -v; git -C "$MEM" log --oneline -3
```
Expected: prints `main`, **no remote lines**, and a few commits. (If a remote already exists, STOP — re-evaluate; the agent may already be hub-backed.)

- [ ] **Step 3: Confirm the canary Gitea repo does NOT already exist**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: token $GITEA_MEMFS_TOKEN" \
  "http://127.0.0.1:3030/api/v1/repos/agents/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a"
```
Expected: `404` (does not exist yet). If `200`, STOP and reconcile.

- [ ] **Step 4: Confirm pa-web is NOT currently running the canary agent (keep it runner-only)**

Run:
```bash
docker exec pa-web-ui sh -c 'ls /app/.letta/lc-local-backend/memfs/ 2>/dev/null | grep 3898b33a' 2>/dev/null && echo "PA-WEB HAS CANARY — keep pa-web off it during canary" || echo "pa-web does not have the canary (good)"
```
Expected: "pa-web does not have the canary." If pa-web has it, note it and ensure pa-web does not invoke `docs` until Phase 2 completes (coordinate manually; do not configure pa-web for the canary yet).

- [ ] **Step 5: Record the runner baseline (for rollback sanity)**

Run:
```bash
pgrep -f letta_local_runner | head -1
launchctl list | grep letta-local-runner
```
Note the PID + last-exit. No commit (read-only phase).

### Task 2: Back up the canary working copy
**Files:** Create backup tarball under `~/.letta/memfs-backups/`

- [ ] **Step 1: Create a timestamped backup + record the seed identity**

Run:
```bash
MEM=~/.letta/lc-local-backend/memfs/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a
mkdir -p ~/.letta/memfs-backups
TS=$(cd "$MEM" && git -C memory rev-parse --short HEAD 2>/dev/null || echo nohead)
tar -czf ~/.letta/memfs-backups/docs-3898b33a-pre-gitea-$TS.tgz -C "$MEM" memory
echo "backup: ~/.letta/memfs-backups/docs-3898b33a-pre-gitea-$TS.tgz (HEAD=$TS)"
git -C "$MEM/memory" rev-parse HEAD > /tmp/canary_seed_head.txt
( cd "$MEM/memory" && git ls-files | sort ) > /tmp/canary_seed_files.txt
wc -l /tmp/canary_seed_files.txt
```
Expected: a `.tgz` exists; `/tmp/canary_seed_head.txt` holds the full HEAD SHA; `/tmp/canary_seed_files.txt` lists the tracked files (the "must-not-lose" manifest).

- [ ] **Step 2: Verify the backup is restorable (extract to a temp dir, diff)**

Run:
```bash
T=$(mktemp -d); tar -xzf ~/.letta/memfs-backups/docs-3898b33a-pre-gitea-*.tgz -C "$T"
diff -rq "$T/memory/system" ~/.letta/lc-local-backend/memfs/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/memory/system && echo "BACKUP OK (system/ identical)"; rm -rf "$T"
```
Expected: "BACKUP OK (system/ identical)".

---

## Phase 1 — Seed the hub (canary)

### Task 3: Create the empty Gitea repo for the canary
**Files:** none (Gitea API)

- [ ] **Step 1: Create `agents/agent-local-3898b33a-...` (no auto-init, private)**

Run:
```bash
cd /Volumes/main-drive/ai-PA && set -a; . ~/.letta/pa-tools.env; set +a
curl -s -X POST -H "Authorization: token $GITEA_MEMFS_TOKEN" -H "Content-Type: application/json" \
  "http://127.0.0.1:3030/api/v1/orgs/agents/repos" \
  -d '{"name":"agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a","private":true,"auto_init":false}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('created:',d.get('full_name') or d)"
```
Expected: `created: agents/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a`.

- [ ] **Step 2: Verify it exists and is empty**

Run:
```bash
curl -s -o /dev/null -w "repo -> %{http_code}\n" -H "Authorization: token $GITEA_MEMFS_TOKEN" \
  "http://127.0.0.1:3030/api/v1/repos/agents/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a"
```
Expected: `200`.

### Task 4: Push the existing working-copy history to Gitea (SEED)
**Files:** adds a git remote to the canary working copy (local git config only)

- [ ] **Step 1: Derive the authenticated push URL (mirror pa-web's credential form)**

Run:
```bash
# pa-web's LETTA_MEMFS_GIT_URL shows the user:token form; reuse that user with our token + 127.0.0.1.
PAWEB_URL=$(docker exec pa-web-ui sh -c 'echo $LETTA_MEMFS_GIT_URL')
GUSER=$(echo "$PAWEB_URL" | sed -E 's#https?://([^:]+):.*#\1#')   # e.g. pa-admin
echo "git user = $GUSER"
set -a; . ~/.letta/pa-tools.env; set +a
PUSH_URL="http://${GUSER}:${GITEA_MEMFS_TOKEN}@127.0.0.1:3030/agents/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a.git"
echo "$PUSH_URL" | sed -E 's#:[^:@]+@#:<redacted>@#'
```
Expected: prints a git user (e.g. `pa-admin`) and a redacted push URL. Keep `$PUSH_URL` for the next step.

- [ ] **Step 2: Add the remote and push full history (branch main)**

Run:
```bash
MEM=~/.letta/lc-local-backend/memfs/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/memory
git -C "$MEM" remote add gitea "$PUSH_URL"
git -C "$MEM" push -u gitea main
```
Expected: push succeeds (`* [new branch] main -> main`), no errors.

- [ ] **Step 3: Verify Gitea now holds the SAME head + file manifest as the working copy (no loss)**

Run:
```bash
set -a; . ~/.letta/pa-tools.env; set +a
REMOTE_HEAD=$(curl -s -H "Authorization: token $GITEA_MEMFS_TOKEN" \
  "http://127.0.0.1:3030/api/v1/repos/agents/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/branches/main" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['commit']['id'])")
echo "gitea head:  $REMOTE_HEAD"
echo "seed head:   $(cat /tmp/canary_seed_head.txt)"
[ "$REMOTE_HEAD" = "$(cat /tmp/canary_seed_head.txt)" ] && echo "HEAD MATCH ✅" || echo "HEAD MISMATCH ❌ STOP"
# file manifest match
curl -s -H "Authorization: token $GITEA_MEMFS_TOKEN" \
  "http://127.0.0.1:3030/api/v1/repos/agents/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/git/trees/main?recursive=true" \
  | python3 -c "import sys,json;print('\n'.join(sorted(e['path'] for e in json.load(sys.stdin).get('tree',[]) if e['type']=='blob')))" > /tmp/canary_gitea_files.txt
diff /tmp/canary_seed_files.txt /tmp/canary_gitea_files.txt && echo "FILE MANIFEST MATCH ✅" || echo "FILE MANIFEST DIFF ❌ STOP"
```
Expected: `HEAD MATCH ✅` and `FILE MANIFEST MATCH ✅`. If either fails, STOP — do not proceed to configure.

---

## Phase 2 — Point the runner at the hub (canary) + verify

### Task 5: Add memfs-git env to the runner plist + reload
**Files:** Modify `~/Library/LaunchAgents/com.ai-pa.letta-local-runner.plist` (backup first)

- [ ] **Step 1: Back up the plist**

Run:
```bash
PLIST=~/Library/LaunchAgents/com.ai-pa.letta-local-runner.plist
cp "$PLIST" "$PLIST.bak.$(date +%s)" && echo "plist backed up"
```

- [ ] **Step 2: Add `LETTA_MEMFS_GIT_URL` (templated, 127.0.0.1) + `LETTA_MEMFS_LOCAL=1`**

Run (uses the same git user derived in Task 4 Step 1):
```bash
PLIST=~/Library/LaunchAgents/com.ai-pa.letta-local-runner.plist
PAWEB_URL=$(docker exec pa-web-ui sh -c 'echo $LETTA_MEMFS_GIT_URL'); GUSER=$(echo "$PAWEB_URL" | sed -E 's#https?://([^:]+):.*#\1#')
set -a; . ~/.letta/pa-tools.env; set +a
python3 - "$PLIST" "$GUSER" "$GITEA_MEMFS_TOKEN" <<'PY'
import plistlib,sys
plist,guser,tok=sys.argv[1],sys.argv[2],sys.argv[3]
d=plistlib.load(open(plist,'rb')); ev=d.setdefault('EnvironmentVariables',{})
ev['LETTA_MEMFS_LOCAL']='1'
ev['LETTA_MEMFS_GIT_URL']=f'http://{guser}:{tok}@127.0.0.1:3030/agents/{{agentId}}.git'
plistlib.dump(d,open(plist,'wb'))
print('LETTA_MEMFS_LOCAL=',ev['LETTA_MEMFS_LOCAL'])
print('LETTA_MEMFS_GIT_URL set (host 127.0.0.1, templated {agentId})')
PY
```
Expected: confirms both env vars set. (The `{agentId}` literal stays — letta-code substitutes it per agent.)

- [ ] **Step 3: Reload the runner (do between cron windows)**

Run:
```bash
PLIST=~/Library/LaunchAgents/com.ai-pa.letta-local-runner.plist
launchctl unload "$PLIST"; sleep 2; launchctl load "$PLIST"; sleep 3
curl -s -o /dev/null -w "runner :8920 -> %{http_code}\n" http://127.0.0.1:8920/health
ps eww -p "$(pgrep -f letta_local_runner|head -1)" | tr ' ' '\n' | grep -E "^LETTA_MEMFS_(LOCAL|GIT_URL)=" | sed -E 's/(GIT_URL=http://[^:]+:)[^@]+@/\1<redacted>@/'
```
Expected: runner health `200`; the two `LETTA_MEMFS_*` vars present in the live process.

### Task 6: Verify the canary git-backs end-to-end (and add `--memfs-startup` only if needed)
**Files:** possibly Modify `letta-local-runner/src/letta_local_runner/invoker.py` (conditional)

- [ ] **Step 1: Invoke the canary via the runner; confirm it reads memfs intact**

Run:
```bash
python3 -c "
import json,urllib.request
p={'agent_id':'agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a',
   'message':'Reply with the literal text OK-CANARY and nothing else.','timeout':180}
r=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8920/invoke',
  data=json.dumps(p).encode(),headers={'Content-Type':'application/json'},method='POST'),timeout=200))
print('runner_status:',r.get('status'),'| resp:',(r.get('agent_response') or '')[:120])
"
```
Expected: `runner_status: success`. (Confirms the agent runs under the new env without breaking.)

- [ ] **Step 2: Confirm a memfs WRITE round-trips to Gitea (push-on-write works)**

Have the agent write a tiny memory note, then check Gitea advanced:
```bash
set -a; . ~/.letta/pa-tools.env; set +a
BEFORE=$(curl -s -H "Authorization: token $GITEA_MEMFS_TOKEN" "http://127.0.0.1:3030/api/v1/repos/agents/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/branches/main" | python3 -c "import sys,json;print(json.load(sys.stdin)['commit']['id'])")
python3 -c "
import json,urllib.request
p={'agent_id':'agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a',
   'message':'Append one line to a scratch note in your memory: \"gitea-backing canary test $(date)\". Use your memory tools. Then reply DONE.','timeout':180}
r=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8920/invoke',data=json.dumps(p).encode(),headers={'Content-Type':'application/json'},method='POST'),timeout=200))
print('status:',r.get('status'))
"
sleep 3
AFTER=$(curl -s -H "Authorization: token $GITEA_MEMFS_TOKEN" "http://127.0.0.1:3030/api/v1/repos/agents/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/branches/main" | python3 -c "import sys,json;print(json.load(sys.stdin)['commit']['id'])")
echo "before=$BEFORE after=$AFTER"; [ "$BEFORE" != "$AFTER" ] && echo "PUSH-ON-WRITE ✅ (gitea head advanced)" || echo "NO PUSH — env may not enable push; investigate (see Step 4)"
```
Expected: `PUSH-ON-WRITE ✅`. If "NO PUSH", go to Step 4.

- [ ] **Step 3: Verify-against-backup (no memory loss)**

Run:
```bash
MEM=~/.letta/lc-local-backend/memfs/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/memory
( cd "$MEM" && git ls-files | sort ) > /tmp/canary_now_files.txt
comm -23 /tmp/canary_seed_files.txt /tmp/canary_now_files.txt > /tmp/canary_lost.txt
[ -s /tmp/canary_lost.txt ] && { echo "FILES LOST ❌:"; cat /tmp/canary_lost.txt; } || echo "NO FILES LOST ✅ (all seed files still present)"
```
Expected: `NO FILES LOST ✅` (new files from the test write are fine; the check is that nothing from the seed disappeared).

- [ ] **Step 4 (conditional): If pull-on-start / push isn't happening with env alone, add `--memfs-startup blocking` to the invoker**

Only if Step 2 showed no push, or you observe the agent not pulling remote changes. Modify the cmd in `letta-local-runner/src/letta_local_runner/invoker.py` (the `cmd = [ self.settings.letta_bin, "--backend", ... "--agent", ... ]` list ~line 110) to append `"--memfs", "--memfs-startup", "blocking"`:
```python
        cmd = [
            self.settings.letta_bin,
            "--backend", "local",
            "--agent", req.agent_id,
            "--memfs",
            "--memfs-startup", "blocking",
            "--new",
            "-p", req.message,
        ]
```
Then `launchctl unload/load` the runner and re-run Step 2. Commit if changed:
```bash
git add letta-local-runner/src/letta_local_runner/invoker.py
git commit -m "feat(runner): pass --memfs-startup blocking so local agents pull-on-start from Gitea"
```

- [ ] **Step 5: Commit the design/plan progress note**

```bash
cd /Volumes/main-drive/ai-PA
git commit --allow-empty -m "chore(memfs): canary docs agent migrated to Gitea-backed memfs (seed+configure verified)"
```

---

## Phase 3 — Characterize contended-push (the decision gate; canary only)

### Task 7: Provoke and observe a concurrent-write conflict
**Files:** scratch clone under `/tmp`; findings appended to the design doc

- [ ] **Step 1: Make a second independent clone of the canary repo (simulates a 2nd instance)**

Run:
```bash
set -a; . ~/.letta/pa-tools.env; set +a
PAWEB_URL=$(docker exec pa-web-ui sh -c 'echo $LETTA_MEMFS_GIT_URL'); GUSER=$(echo "$PAWEB_URL" | sed -E 's#https?://([^:]+):.*#\1#')
URL="http://${GUSER}:${GITEA_MEMFS_TOKEN}@127.0.0.1:3030/agents/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a.git"
rm -rf /tmp/canary-clone2 && git clone "$URL" /tmp/canary-clone2 && echo "clone2 ready"
```
Expected: clone succeeds.

- [ ] **Step 2: Diverge BOTH copies on the SAME file, push clone2 first**

Run:
```bash
MEM=~/.letta/lc-local-backend/memfs/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/memory
F="digest/contention-probe.md"   # a non-system, low-stakes file
mkdir -p "$MEM/digest" /tmp/canary-clone2/digest
echo "edit from RUNNER working copy $(date)" >> "$MEM/$F"; git -C "$MEM" add "$F"; git -C "$MEM" -c user.email=t@t -c user.name=t commit -q -m "runner edit"
echo "edit from CLONE2 $(date)"            >> "/tmp/canary-clone2/$F"; git -C /tmp/canary-clone2 add "$F"; git -C /tmp/canary-clone2 -c user.email=t@t -c user.name=t commit -q -m "clone2 edit"
git -C /tmp/canary-clone2 push origin main && echo "clone2 pushed (gitea now ahead of runner working copy)"
```
Expected: clone2 push succeeds; the runner working copy is now behind + divergent on the same file.

- [ ] **Step 3: Observe how a naive push from the runner copy behaves (raw git)**

Run:
```bash
MEM=~/.letta/lc-local-backend/memfs/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/memory
git -C "$MEM" push gitea main 2>&1 | tail -5
```
Expected: a **non-fast-forward rejection** (`! [rejected] main -> main (fetch first)`). Record this — it confirms git protects against blind overwrite (good).

- [ ] **Step 4: Observe how letta-code reacts on the NEXT run with the remote ahead (THE key observation)**

Run:
```bash
python3 -c "
import json,urllib.request
p={'agent_id':'agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a','message':'Reply OK.','timeout':180}
r=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8920/invoke',data=json.dumps(p).encode(),headers={'Content-Type':'application/json'},method='POST'),timeout=200))
print('runner_status:',r.get('status'),'| resp:',(r.get('agent_response') or '')[:80])
"
# inspect what letta-code did to the working copy + remote
MEM=~/.letta/lc-local-backend/memfs/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/memory
git -C "$MEM" log --oneline -6
git -C "$MEM" status -s
echo "--- both edits still present? (graceful merge) or one lost? (force/clobber) ---"
git -C "$MEM" show HEAD:digest/contention-probe.md 2>/dev/null | tail -4 || echo "(file resolved differently)"
```
Record the verdict precisely: did letta-code (a) **pull/rebase/merge** the remote edit and keep BOTH (graceful), (b) **fail/refuse** to run (blocked), or (c) **force-push / overwrite**, losing the remote edit (lossy)?

- [ ] **Step 5: Clean up the probe + restore canary cleanliness**

Run:
```bash
MEM=~/.letta/lc-local-backend/memfs/agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a/memory
git -C "$MEM" rm -q --ignore-unmatch digest/contention-probe.md 2>/dev/null; rm -f "$MEM/digest/contention-probe.md"
git -C "$MEM" -c user.email=t@t -c user.name=t commit -q -m "remove contention probe" 2>/dev/null || true
git -C "$MEM" pull --rebase gitea main 2>&1 | tail -3; git -C "$MEM" push gitea main 2>&1 | tail -3
rm -rf /tmp/canary-clone2
echo "probe cleaned; verify no real memory lost:"
( cd "$MEM" && git ls-files | sort ) > /tmp/canary_post_probe.txt
comm -23 /tmp/canary_seed_files.txt /tmp/canary_post_probe.txt && echo "(any lines above = seed files now missing — restore from backup if so)"
```
Expected: probe file gone; **no seed files missing**. If any real seed file is missing, restore from the Task 2 backup immediately.

### Task 8: Decision gate — record the verdict and the coordination decision
**Files:** Modify `docs/plans/2026-06-09-gitea-backed-local-memfs-design.md` (append a "Canary findings" section)

- [ ] **Step 1: Write the verdict + decision into the design doc**

Append a section recording: (a) git's non-fast-forward behavior (Step 3 result), (b) letta-code's contended-run behavior (Step 4 verdict: graceful / blocked / lossy), and (c) the resulting decision:
- **graceful (merge/rebase/retry):** defer coordination — proceed to Phase 4 as-is.
- **blocked (refuses):** acceptable for now (no data loss) — proceed, note the failure mode.
- **lossy (force/overwrite):** DO NOT proceed to multi-instance; first build the sync wrapper (pull-rebase before / push-retry after) or a per-agent lock, then re-test, then Phase 4.

```bash
cd /Volumes/main-drive/ai-PA
git add docs/plans/2026-06-09-gitea-backed-local-memfs-design.md
git commit -m "docs(memfs): canary contended-push findings + coordination decision"
```

- [ ] **Step 2: STOP for human checkpoint.** Phase 4 (fleet rollout) is gated on this verdict. Surface the finding and the recommended decision to Chad before rolling the rest.

---

## Phase 4 — Roll out the remaining agents (GATED on Phase 3 verdict)

> Only after Task 8's verdict is "graceful" or "blocked" (or after the required coordination layer is in place for "lossy"). Run the **per-agent procedure** below for each, **low→high stakes**, MC LAST. Verify each against its own backup before moving on.

**Agent order:** `calendar`=`agent-local-cd5ed5cd-44d5-4e32-b202-3d8dfcb5505c`, `email`=`agent-local-93241bd6-ce9c-4ea6-89ca-318a6d873b0f`, `tasks`=`agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4`, `pulse`=`agent-local-d48b128a-b3a8-4930-a27f-b4127c96fe3a`, `mc`=`agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d`.

### Task 9: Per-agent migration procedure (repeat for each agent above)
**Files:** backup tarball per agent; git remote per working copy; Gitea repo per agent

For a given `AID` (full agent id), run exactly:

- [ ] **Step 1: Backup + manifest**
```bash
AID=<full-agent-id>
MEM=~/.letta/lc-local-backend/memfs/$AID/memory
mkdir -p ~/.letta/memfs-backups
tar -czf ~/.letta/memfs-backups/$AID-pre-gitea-$(git -C "$MEM" rev-parse --short HEAD).tgz -C "$(dirname "$MEM")" memory
( cd "$MEM" && git ls-files | sort ) > /tmp/seed_$AID.txt
git -C "$MEM" rev-parse HEAD > /tmp/head_$AID.txt
```

- [ ] **Step 2: Create empty Gitea repo + seed (push full history) + verify head/manifest match**
```bash
set -a; . ~/.letta/pa-tools.env; set +a
curl -s -X POST -H "Authorization: token $GITEA_MEMFS_TOKEN" -H "Content-Type: application/json" \
  "http://127.0.0.1:3030/api/v1/orgs/agents/repos" -d "{\"name\":\"$AID\",\"private\":true,\"auto_init\":false}" >/dev/null
PAWEB_URL=$(docker exec pa-web-ui sh -c 'echo $LETTA_MEMFS_GIT_URL'); GUSER=$(echo "$PAWEB_URL" | sed -E 's#https?://([^:]+):.*#\1#')
git -C "$MEM" remote add gitea "http://${GUSER}:${GITEA_MEMFS_TOKEN}@127.0.0.1:3030/agents/$AID.git"
git -C "$MEM" push -u gitea main
REMOTE_HEAD=$(curl -s -H "Authorization: token $GITEA_MEMFS_TOKEN" "http://127.0.0.1:3030/api/v1/repos/agents/$AID/branches/main" | python3 -c "import sys,json;print(json.load(sys.stdin)['commit']['id'])")
[ "$REMOTE_HEAD" = "$(cat /tmp/head_$AID.txt)" ] && echo "HEAD MATCH ✅" || echo "MISMATCH ❌ STOP"
```
Expected: `HEAD MATCH ✅`. (The runner env from Task 5 already templates `{agentId}`, so no per-agent env change is needed — the next runner invocation of this agent uses its repo.)

- [ ] **Step 3: Verify the agent runs + write round-trips + no seed files lost**
```bash
python3 -c "
import json,urllib.request
p={'agent_id':'$AID','message':'Reply OK.','timeout':180}
r=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8920/invoke',data=json.dumps(p).encode(),headers={'Content-Type':'application/json'},method='POST'),timeout=200))
print('status:',r.get('status'))
"
MEM=~/.letta/lc-local-backend/memfs/$AID/memory
( cd "$MEM" && git ls-files | sort ) > /tmp/now_$AID.txt
comm -23 /tmp/seed_$AID.txt /tmp/now_$AID.txt > /tmp/lost_$AID.txt
[ -s /tmp/lost_$AID.txt ] && { echo "FILES LOST ❌"; cat /tmp/lost_$AID.txt; } || echo "NO FILES LOST ✅"
```
Expected: `status: success` and `NO FILES LOST ✅`. If files lost → restore from this agent's backup, STOP, reassess.

- [ ] **Step 4: Commit progress note (after each agent)**
```bash
cd /Volumes/main-drive/ai-PA
git commit --allow-empty -m "chore(memfs): $AID migrated to Gitea-backed memfs (verified)"
```

### Task 10: Final verification + enable pa-web sharing (optional, gated)
**Files:** none (verification); pa-web already configured with `{agentId}` template

- [ ] **Step 1: Confirm every migrated agent has a Gitea repo + a working remote**
```bash
set -a; . ~/.letta/pa-tools.env; set +a
for AID in agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a agent-local-cd5ed5cd-44d5-4e32-b202-3d8dfcb5505c agent-local-93241bd6-ce9c-4ea6-89ca-318a6d873b0f agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4 agent-local-d48b128a-b3a8-4930-a27f-b4127c96fe3a agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token $GITEA_MEMFS_TOKEN" "http://127.0.0.1:3030/api/v1/repos/agents/$AID")
  echo "  $AID -> repo HTTP $code; remote: $(git -C ~/.letta/lc-local-backend/memfs/$AID/memory remote get-url gitea 2>/dev/null | sed -E 's#:[^:@]+@#:<redacted>@#')"
done
```
Expected: all `200` with a `gitea` remote.

- [ ] **Step 2: (Only when ready for multi-instance) confirm pa-web shares the same repos**

pa-web is already configured with `LETTA_MEMFS_GIT_URL={agentId}` (gitea:3000). Once you want pa-web to co-run an agent, verify it pulls the SAME repo (its first run clones from Gitea, not a fresh empty repo). Test on the canary only first; watch for the contended-push behavior characterized in Phase 3. This step is the entry point to true multi-instance and is gated on the Phase 3 verdict + your go-ahead.

---

## Rollback (per agent, any time)
```bash
AID=<full-agent-id>; MEM=~/.letta/lc-local-backend/memfs/$AID/memory
# 1. stop git-backing: remove the remote (and, if it was the only reason, revert the plist env via its .bak)
git -C "$MEM" remote remove gitea
# 2. if memory looks wrong, restore the working copy from backup:
T=$(mktemp -d); tar -xzf ~/.letta/memfs-backups/$AID-pre-gitea-*.tgz -C "$T"
rm -rf "$MEM"; mv "$T/memory" "$MEM"
# 3. reload runner if the plist was changed back:
launchctl unload ~/Library/LaunchAgents/com.ai-pa.letta-local-runner.plist; launchctl load ~/Library/LaunchAgents/com.ai-pa.letta-local-runner.plist
```
The Gitea repo can remain (harmless) or be deleted via `DELETE /api/v1/repos/agents/$AID`. To fully revert the env change, restore the plist from its `.bak.<ts>` (removes `LETTA_MEMFS_*`).

---

## Self-review notes (coverage vs design)
- Hub-as-source-of-truth + per-agent repo `agents/agent-local-<id>` → Tasks 3, 9.
- Seed-then-configure ORDER + backup + verify-against-backup → Tasks 2, 4, 5, 6 (and 9).
- letta-code env mechanism + conditional `--memfs-startup` → Tasks 5, 6.
- 127.0.0.1 addressing (IPv6 trap) → all Gitea/remote URLs.
- Local agents bypass relay → no relay tasks (env-pull only); not added.
- Contended-push characterization as the gate → Tasks 7, 8 (Phase 4 gated).
- Canary = docs, runner-only until characterized → Task 1 Step 4, Phase 3.
- Rollback per agent → Rollback section + per-task backups.
- pa-web multi-instance entry gated → Task 10 Step 2.
- OUT of scope (conversation history/search) → not in plan (design notes only). ✅
