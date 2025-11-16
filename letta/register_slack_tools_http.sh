#!/bin/bash
#
# Register Slack Analytics Tools with Letta via HTTP API
# Usage: ./register_slack_tools_http.sh agent-6eb765bf-7268-4f6d-a380-c527c9c53000
#

LETTA_BASE="${LETTA_BASE_URL:-http://localhost:8283}"
AGENT_ID="${1:-${LETTA_AGENT_ID}}"

if [ -z "$AGENT_ID" ]; then
    echo "❌ Error: No agent ID provided"
    echo "Usage: $0 <agent-id>"
    echo "   or: LETTA_AGENT_ID=<agent-id> $0"
    exit 1
fi

echo "============================================================"
echo "Slack Analytics Tools Registration"
echo "============================================================"
echo ""
echo "Letta Base: $LETTA_BASE"
echo "Agent ID: $AGENT_ID"
echo ""

# Tool 1: Trigger Export
echo "→ Registering trigger_slack_analytics_export..."

SOURCE_CODE_1='import os
import subprocess

def trigger_slack_analytics_export(analytics_type: str = "channels") -> str:
    """
    Trigger a Slack analytics CSV export.
    
    Args:
        analytics_type: Type of analytics (channels, members, overview, all)
    
    Returns:
        Success message with instructions
    """
    SCRIPT = "/Users/dorseyhomeserver/ai-PA/scripts/slack_analytics_trigger_export.py"
    AUTH = "/Users/dorseyhomeserver/ai-PA/slack_auth_state.json"
    
    if analytics_type not in ["channels", "members", "overview", "all"]:
        return f"❌ Invalid type: {analytics_type}"
    
    try:
        result = subprocess.run(
            ["python3", SCRIPT, "--type", analytics_type, "--headless", "--auth-file", AUTH],
            capture_output=True, text=True, timeout=60
        )
        
        if result.returncode == 0:
            return f"✓ Triggered {analytics_type} export. CSV will be in Slack Files in 1-2 min. Use list_recent_slack_files() to find it."
        else:
            return f"❌ Failed: {result.stderr}"
    except Exception as e:
        return f"❌ Error: {str(e)}"
'

TOOL1_JSON=$(cat <<EOF
{
  "source_code": $(echo "$SOURCE_CODE_1" | jq -Rs .),
  "tags": ["slack", "analytics"],
  "name": "trigger_slack_analytics_export"
}
EOF
)

TOOL1_ID=$(curl -s -X POST "$LETTA_BASE/v1/tools/" \
  -H "Content-Type: application/json" \
  -d "$TOOL1_JSON" | jq -r '.id // empty')

if [ -n "$TOOL1_ID" ]; then
    echo "✓ Created tool: trigger_slack_analytics_export (ID: $TOOL1_ID)"
else
    echo "⚠ Tool may already exist or creation failed"
    TOOL1_ID=$(curl -s "$LETTA_BASE/v1/tools/" | jq -r '.tools[] | select(.name == "trigger_slack_analytics_export") | .id' | head -1)
    if [ -n "$TOOL1_ID" ]; then
        echo "→ Found existing tool ID: $TOOL1_ID"
    fi
fi

# Tool 2: List Files
echo "→ Registering list_recent_slack_files..."

SOURCE_CODE_2='import os
import requests
import json
from datetime import datetime

def list_recent_slack_files(types: str = "csv", count: int = 10) -> str:
    """
    List recent files in Slack workspace.
    
    Args:
        types: File types to filter (csv, pdf, all)
        count: Number of files (max 100)
    
    Returns:
        JSON string with recent files
    """
    TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    if not TOKEN:
        return "❌ SLACK_MCP_XOXP_TOKEN not set"
    
    try:
        params = {"count": min(count, 100)}
        if types != "all":
            params["types"] = types
        
        r = requests.get(
            "https://slack.com/api/files.list",
            headers={"Authorization": f"Bearer {TOKEN}"},
            params=params,
            timeout=10
        )
        data = r.json()
        
        if not data.get("ok"):
            return f"❌ API error: {data.get('"'error'"')}"
        
        files = []
        for f in data.get("files", []):
            files.append({
                "id": f.get("id"),
                "name": f.get("name"),
                "created": datetime.fromtimestamp(f.get("created", 0)).isoformat(),
                "url": f.get("url_private_download")
            })
        
        return json.dumps({"count": len(files), "files": files}, indent=2)
    except Exception as e:
        return f"❌ Error: {str(e)}"
'

TOOL2_JSON=$(cat <<EOF
{
  "source_code": $(echo "$SOURCE_CODE_2" | jq -Rs .),
  "tags": ["slack", "analytics"],
  "name": "list_recent_slack_files"
}
EOF
)

TOOL2_ID=$(curl -s -X POST "$LETTA_BASE/v1/tools/" \
  -H "Content-Type: application/json" \
  -d "$TOOL2_JSON" | jq -r '.id // empty')

if [ -n "$TOOL2_ID" ]; then
    echo "✓ Created tool: list_recent_slack_files (ID: $TOOL2_ID)"
else
    echo "⚠ Tool may already exist or creation failed"
    TOOL2_ID=$(curl -s "$LETTA_BASE/v1/tools/" | jq -r '.tools[] | select(.name == "list_recent_slack_files") | .id' | head -1)
    if [ -n "$TOOL2_ID" ]; then
        echo "→ Found existing tool ID: $TOOL2_ID"
    fi
fi

echo ""
echo "→ Attaching tools to agent $AGENT_ID..."

# Get current agent tools
CURRENT_TOOLS=$(curl -s "$LETTA_BASE/v1/agents/$AGENT_ID" | jq -r '.tools[]')

# Build new tools array (merge with existing)
NEW_TOOLS="["
FIRST=true
for TOOL_ID in $CURRENT_TOOLS; do
    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        NEW_TOOLS="${NEW_TOOLS},"
    fi
    NEW_TOOLS="${NEW_TOOLS}\"$TOOL_ID\""
done

# Add new tools if we have IDs
for NEW_ID in $TOOL1_ID $TOOL2_ID; do
    if [ -n "$NEW_ID" ]; then
        # Check if already in list
        if echo "$CURRENT_TOOLS" | grep -q "$NEW_ID"; then
            echo "→ Tool $NEW_ID already attached"
        else
            if [ "$FIRST" = false ]; then
                NEW_TOOLS="${NEW_TOOLS},"
            fi
            NEW_TOOLS="${NEW_TOOLS}\"$NEW_ID\""
            FIRST=false
        fi
    fi
done
NEW_TOOLS="${NEW_TOOLS}]"

# Update agent with new tools
PATCH_JSON=$(cat <<EOF
{
  "tools": $NEW_TOOLS
}
EOF
)

curl -s -X PATCH "$LETTA_BASE/v1/agents/$AGENT_ID" \
  -H "Content-Type: application/json" \
  -d "$PATCH_JSON" > /dev/null

echo "✓ Tools attached to agent"

echo ""
echo "============================================================"
echo "✓ Registration Complete"
echo "============================================================"
echo ""
echo "Your agent now has these Slack analytics tools:"
echo "  • trigger_slack_analytics_export - Trigger CSV export"
echo "  • list_recent_slack_files - List recent files in Slack"
echo ""
echo "Try asking your agent:"
echo '  "Can you trigger a channels analytics export from Slack?"'
echo '  "List the recent CSV files from Slack"'
echo ""


