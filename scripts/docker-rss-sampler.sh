#!/bin/bash
# Hourly sample of docker container memory, for memory-creep investigation.
# Append TSV: timestamp<TAB>name<TAB>mem_used<TAB>mem_pct<TAB>cpu_pct

set -euo pipefail

LOG=/Volumes/main-drive/ai-PA/logs/docker-rss-sampler.tsv
mkdir -p "$(dirname "$LOG")"

ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

docker stats --no-stream --format '{{.Name}}	{{.MemUsage}}	{{.MemPerc}}	{{.CPUPerc}}' \
  | while IFS=$'\t' read -r name mem pct cpu; do
      printf '%s\t%s\t%s\t%s\t%s\n' "$ts" "$name" "$mem" "$pct" "$cpu"
  done >> "$LOG"
