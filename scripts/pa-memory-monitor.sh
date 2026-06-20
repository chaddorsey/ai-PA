#!/usr/bin/env bash
# pa-memory-monitor.sh — sample host + Docker memory pressure for trend analysis.
#
# Purpose: catch the slow climb that precedes the OOM/Jetsam reboots on the
# 24 GB mini. LOG-ONLY for now (no alerting / load-shedding yet) — we add
# thresholds once the curve tells us what climbs (agents/pa-web vs OrbStack creep).
#
# Logs to ~/Library/Logs/pa-memory-monitor/ (NOT /Volumes — launchd can't open
# log paths on external volumes at spawn; EX_CONFIG/78).
#
# Usage:
#   pa-memory-monitor.sh sample        # capture one sample (default; what launchd runs)
#   pa-memory-monitor.sh report [file] # summarize a day's headline TSV (climb at a glance)
set -uo pipefail

# launchd has no interactive PATH — set one that finds docker + the BSD tools.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.orbstack/bin:/usr/bin:/usr/sbin:/bin:/sbin"

LOGDIR="$HOME/Library/Logs/pa-memory-monitor"
mkdir -p "$LOGDIR"
DAY=$(date +%Y%m%d)
TSV="$LOGDIR/headline-$DAY.tsv"
DETAIL="$LOGDIR/detail-$DAY.log"
TS=$(date +%Y-%m-%dT%H:%M:%S)

CMD="${1:-sample}"

# ---------------------------------------------------------------- report mode
if [ "$CMD" = "report" ]; then
  f="${2:-$TSV}"
  [ -f "$f" ] || { echo "no log file: $f"; exit 1; }
  echo "Trend report for: $f"
  awk -F'\t' '
    NR==1 { next }
    {
      n++
      if (n==1) { ts0=$1; f0=$3; c0=$4; o0=$6; a0=$7 }
      ts1=$1; f1=$3; c1=$4; o1=$6; a1=$7
      if ($3!="" && (fmin=="" || $3+0<fmin)) fmin=$3+0
      if ($4+0>cmax) cmax=$4+0
      if ($6+0>omax) omax=$6+0
      if ($7+0>amax) amax=$7+0
    }
    END {
      if (n==0) { print "  (no samples yet)"; exit }
      printf "  samples: %d   window: %s .. %s\n\n", n, ts0, ts1
      printf "  %-14s %8s %8s %8s %8s\n", "metric", "first", "last", "min", "max"
      printf "  %-14s %8s %8s %8s %8s\n", "free_%",        f0, f1, fmin, "-"
      printf "  %-14s %8s %8s %8s %8s\n", "compressor_GB", c0, c1, "-", cmax
      printf "  %-14s %8s %8s %8s %8s\n", "orbstack_GB",   o0, o1, "-", omax
      printf "  %-14s %8s %8s %8s %8s\n", "agents_GB",     a0, a1, "-", amax
      print ""
      print "  (climb = last/max well above first → that metric is the leak suspect)"
    }' "$f"
  exit 0
fi

# ---------------------------------------------------------------- sample mode
# page size (bytes)
PGSZ=$(vm_stat 2>/dev/null | sed -n '1s/.*page size of \([0-9]*\) bytes.*/\1/p'); PGSZ="${PGSZ:-16384}"

# system free % (cheap, authoritative)
FREEPCT=$(memory_pressure 2>/dev/null | sed -n 's/.*free percentage: *\([0-9][0-9]*\)%.*/\1/p'); FREEPCT="${FREEPCT:-}"

# compressor footprint (GB) — heavy compressor = real pressure even when free% looks OK
COMPPAGES=$(vm_stat 2>/dev/null | sed -n 's/.*occupied by compressor: *\([0-9][0-9]*\)\..*/\1/p'); COMPPAGES="${COMPPAGES:-0}"
COMPGB=$(awk -v p="$COMPPAGES" -v s="$PGSZ" 'BEGIN{printf "%.2f", p*s/1073741824}')

# swap used (GB)
SWAPGB=$(sysctl -n vm.swapusage 2>/dev/null | sed -n 's/.*used = \([0-9.]*\)\([MG]\).*/\1 \2/p' | awk '{if($2=="G")printf "%.2f",$1; else printf "%.2f",$1/1024}')
SWAPGB="${SWAPGB:-0.00}"

# 1-min load
LOAD1=$(sysctl -n vm.loadavg 2>/dev/null | awk '{print $2}'); LOAD1="${LOAD1:-}"

# OrbStack host RSS (GB) — the VM overhead + lazy-reclaim creep suspect
ORBGB=$(ps -axo rss,comm 2>/dev/null | grep -i orbstack | grep -v grep | awk '{s+=$1} END{printf "%.2f", s/1048576}'); ORBGB="${ORBGB:-0.00}"

# local letta-code agents total RSS (GB) — the uncapped host-side growth suspect
AGENTGB=$(ps -axo rss,command 2>/dev/null | grep -- "letta --backend local" | grep -v grep | awk '{s+=$1} END{printf "%.2f", s/1048576}'); AGENTGB="${AGENTGB:-0.00}"

# single biggest host process (hint; detail log has the full list)
TOPLINE=$(ps -axo rss,comm 2>/dev/null | sort -rn | head -1)
TOPGB=$(echo "$TOPLINE" | awk '{printf "%.2f", $1/1048576}')
TOPPROC=$(echo "$TOPLINE" | awk '{print $2}' | xargs basename 2>/dev/null)

# headline TSV (one parseable line per sample)
if [ ! -f "$TSV" ]; then
  printf "ts\tload1\tfree_pct\tcompressor_gb\tswap_gb\torbstack_gb\tagents_gb\ttop_proc\ttop_gb\n" >> "$TSV"
fi
printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
  "$TS" "$LOAD1" "$FREEPCT" "$COMPGB" "$SWAPGB" "$ORBGB" "$AGENTGB" "${TOPPROC:-?}" "$TOPGB" >> "$TSV"

# detail block (host top-15 + container mem) — host part written first so a slow
# docker call never costs us the headline data
{
  echo "===== $TS  free=${FREEPCT}%  compressor=${COMPGB}GB  swap=${SWAPGB}GB  orbstack=${ORBGB}GB  agents=${AGENTGB}GB ====="
  echo "-- top 15 host processes by RSS --"
  ps -axo rss,comm 2>/dev/null | sort -rn | head -15 | awk '{rss=$1; $1=""; sub(/^ /,""); printf "  %7.2f GB  %s\n", rss/1048576, $0}'
  echo "-- docker containers by mem --"
  docker stats --no-stream --format '{{.MemUsage}}|{{.Name}}' 2>/dev/null | sort -rh | head -15 | sed 's/^/  /' || echo "  (docker unavailable)"
  echo "-- top 12 by memory FOOTPRINT (top -o mem; catches compressed/non-RSS the leak hides in) --"
  top -l 1 -o mem -n 12 -stats command,mem 2>/dev/null | sed -n '/COMMAND/,$p' | head -13 | sed 's/^/  /' || echo "  (top unavailable)"
  echo ""
} >> "$DETAIL" 2>&1
