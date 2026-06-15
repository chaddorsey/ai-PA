#!/usr/bin/env bash
# Weekly: incremental sync -> re-export -> re-convert (idempotent) -> post-process -> reindex.
set -euo pipefail
BK="$HOME/.letta/reference-archive/.backup"
CORPUS="$HOME/.letta/reference-archive/raw/evernote"
STATE="$HOME/.letta/reference-archive/.state/evernote-archive.json"
CFG="/Volumes/main-drive/ai-PA/evernote-archiver/yarle-config.json"
PKG="/Volumes/main-drive/ai-PA/evernote-archiver"
PY="$HOME/.letta/pa-tools-venv/bin/python"

cd "$BK"
evernote-backup sync                      # incremental; refreshes en_backup.db
rm -rf enex_out && evernote-backup export ./enex_out/
rm -rf "$CORPUS" && mkdir -p "$CORPUS"    # clean re-convert (idempotent, avoids orphans)
npx -y -p yarle-evernote-to-md@latest yarle --configFile "$CFG"

cd "$PKG"
"$PY" -m evernote_archiver.run --corpus "$CORPUS" --db "$BK/en_backup.db" --state "$STATE"
# run.py exits non-zero on reconcile failure -> launchd logs it; corpus already written for inspection

# Refresh the qmd index + local embeddings (content-hash dedup => unchanged notes
# are skipped; embeddings are local/free). Collection must already exist (created
# once via: qmd collection add /Volumes/main-filestore/reference-archive/raw/evernote --name evernote).
qmd update 2>&1 | tail -3 || true
# Embed in a loop: the local embedding server can expire mid-run on large batches,
# leaving chunks pending. Re-run (resumable) until pending hits 0 or no progress.
for i in $(seq 1 10); do
  qmd embed -c evernote 2>&1 | tail -2 || true
  pending=$(qmd status 2>/dev/null | grep -i Pending | grep -oE '[0-9]+' | head -1)
  echo "embed pass $i: pending=${pending:-0}"   # qmd omits the line at 0
  if [ -z "$pending" ] || [ "$pending" = "0" ]; then break; fi
done
echo "evernote-archive done: $(date)"
