#!/bin/bash
# Configure Letta to use the Atlassian Rovo token

TOKEN_FILE="$HOME/.atlassian-rovo-token.txt"

echo "============================================================"
echo "Configure Letta with Atlassian Rovo Token"
echo "============================================================"
echo ""

# Check if token file exists
if [ ! -f "$TOKEN_FILE" ]; then
    echo "❌ Token file not found: $TOKEN_FILE"
    echo ""
    echo "Please extract the token from browser DevTools and save it:"
    echo "  echo 'YOUR_TOKEN' > $TOKEN_FILE"
    exit 1
fi

# Read token
TOKEN=$(cat "$TOKEN_FILE" | tr -d '\n' | tr -d ' ')

if [ -z "$TOKEN" ]; then
    echo "❌ Token file is empty"
    exit 1
fi

echo "✓ Token found: ${TOKEN:0:50}..."
echo ""

# Export token
export ATLASSIAN_ROVO_TOKEN="$TOKEN"

echo "Token exported as ATLASSIAN_ROVO_TOKEN"
echo ""
echo "Next steps:"
echo "  1. Update docker-compose.yml to include:"
echo "     environment:"
echo "       ATLASSIAN_ROVO_TOKEN: \${ATLASSIAN_ROVO_TOKEN}"
echo ""
echo "  2. Or add to .env file:"
echo "     ATLASSIAN_ROVO_TOKEN=$TOKEN"
echo ""
echo "  3. Restart Letta:"
echo "     docker-compose restart letta"
echo ""
echo "  4. Reconfigure MCP servers:"
echo "     docker-compose exec letta python /app/tools/letta/configure_mcp_servers.py"
echo ""

