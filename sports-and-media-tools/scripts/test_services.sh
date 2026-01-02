#!/bin/bash
#
# Test script for Sports & Media Control Services
# Tests sports-service and flipper-api endpoints
#

set -e

echo "=========================================="
echo "Sports & Media Control Services Test"
echo "=========================================="
echo ""

# Configuration
SPORTS_SERVICE_URL="${SPORTS_SERVICE_URL:-http://localhost:5123}"
FLIPPER_API_URL="${FLIPPER_API_URL:-http://localhost:5124}"
ROKU_TV_IP="${ROKU_TV_IP:-192.168.7.187}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

success() {
    echo -e "${GREEN}✓ $1${NC}"
}

error() {
    echo -e "${RED}✗ $1${NC}"
}

warn() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

test_endpoint() {
    local name="$1"
    local url="$2"
    local expected_status="${3:-200}"
    
    echo -n "Testing $name... "
    
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    
    if [ "$HTTP_STATUS" = "$expected_status" ]; then
        success "OK (HTTP $HTTP_STATUS)"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        error "FAILED (HTTP $HTTP_STATUS, expected $expected_status)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

test_json_field() {
    local name="$1"
    local url="$2"
    local field="$3"
    local expected="$4"
    
    echo -n "Testing $name... "
    
    RESPONSE=$(curl -s "$url" 2>/dev/null || echo "{}")
    VALUE=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$field',''))" 2>/dev/null || echo "")
    
    if [ "$VALUE" = "$expected" ]; then
        success "OK ($field=$VALUE)"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        error "FAILED ($field=$VALUE, expected $expected)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

echo "=== Sports Service Tests ==="
echo ""

# Health check
test_json_field "Sports Service Health" "$SPORTS_SERVICE_URL/health" "status" "healthy"

# Games endpoint
test_endpoint "Games Endpoint" "$SPORTS_SERVICE_URL/games"

# League filter
test_endpoint "NFL Games" "$SPORTS_SERVICE_URL/games/nfl"
test_endpoint "NBA Games" "$SPORTS_SERVICE_URL/games/nba"

# Team lookup
test_endpoint "Team Lookup (Patriots)" "$SPORTS_SERVICE_URL/team/patriots"

# Channel lookup
test_endpoint "Channel Lookup (ESPN)" "$SPORTS_SERVICE_URL/channel/ESPN"

# Mapping endpoint
test_endpoint "Channel Mapping" "$SPORTS_SERVICE_URL/mapping"

echo ""
echo "=== Flipper API Tests ==="
echo ""

# Health check
test_endpoint "Flipper API Health" "$FLIPPER_API_URL/health"

# Commands list
test_endpoint "Available Commands" "$FLIPPER_API_URL/commands"

echo ""
echo "=== Roku TV Tests ==="
echo ""

# Roku device info
test_endpoint "Roku Device Info" "http://$ROKU_TV_IP:8060/query/device-info"

echo ""
echo "=========================================="
echo "Test Results"
echo "=========================================="
echo ""
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "${YELLOW}Some tests failed. Check service logs for details.${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  - Ensure Docker services are running: docker-compose ps"
    echo "  - Check sports-service logs: docker-compose logs sports-service"
    echo "  - Check flipper-api logs: docker-compose logs flipper-api"
    echo "  - Verify Flipper Zero is connected via USB"
    echo "  - Verify Roku TV is on the network at $ROKU_TV_IP"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi

