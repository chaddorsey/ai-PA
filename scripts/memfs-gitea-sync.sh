#!/usr/bin/env bash
# memfs-gitea-sync.sh — periodic Gitea sync for every local agent's memfs repo.
#
# Replaces the letta-local-runner's per-invocation pull-rebase-before/push-after wrapper
# (invoker.py), retired with the runner at the 2026-08-17 controller cutover. Turns now
# originate from many sources (controller queue, scheduler ingress, enrichment
# /v1/responses, web surface), so a periodic sweep is the only place that covers them
# all uniformly. letta-code commits memfs changes locally on its own; this only MOVES
# commits between the local repos and the Gitea hub. Logic mirrors invoker.py:
#   pull --rebase --autostash   (on failure: rebase --abort → clean tree, skip)
#   push                        (on reject: one pull-rebase + push retry)
# A true same-file conflict leaves the local commit unpushed on a clean tree — no data
# loss, retried next interval, surfaced in the log.
#
# Driven by com.ai-pa.memfs-gitea-sync (StartInterval). Safe to run by hand.
set -uo pipefail

export HOME="${HOME:-/Users/dorseyhomeserver}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
# Identity so a rebase can replay commits even without global git config
# (same values the runner used).
export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-memfs-gitea-sync}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-runner@localhost}"
export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-memfs-gitea-sync}"
export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-runner@localhost}"

MEMFS_ROOT="${MEMFS_ROOT:-$HOME/.letta/lc-local-backend/memfs}"
REMOTE="${MEMFS_REMOTE:-gitea}"
BRANCH="${MEMFS_BRANCH:-main}"
GIT_TIMEOUT="${MEMFS_GIT_TIMEOUT:-60}"

LOG_DIR="$HOME/Library/Logs/memfs-gitea-sync"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/sync.log"
ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" >> "$LOG"; }

git_to() { # bounded git in a repo: git_to <repo> <args...>
  local repo="$1"; shift
  # macOS has no coreutils timeout by default; perl alarm is always present.
  perl -e 'alarm shift; exec @ARGV' "$GIT_TIMEOUT" git -C "$repo" "$@" >>"$LOG" 2>&1
}

pull_rebase() { # $1=repo $2=agent — true only on clean pull
  if git_to "$1" pull --rebase --autostash "$REMOTE" "$BRANCH"; then
    return 0
  fi
  git_to "$1" rebase --abort || true   # no-op (nonzero) when no rebase in progress
  log "WARN $2: pull-rebase failed; aborted to clean tree"
  return 1
}

synced=0 skipped=0 failed=0
for mem in "$MEMFS_ROOT"/*/memory; do
  [ -d "$mem/.git" ] || { skipped=$((skipped+1)); continue; }
  agent="$(basename "$(dirname "$mem")")"
  git -C "$mem" remote 2>/dev/null | grep -qx "$REMOTE" || { skipped=$((skipped+1)); continue; }

  # Sync moves COMMITS only; letta-code's per-turn auto-commit produces them. A tree
  # that stays dirty means auto-commit is failing (seen 2026-08-17: pulse's pre-commit
  # frontmatter hook silently rejected every commit for 3 days) — surface it.
  dirty_tracked=$(git -C "$mem" status --porcelain 2>/dev/null | grep -cv '^??')
  [ "${dirty_tracked:-0}" -gt 0 ] && log "WARN $agent: $dirty_tracked uncommitted tracked change(s) — letta-code auto-commit may be failing (pre-commit hook?)"

  pull_rebase "$mem" "$agent" || { failed=$((failed+1)); continue; }

  if git_to "$mem" push "$REMOTE" "$BRANCH"; then
    synced=$((synced+1)); continue
  fi
  # Most likely non-fast-forward: the hub advanced. Rebase and retry once.
  log "WARN $agent: push rejected; rebase+retry"
  if pull_rebase "$mem" "$agent" && git_to "$mem" push "$REMOTE" "$BRANCH"; then
    log "OK $agent: pushed after rebase"
    synced=$((synced+1))
  else
    log "ERROR $agent: push failed after rebase (local commit stays unpushed, clean tree)"
    failed=$((failed+1))
  fi
done

log "sweep done: synced=$synced skipped=$skipped failed=$failed"
exit 0
