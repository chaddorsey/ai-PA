---
date: 2026-06-19
status: RUNBOOK — coordinated laptop↔server steps to demonstrate the 5 Phase-6 acceptance checks.
parent: docs/plans/2026-06-19-mc-offline-travel-mode-plan.md
note: |
  Laptop side is driven by the laptop agent; SERVER side (this doc) is for the
  home server agent. Hand the server agent the [SERVER] blocks. Steps are
  ordered; ⏸ marks a handoff (wait for the other side). Decision in effect:
  Checks 2 & 3 are demonstrated transport-layer (the laptop produces the memory
  edit + envelope exactly as MC's tools would; the sync/drainer/fold machinery
  carries them). Local model: Ollama qwen2.5:7b-instruct. One MC identity
  (agent-local-8474bbbd…). git is the only transport. Do NOT disrupt the other
  7 fleet agents, the guardian, or the roaming tmux sessions.
---

# MC offline/travel-mode — Phase-6 acceptance runbook

## Constants
- MC agent id: `agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d`
- Canonical MC conversation dir (server): `~/.letta/lc-local-backend/conversations/ZGVmYXVsdDphZ2VudC1sb2NhbC04NDc0YmJiZC05NWZjLTQyZjctYjU4Ni1lYjBjZjk0YTVhNWQ`
  (base64 = `default:agent-local-8474bbbd…`, i.e. `--conversation default`)
- Gitea (server, loopback): `http://<token>@127.0.0.1:3030`; token in `/Volumes/main-drive/ai-PA/.env` as `GITEA_MEMFS_TOKEN`
- push-receiver: `http://localhost:8099/push` (loopback)
- memfs working tree (server, the LIVE MC memory): `~/.letta/lc-local-backend/memfs/<MC>/memory` (branch `main`, remote `gitea`)
- Schema baseline already captured (server `/tmp/pa-schema-baseline.txt`, sha `ee14a94e61e8ad579c0ba6e30ae9be209ccf7e0ef19df4c28fc8dbbbfe5dccb5`)

Bus layout (both ends use it): `Outbox(base_dir=<offline-bus>/outbox)` writes envelopes to
`<offline-bus>/outbox/outbox/<id>.json` and dispatched markers to `<offline-bus>/outbox/dispatched/<id>` —
both inside the `mc-offline-outbox` repo clone so they git-sync. Results go to `<offline-bus>/inbox/<reply_to>.json`.

---

## Part A — Check 3 (Command durability). No quiesce needed.

### [SERVER A1] Apply the drainer inbox-writeback patch + clone the bus
The server repo has the base drainer (commit 08c04fbb); this adds the result→inbox loop.
```bash
cd /Volumes/main-drive/ai-PA
git apply docs/plans/2026-06-19-drainer-inbox-writeback.patch   # patch is in the repo
grep -q _write_inbox_result letta/offline/drainer.py && echo "patch applied"

TOKEN=$(grep '^GITEA_MEMFS_TOKEN=' /Volumes/main-drive/ai-PA/.env | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
mkdir -p ~/.letta/offline-bus
git clone "http://${TOKEN}@127.0.0.1:3030/agents/mc-offline-outbox.git" ~/.letta/offline-bus/outbox
git clone "http://${TOKEN}@127.0.0.1:3030/agents/mc-offline-inbox.git"  ~/.letta/offline-bus/inbox
```
Also locate the push-receiver log (for the “push count = 1” evidence) — wherever
`run-letta-push-receiver.sh` / its launchd plist sends stdout (it logs `PUSH agent=… source_ref=…`).
⏸ **Tell the laptop A1 is done.**

### [LAPTOP A2] append envelope + simulate ≥2 drops + reconnect + push  *(laptop agent does this)*

### [SERVER A3] drain exactly once, push results, prove idempotency
```bash
cd /Volumes/main-drive/ai-PA/letta/offline
git -C ~/.letta/offline-bus/outbox pull
PA_OFFLINE_INBOX_DIR="$HOME/.letta/offline-bus/inbox" PA_PUSH_RECEIVER_URL=http://localhost:8099/push \
  python3 -c "import sys; sys.path.insert(0,'.'); from outbox import Outbox; from drainer import drain_default; print(drain_default(Outbox('$HOME/.letta/offline-bus/outbox')))"
# expect: [{'id': '<id>', 'routed': 'push'}]
git -C ~/.letta/offline-bus/outbox add -A && git -C ~/.letta/offline-bus/outbox commit -m "drainer: dispatched" && git -C ~/.letta/offline-bus/outbox push
git -C ~/.letta/offline-bus/inbox  add -A && git -C ~/.letta/offline-bus/inbox  commit -m "drainer: result"     && git -C ~/.letta/offline-bus/inbox  push

# idempotency: replay → expect []  (dispatched markers suppress re-dispatch)
PA_OFFLINE_INBOX_DIR="$HOME/.letta/offline-bus/inbox" \
  python3 -c "import sys; sys.path.insert(0,'.'); from outbox import Outbox; from drainer import drain_default; print(drain_default(Outbox('$HOME/.letta/offline-bus/outbox')))"

# EVIDENCE (Check 3): push count == 1
grep -c "source_ref=cmd-001" <push-receiver-log>      # → 1
```
⏸ **Tell the laptop A3 is done** (laptop pulls inbox → shows `cmd-001.json`).

Note: this uses a non-`task.*` verb → routes to push-receiver only; `task_queue` is untouched
(keeps Check 5 clean). If you ever drain a `task.*` verb from the host, set
`PA_WEB_POSTGRES_URL=postgresql://postgres:<pw>@localhost:5433/postgres` (host can't resolve `supabase-db`).

---

## Part B — Checks 1 (Continuity), 2 (Memory), 4 (Automation). The quiesce window (§9).

### [SERVER B1] enter the window — pause ONLY mc, publish the conversation
```bash
# Pause ONLY the mc conversational session (single live writer). Leave the other 7
# agent-supervise sessions + guardian + automation RUNNING (that running automation
# during the window IS the Check 4 evidence). Use your agent-supervise stop for 'mc' only.

TOKEN=$(grep '^GITEA_MEMFS_TOKEN=' /Volumes/main-drive/ai-PA/.env | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
CONV=~/.letta/lc-local-backend/conversations/ZGVmYXVsdDphZ2VudC1sb2NhbC04NDc0YmJiZC05NWZjLTQyZjctYjU4Ni1lYjBjZjk0YTVhNWQ
cd "$CONV"
git init -q && git add -A && git commit -q -m "conversation snapshot for offline sync"
git remote add origin "http://${TOKEN}@127.0.0.1:3030/agents/mc-offline-conversation.git"
git push -u origin HEAD:main
echo "published; tip $(git rev-parse --short HEAD)"
```
⏸ **Tell the laptop B1 is done** (laptop clones the conversation, holds an offline exchange,
makes the preference memory edit on `travel/laptop`, runs sync-runner to fold memory→main + conversation tail, then pings you).

### [SERVER B2] reconcile + evidence, then leave the window
```bash
MEM=~/.letta/lc-local-backend/memfs/agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d/memory
CONV=~/.letta/lc-local-backend/conversations/ZGVmYXVsdDphZ2VudC1sb2NhbC04NDc0YmJiZC05NWZjLTQyZjctYjU4Ni1lYjBjZjk0YTVhNWQ

# Check 2 (Memory): pull folded memory into the LIVE MC working tree
git -C "$MEM" pull gitea main
git -C "$MEM" log --oneline -5                       # shows the laptop preference commit
git -C "$MEM" show --stat HEAD                        # the preference edit, merged cleanly

# Check 4 (Automation co-existence): automation/ commits made DURING the window, no collision
git -C "$MEM" log --oneline -- automation/ | head

# Check 1 (Continuity): the offline exchange appears ONCE in the canonical thread
git -C "$CONV" pull origin main
grep -rc "<offline-msg-id>" "$CONV"                   # → 1 (laptop will give you the id)

# leave the window: un-pause mc; confirm all 8 sessions healthy
```
⏸ **Tell the laptop B2 is done.**

---

## Part C — Check 5 (No DB growth). After the cycle.
```bash
C=$(docker ps --format '{{.Names}}' | grep -iE 'supabase-db|postgres' | head -1)
SQL="SELECT table_schema||'.'||table_name||'.'||column_name||':'||data_type FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1;"
docker exec "$C" psql -U postgres -d postgres -At -c "$SQL" > /tmp/pa-schema-after.txt
diff /tmp/pa-schema-baseline.txt /tmp/pa-schema-after.txt && echo "IDENTICAL — zero schema change"
shasum -a 256 /tmp/pa-schema-after.txt    # expect ee14a94e61e8ad579c0ba6e30ae9be209ccf7e0ef19df4c28fc8dbbbfe5dccb5
```
