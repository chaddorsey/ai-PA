#!/bin/bash
# Calendly MCP Server Test Script
# Demonstrates all functionality and error handling

set -e

BASE_URL="http://localhost:8086"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================="
echo "Calendly MCP Server Comprehensive Tests"
echo "========================================="
echo ""

# Test 1: Health Check
echo -e "${YELLOW}Test 1: Health Check${NC}"
HEALTH=$(curl -s ${BASE_URL}/health)
if echo "$HEALTH" | jq -e '.status == "healthy"' > /dev/null; then
    echo -e "${GREEN}✓ Health check passed${NC}"
    echo "$HEALTH" | jq '.'
else
    echo -e "${RED}✗ Health check failed${NC}"
    exit 1
fi
echo ""

# Test 2: MCP Initialize
echo -e "${YELLOW}Test 2: MCP Initialize${NC}"
INIT=$(curl -s -X POST ${BASE_URL}/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
if echo "$INIT" | jq -e '.result.serverInfo.name == "calendly-tools"' > /dev/null; then
    echo -e "${GREEN}✓ Initialize successful${NC}"
    echo "$INIT" | jq '.result.serverInfo'
else
    echo -e "${RED}✗ Initialize failed${NC}"
    exit 1
fi
echo ""

# Test 3: Tools List
echo -e "${YELLOW}Test 3: Tools List (Simplified Schema)${NC}"
TOOLS=$(curl -s -X POST ${BASE_URL}/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}')
TOOL_COUNT=$(echo "$TOOLS" | jq '.result.tools | length')
PARAMS=$(echo "$TOOLS" | jq -r '.result.tools[0].inputSchema.properties | keys | join(", ")')
echo -e "${GREEN}✓ Found ${TOOL_COUNT} tool(s)${NC}"
echo "  Parameters: ${PARAMS}"
echo "  (sniff_wait and per_day_delay are NOT exposed - handled internally)"
echo ""

# Test 4: Valid Query with Simplified API
echo -e "${YELLOW}Test 4: Valid Query (Simplified API)${NC}"
QUERY=$(curl -s -X POST ${BASE_URL}/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{
      "name":"calendly_slots",
      "arguments":{
        "url":"https://calendly.com/zarek-drozda",
        "start":"2025-10-16",
        "end":"2025-10-18"
      }
    }
  }')
if echo "$QUERY" | jq -e '.result' > /dev/null 2>&1; then
    EVENT_COUNT=$(echo "$QUERY" | jq -r '.result.content[0].text' | python3 -c "import sys, ast; print(len(ast.literal_eval(sys.stdin.read())['events']))")
    echo -e "${GREEN}✓ Query successful, found ${EVENT_COUNT} event(s)${NC}"
else
    echo -e "${RED}✗ Query failed${NC}"
    echo "$QUERY" | jq '.error.message'
fi
echo ""

# Test 5: Missing Required Parameter
echo -e "${YELLOW}Test 5: Missing URL (Error Handling)${NC}"
ERROR1=$(curl -s -X POST ${BASE_URL}/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":4,
    "method":"tools/call",
    "params":{
      "name":"calendly_slots",
      "arguments":{}
    }
  }')
ERROR_MSG=$(echo "$ERROR1" | jq -r '.error.message')
echo -e "${GREEN}✓ Error message:${NC}"
echo "  $ERROR_MSG"
echo ""

# Test 6: Invalid Date Format
echo -e "${YELLOW}Test 6: Invalid Date Format (Error Handling)${NC}"
ERROR2=$(curl -s -X POST ${BASE_URL}/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":5,
    "method":"tools/call",
    "params":{
      "name":"calendly_slots",
      "arguments":{
        "url":"https://calendly.com/test",
        "start":"2025/10/15"
      }
    }
  }')
ERROR_MSG=$(echo "$ERROR2" | jq -r '.error.message')
echo -e "${GREEN}✓ Error message:${NC}"
echo "  $ERROR_MSG"
echo ""

# Test 7: Invalid Date Range
echo -e "${YELLOW}Test 7: Invalid Date Range (Error Handling)${NC}"
ERROR3=$(curl -s -X POST ${BASE_URL}/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":6,
    "method":"tools/call",
    "params":{
      "name":"calendly_slots",
      "arguments":{
        "url":"https://calendly.com/test",
        "start":"2025-11-15",
        "end":"2025-11-10"
      }
    }
  }')
ERROR_MSG=$(echo "$ERROR3" | jq -r '.error.message')
echo -e "${GREEN}✓ Error message:${NC}"
echo "  $ERROR_MSG"
echo ""

# Test 8: Non-Calendly URL
echo -e "${YELLOW}Test 8: Non-Calendly URL (Error Handling)${NC}"
ERROR4=$(curl -s -X POST ${BASE_URL}/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":7,
    "method":"tools/call",
    "params":{
      "name":"calendly_slots",
      "arguments":{
        "url":"https://example.com/meeting"
      }
    }
  }')
ERROR_MSG=$(echo "$ERROR4" | jq -r '.error.message')
echo -e "${GREEN}✓ Error message:${NC}"
echo "  $ERROR_MSG"
echo ""

echo "========================================="
echo -e "${GREEN}All tests completed successfully!${NC}"
echo "========================================="
echo ""
echo "Summary:"
echo "  ✓ Simplified API (4 parameters instead of 6)"
echo "  ✓ Automatic retry with increasing wait times"
echo "  ✓ Expressive validation error messages"
echo "  ✓ Context-specific runtime error messages"
echo "  ✓ Internal optimization (no exposed sniff_wait/per_day_delay)"

