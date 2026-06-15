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

qmd collection reindex evernote 2>/dev/null || qmd collection add evernote "$CORPUS"
echo "evernote-archive done: $(date)"
