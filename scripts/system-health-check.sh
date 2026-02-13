#!/bin/bash
#
# AI-PA System Health Check
#
# Run after reboot or whenever you need to verify all services are up.
#
# Usage:
#   ./scripts/system-health-check.sh          # Full check
#   ./scripts/system-health-check.sh --quick   # Skip slow checks (MCP tool listing)
#   ./scripts/system-health-check.sh --start   # Start everything that's down
#

set -uo pipefail

PROJECT_ROOT="/Volumes/main-drive/ai-PA"
QUICK=false
AUTO_START=false

for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=true ;;
        --start) AUTO_START=true ;;
    esac
done

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

pass=0
fail=0
warn=0

ok()   { echo -e "  ${GREEN}✓${NC} $1"; ((pass++)); }
fail() { echo -e "  ${RED}✗${NC} $1"; ((fail++)); }
warn() { echo -e "  ${YELLOW}!${NC} $1"; ((warn++)); }

# -----------------------------------------------------------------------
echo -e "${BOLD}=== Docker Desktop ===${NC}"
# -----------------------------------------------------------------------

if docker info >/dev/null 2>&1; then
    ok "Docker engine running"
else
    fail "Docker engine not running"
    if $AUTO_START; then
        echo "    Starting Docker Desktop..."
        open -a "Docker Desktop"
        echo "    Waiting up to 60s for engine..."
        for i in $(seq 1 12); do
            sleep 5
            if docker info >/dev/null 2>&1; then
                ok "Docker engine started after ~$((i*5))s"
                break
            fi
        done
        if ! docker info >/dev/null 2>&1; then
            fail "Docker engine still not ready — start manually"
        fi
    fi
fi

# Bail early if Docker isn't available
if ! docker info >/dev/null 2>&1; then
    echo ""
    echo -e "${RED}Docker is down — skipping container checks${NC}"
    echo -e "Start Docker Desktop, then re-run this script."
    echo ""
    echo -e "${BOLD}=== LaunchAgents ===${NC}"
    # Still check launchd agents since they don't need Docker
    _check_launchd=true
else
    _check_launchd=false

    # -------------------------------------------------------------------
    echo ""
    echo -e "${BOLD}=== Docker Compose Services ===${NC}"
    # -------------------------------------------------------------------

    cd "$PROJECT_ROOT"

    # Core services to check
    CORE_SERVICES="letta supabase-db supabase-rest n8n slackbot scheduler-service pa-routing-handler pa-web-ui"
    OPTIONAL_SERVICES="neo4j graphiti-mcp-server gmail-mcp-server omnifocus-mcp-server scheduler-mcp"

    if $AUTO_START; then
        echo "  Starting all services..."
        docker-compose up -d 2>/dev/null
        sleep 5
    fi

    for svc in $CORE_SERVICES; do
        status=$(docker-compose ps --format json "$svc" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('State','unknown'))" 2>/dev/null || echo "unknown")
        if [ "$status" = "running" ]; then
            ok "$svc"
        else
            fail "$svc ($status)"
        fi
    done

    for svc in $OPTIONAL_SERVICES; do
        status=$(docker-compose ps --format json "$svc" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('State','unknown'))" 2>/dev/null || echo "unknown")
        if [ "$status" = "running" ]; then
            ok "$svc"
        elif [ "$status" = "unknown" ]; then
            warn "$svc (not configured)"
        else
            warn "$svc ($status)"
        fi
    done

    # -------------------------------------------------------------------
    echo ""
    echo -e "${BOLD}=== Letta ===${NC}"
    # -------------------------------------------------------------------

    LETTA_HEALTH=$(curl -sL --max-time 5 http://localhost:8283/v1/health/ 2>&1)
    if echo "$LETTA_HEALTH" | grep -q "ok\|healthy" 2>/dev/null; then
        ok "Letta API (http://localhost:8283)"
    elif curl -sL --max-time 5 -o /dev/null -w "%{http_code}" http://localhost:8283/v1/health/ 2>/dev/null | grep -q "200"; then
        ok "Letta API (http://localhost:8283)"
    else
        fail "Letta API not responding"
    fi

    # -------------------------------------------------------------------
    echo ""
    echo -e "${BOLD}=== MCP Proxies ===${NC}"
    # -------------------------------------------------------------------

    check_mcp_proxy() {
        local name="$1"
        local port="$2"
        local expect="$3"

        RESP=$(curl -s --max-time 5 -X POST "http://localhost:$port/mcp" \
            -H "Content-Type: application/json" \
            -H "Accept: application/json, text/event-stream" \
            -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"health","version":"1.0"}}}' 2>&1)

        if echo "$RESP" | grep -q "$expect"; then
            if ! $QUICK; then
                TOOLS=$(curl -s --max-time 5 -X POST "http://localhost:$port/mcp" \
                    -H "Content-Type: application/json" \
                    -H "Accept: application/json, text/event-stream" \
                    -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' 2>&1)
                TOOL_COUNT=$(echo "$TOOLS" | python3 -c "
import sys,json
for line in sys.stdin:
    if line.startswith('data: '):
        d = json.loads(line[6:])
        print(len(d.get('result',{}).get('tools',[])))
        break
" 2>/dev/null || echo "?")
                ok "$name (:$port) — $TOOL_COUNT tools"
            else
                ok "$name (:$port)"
            fi
        else
            fail "$name (:$port) not responding"
        fi
    }

    check_mcp_proxy "Granola supergateway" 8089 "granola-mcp"
    check_mcp_proxy "Atlassian supergateway" 8091 "atlassian-mcp-server"

    # -------------------------------------------------------------------
    echo ""
    echo -e "${BOLD}=== LaunchAgents ===${NC}"
    _check_launchd=true
    # -------------------------------------------------------------------
fi

if $_check_launchd; then
    AGENTS=(
        "com.ai-pa.supergateway-granola|Granola MCP proxy (port 8089)"
        "com.ai-pa.supergateway-atlassian|Atlassian MCP proxy (port 8091)"
        "com.ai-pa.granola-mcp-ingest|Granola MCP archival ingestion (15m)"
        "com.ai-pa.granola-watcher|Granola cache watcher (5m)"
        "com.ai-pa.granola-export|Granola export"
        "com.ai-pa.letta-cleanup|macOS metadata cleanup (hourly)"
    )

    for entry in "${AGENTS[@]}"; do
        label="${entry%%|*}"
        desc="${entry##*|}"

        line=$(launchctl list 2>/dev/null | grep "$label" || true)
        if [ -z "$line" ]; then
            fail "$desc — not loaded"
            if $AUTO_START; then
                plist="$HOME/Library/LaunchAgents/$label.plist"
                if [ -f "$plist" ]; then
                    launchctl load "$plist" 2>/dev/null && warn "$desc — loaded now" || fail "$desc — load failed"
                fi
            fi
        else
            pid=$(echo "$line" | awk '{print $1}')
            exit_code=$(echo "$line" | awk '{print $2}')
            if [ "$pid" != "-" ]; then
                ok "$desc (running, PID $pid)"
            elif [ "$exit_code" = "0" ]; then
                ok "$desc (last exit: 0)"
            else
                warn "$desc (last exit: $exit_code)"
            fi
        fi
    done
fi

# -----------------------------------------------------------------------
echo ""
echo -e "${BOLD}=== Summary ===${NC}"
echo -e "  ${GREEN}$pass passed${NC}  ${RED}$fail failed${NC}  ${YELLOW}$warn warnings${NC}"
# -----------------------------------------------------------------------

if [ $fail -gt 0 ]; then
    echo ""
    echo "  Tip: re-run with --start to auto-start failed services"
    exit 1
fi
