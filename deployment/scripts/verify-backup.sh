#!/bin/bash
# verify-backup.sh — check that a pa-ecosystem backup is complete and valid.
# Exits 0 if all checks pass, 1 otherwise.
#
# Usage:
#   verify-backup.sh [backup-path]
#
# If no path is given, verifies the 'latest' symlink in
# /Volumes/main-drive/ai-PA/deployment/backups/latest.

set -uo pipefail

BACKUP_PATH="${1:-/Volumes/main-drive/ai-PA/deployment/backups/latest}"

if [[ -L "$BACKUP_PATH" ]]; then
    BACKUP_PATH="$(cd "$(dirname "$BACKUP_PATH")" && cd "$(readlink "$BACKUP_PATH")" && pwd)"
elif [[ -d "$BACKUP_PATH" ]]; then
    BACKUP_PATH="$(cd "$BACKUP_PATH" && pwd)"
else
    echo "ERROR: $BACKUP_PATH is neither a directory nor a symlink" >&2
    exit 2
fi

echo "=== Verifying backup: $BACKUP_PATH ==="

FAIL=0
pass() { printf "  \033[32m[PASS]\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m[FAIL]\033[0m %s\n" "$1"; FAIL=1; }

# ---- 1. Overall size ----
size_gb=$(du -sk "$BACKUP_PATH" | awk '{print int($1/1024/1024)}')
if (( size_gb >= 50 )); then
    pass "Total size ${size_gb}G (min 50G)"
else
    fail "Total size ${size_gb}G, below 50G floor"
fi

# ---- 2. Required subdirectories present and non-empty ----
for d in configs databases host_data letta_exports volumes; do
    if [[ ! -d "$BACKUP_PATH/$d" ]]; then
        fail "Missing subdir: $d/"
    else
        bytes=$(du -sk "$BACKUP_PATH/$d" | awk '{print $1}')
        if (( bytes > 4 )); then
            pass "$d/ populated ($(du -sh "$BACKUP_PATH/$d" | cut -f1))"
        else
            fail "$d/ is empty"
        fi
    fi
done

# ---- 3. Database dumps — expect 6 DBs + pg_cluster ----
# pg_cluster dump header is "PostgreSQL database cluster dump"; per-DB dumps
# say "PostgreSQL database dump". Check first few lines for either variant.
expected_dbs=(pg_cluster letta litellm n8n scheduler_service curator_radar)
for db in "${expected_dbs[@]}"; do
    if ls "$BACKUP_PATH/databases/${db}"_*.sql >/dev/null 2>&1; then
        dump=$(ls "$BACKUP_PATH/databases/${db}"_*.sql | head -1)
        if head -5 "$dump" | grep -qi "PostgreSQL database"; then
            pass "DB dump valid: $(basename "$dump") ($(du -sh "$dump" | cut -f1))"
        else
            fail "DB dump missing SQL header: $(basename "$dump")"
        fi
    else
        fail "Expected DB dump missing: ${db}_*.sql"
    fi
done

# ---- 4. Docker volume tarballs ----
# Most PA data lives in bind mounts (host_data) and Postgres (databases); named
# Docker volumes are limited. We expect at least the supabase-db data volume.
vol_count=$(find "$BACKUP_PATH/volumes" -name "*.tar.gz" 2>/dev/null | wc -l | tr -d ' ')
if (( vol_count >= 2 )); then
    pass "Docker volumes tarred: $vol_count file(s)"
else
    fail "Only $vol_count volume tarball(s); expected >= 2 (at minimum supabase-db)"
fi

# Specifically verify the supabase-db volume tarball exists and is substantial
supabase_tar=$(find "$BACKUP_PATH/volumes" -name "*supabase_db*.tar.gz" 2>/dev/null | head -1)
if [[ -n "$supabase_tar" ]]; then
    supabase_gb=$(du -k "$supabase_tar" | awk '{print int($1/1024/1024)}')
    if (( supabase_gb >= 1 )); then
        pass "supabase-db volume tar: ${supabase_gb}G"
    else
        fail "supabase-db volume tar is only ${supabase_gb}G (suspicious)"
    fi
else
    fail "No supabase_db volume tarball found"
fi

# ---- 5. Letta agent exports ----
agent_count=$(find "$BACKUP_PATH/letta_exports/agents" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
if (( agent_count >= 20 )); then
    pass "Letta agent exports: $agent_count file(s)"
else
    fail "Only $agent_count Letta agent export(s); expected >= 20"
fi

blocks_file="$BACKUP_PATH/letta_exports/memory/blocks_all.json"
if [[ -s "$blocks_file" ]]; then
    blocks_kb=$(du -k "$blocks_file" | awk '{print $1}')
    if (( blocks_kb >= 50 )); then
        pass "Letta memory blocks ($(du -sh "$blocks_file" | cut -f1))"
    else
        fail "Letta memory blocks file too small: ${blocks_kb}K"
    fi
else
    fail "Letta memory blocks file missing or empty"
fi

# ---- 6. Host data — the regression we spotted in Apr 14 backup ----
host_count=$(find "$BACKUP_PATH/host_data" -name "*.tar.gz" 2>/dev/null | wc -l | tr -d ' ')
if (( host_count >= 3 )); then
    pass "Host data tarballs: $host_count file(s)"
else
    fail "Only $host_count host_data file(s); expected >= 3 (auto-madden, smaug, letta-filesystem-repo...)"
fi

# ---- 7. Git reference + manifest ----
if [[ -s "$BACKUP_PATH/GIT_REFERENCE.txt" ]] && grep -q "^Commit:" "$BACKUP_PATH/GIT_REFERENCE.txt"; then
    commit=$(awk '/^Commit:/ {print $2}' "$BACKUP_PATH/GIT_REFERENCE.txt" | head -1)
    pass "Git reference captured (commit $commit)"
else
    fail "GIT_REFERENCE.txt missing or malformed"
fi

if [[ -s "$BACKUP_PATH/BACKUP_MANIFEST.md" ]]; then
    pass "BACKUP_MANIFEST.md present"
else
    fail "BACKUP_MANIFEST.md missing"
fi

echo
if (( FAIL == 0 )); then
    echo "=== VERIFICATION PASSED ==="
    exit 0
else
    echo "=== VERIFICATION FAILED ==="
    exit 1
fi
