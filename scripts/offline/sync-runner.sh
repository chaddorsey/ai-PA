#!/usr/bin/env bash
# sync-runner.sh — connectivity-aware git sync for the offline/travel MC (laptop side).
#
# One pipe for all four data kinds (design §5): memory (memfs), conversation,
# outbox, inbox — all ride the SSH tunnel → Gitea. MC never drives this; it only
# appends locally (letta-code commits memfs; envelopes land in the outbox repo).
# This runner does the I/O on network-up.
#
# memfs uses the B'-style branch fold (design D4): the laptop shapes on
# `travel/laptop`; each online window we rebase it onto origin/main (picking up
# home's automation/-namespace commits) and fast-forward main → fold complete,
# trivial merges because the two writers never touch the same paths.
#
# Idempotent + safe to re-run (cron/launchd). Lock prevents overlap; debounce
# skips rapid re-fires. Run conn-probe first; do nothing while offline.
set -uo pipefail

REPO_ROOT="${PA_AI_REPO_ROOT:-$HOME/ai-PA}"
HERE="$(cd "$(dirname "$0")" && pwd)"
MC="agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d"
BACKEND="${LETTA_LOCAL_BACKEND_DIR:-$HOME/.letta/lc-local-backend}"
BUS_DIR="${OFFLINE_BUS_DIR:-$HOME/.letta/offline-bus}"

MEMFS="$BACKEND/memfs/$MC/memory"
OUTBOX="$BUS_DIR/outbox"
INBOX="$BUS_DIR/inbox"
LINK_JSON="$BUS_DIR/link.json"
LOCK="$BUS_DIR/.sync.lock"
LAST_RUN="$BUS_DIR/.sync.last"
LOG="${OFFLINE_SYNC_LOG:-$HOME/Library/Logs/offline-sync.log}"

DEBOUNCE_SECS="${SYNC_DEBOUNCE_SECS:-15}"
TUNNEL_SPEC="-L 3030:127.0.0.1:3030 dorseyhomeserver@dorseys-mac-mini.tailf9b999.ts.net"

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG" >&2; }
mkdir -p "$(dirname "$LOG")" "$BUS_DIR"

# ---- lock (mkdir is atomic; works without flock on macOS) ----
if ! mkdir "$LOCK" 2>/dev/null; then
  log "another sync holds the lock ($LOCK); skipping"; exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

# ---- debounce ----
if [ -f "$LAST_RUN" ]; then
  last=$(cat "$LAST_RUN" 2>/dev/null || echo 0)
  nows=$(date +%s)
  if [ $(( nows - last )) -lt "$DEBOUNCE_SECS" ]; then
    log "debounced (last run $(( nows - last ))s ago < ${DEBOUNCE_SECS}s)"; exit 0
  fi
fi

ensure_tunnel() {
  # Bring up autossh if Gitea isn't answering and we're not simulating offline.
  if curl -s -o /dev/null -m 3 -w '%{http_code}' http://127.0.0.1:3030/api/v1/version 2>/dev/null | grep -q 200; then
    return 0
  fi
  if command -v autossh >/dev/null 2>&1; then
    log "tunnel down — starting autossh"
    # shellcheck disable=SC2086
    autossh -M 0 -f -N $TUNNEL_SPEC 2>>"$LOG" || true
    sleep 2
  fi
}

# generic pull/push for a simple (single-branch) repo; $2 = push? (1/0)
sync_simple() {
  local dir="$1" do_push="$2" name="$3"
  [ -d "$dir/.git" ] || { log "$name: no repo at $dir (skip)"; return 0; }
  local br; br="$(git -C "$dir" rev-parse --abbrev-ref HEAD)"
  if [ "$do_push" = "1" ]; then
    git -C "$dir" add -A 2>/dev/null
    git -C "$dir" diff --cached --quiet 2>/dev/null || git -C "$dir" commit -q -m "sync-runner: $name @ $(date -u +%FT%TZ)"
  fi
  git -C "$dir" fetch -q origin 2>>"$LOG" || { log "$name: fetch failed"; return 1; }
  git -C "$dir" rebase -q "origin/$br" 2>>"$LOG" || { git -C "$dir" rebase --abort 2>/dev/null; log "$name: rebase conflict — left for review"; return 2; }
  if [ "$do_push" = "1" ]; then
    git -C "$dir" push -q origin "HEAD:$br" 2>>"$LOG" || { log "$name: push failed"; return 3; }
  fi
  log "$name: synced ($br @ $(git -C "$dir" rev-parse --short HEAD))"
}

# memfs: rebase travel/laptop onto origin/main, then fold (ff) main forward.
sync_memfs() {
  [ -d "$MEMFS/.git" ] || { log "memfs: no repo (skip)"; return 0; }
  git -C "$MEMFS" add -A 2>/dev/null
  git -C "$MEMFS" diff --cached --quiet 2>/dev/null || git -C "$MEMFS" commit -q -m "sync-runner: laptop memory @ $(date -u +%FT%TZ)"
  local a
  for a in 1 2 3; do
    git -C "$MEMFS" fetch -q origin 2>>"$LOG" || { log "memfs: fetch failed"; return 1; }
    git -C "$MEMFS" rebase -q origin/main 2>>"$LOG" || { git -C "$MEMFS" rebase --abort 2>/dev/null; log "memfs: rebase conflict onto main — left for review"; return 2; }
    git -C "$MEMFS" push -q origin travel/laptop 2>>"$LOG" || true
    if git -C "$MEMFS" push -q origin travel/laptop:main 2>>"$LOG"; then
      log "memfs: folded travel/laptop -> main (attempt $a, $(git -C "$MEMFS" rev-parse --short HEAD))"
      return 0
    fi
    log "memfs: main push non-ff, retrying ($a)"
  done
  log "memfs: fold failed after retries"; return 3
}

# ---- main ----
bash "$HERE/conn-probe.sh" >/dev/null 2>&1 || true
ensure_tunnel
bash "$HERE/conn-probe.sh" >/dev/null 2>&1 || true

online="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["online"])' "$LINK_JSON" 2>/dev/null || echo False)"
if [ "$online" != "True" ]; then
  log "offline (online=$online) — nothing to sync"
  date +%s > "$LAST_RUN"; exit 0
fi

log "online — syncing memfs + outbox + inbox + conversation"
sync_memfs                                  || log "memfs sync incomplete"
sync_simple "$OUTBOX" 1 "outbox"            || log "outbox sync incomplete"
sync_simple "$INBOX"  0 "inbox"             || log "inbox sync incomplete"
# conversation repo (created during the §6 quiesce window; synced once present)
for cdir in "$BACKEND"/conversations/*/; do
  [ -d "$cdir/.git" ] && sync_simple "$cdir" 1 "conversation:$(basename "$cdir")"
done

date +%s > "$LAST_RUN"
log "sync complete"
