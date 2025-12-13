# Slack Analytics Export Troubleshooting Guide

## Quick Checks

### 1. Verify Service is Running
```bash
docker ps | grep slack-analytics-mcp-server
docker logs slack-analytics-mcp-server --tail 20
```

### 2. Test Endpoint Directly
```bash
# From your host machine
curl -X POST http://localhost:8097/trigger-export \
  -H "Content-Type: application/json" \
  -d '{"analytics_type":"channels","days_ago":2,"date_range_days":1}'

# From Letta container
docker exec ai-pa-letta-1 curl -X POST http://slack-analytics-mcp-server:8087/trigger-export \
  -H "Content-Type: application/json" \
  -d '{"analytics_type":"channels","days_ago":2,"date_range_days":1}'
```

### 3. Check Service Health
```bash
curl http://localhost:8097/health
# Should return: {"status":"healthy","service":"slack-analytics-export","script":true,"auth_file":true}
```

## Common Issues

### Issue 1: Export Triggered But CSV Not Appearing

**Symptoms:**
- Tool returns success message
- Service logs show "Export triggered"
- No CSV file appears in Slack Files

**Possible Causes:**
1. **Slack Processing Delay**: Slack can take 1-5 minutes to generate the CSV
2. **Date Range Issue**: The date range might be too recent (Slack analytics have a delay)
3. **Authentication Expired**: Slack session may have expired

**Solutions:**
```bash
# Check recent logs for errors
docker logs slack-analytics-mcp-server --tail 100 | grep -i error

# Verify authentication file exists
docker exec slack-analytics-mcp-server ls -la /app/slack_auth_state.json

# Check screenshots to see what happened
docker exec slack-analytics-mcp-server ls -la /app/slack_analytics_screenshots/ | tail -5
```

### Issue 2: Connection Refused

**Symptoms:**
- Tool returns "Connection refused" error
- Network error when calling endpoint

**Solutions:**
```bash
# Verify service is on the same network
docker network inspect pa-internal | grep -A 5 slack-analytics

# Test connectivity from Letta container
docker exec ai-pa-letta-1 curl -v http://slack-analytics-mcp-server:8087/health

# Check if service is listening
docker exec slack-analytics-mcp-server netstat -tlnp | grep 8087
```

### Issue 3: Script Execution Fails

**Symptoms:**
- Service returns error
- Logs show script execution failure
- Return code is non-zero

**Solutions:**
```bash
# Check full service logs
docker logs slack-analytics-mcp-server --tail 200

# Verify script exists
docker exec slack-analytics-mcp-server ls -la /app/slack_analytics_with_dates.py

# Test script manually
docker exec slack-analytics-mcp-server python /app/slack_analytics_with_dates.py \
  --type channels \
  --start-date 2025-12-09 \
  --end-date 2025-12-09 \
  --headless \
  --auth-file /app/slack_auth_state.json
```

### Issue 4: Timeout Errors

**Symptoms:**
- Request times out after 90-120 seconds
- Service returns 504 error

**Solutions:**
```bash
# Check if script is hanging
docker exec slack-analytics-mcp-server ps aux | grep python

# Increase timeout in docker-compose.yml
# SLACK_ANALYTICS_TIMEOUT=180

# Check browser/Playwright issues
docker logs slack-analytics-mcp-server | grep -i playwright
docker logs slack-analytics-mcp-server | grep -i browser
```

## Detailed Diagnostics

### Check Tool Response
When the tool runs, it should return a JSON response. Check what the agent is actually receiving:

```python
# The tool should return something like:
{
  "success": true,
  "analytics_type": "channels",
  "date_range": {"start": "2025-12-09", "end": "2025-12-09"},
  "message": "✓ Export triggered for 2025-12-09 to 2025-12-09. CSV will be available in Slack shortly.",
  "stdout": "..."
}
```

### Verify Export Actually Happened
1. **Check Slack Files**: Go to Slack → Files → Filter by CSV
2. **Look for recent files**: Files are named like `channels-YYYY-MM-DD.csv`
3. **Check file timestamp**: Should be within 1-5 minutes of trigger

### Check Screenshots
The service saves screenshots of the automation process:

```bash
# List recent screenshots
docker exec slack-analytics-mcp-server ls -lt /app/slack_analytics_screenshots/ | head -10

# Copy a screenshot to inspect
docker cp slack-analytics-mcp-server:/app/slack_analytics_screenshots/slack_channels_after_dates_*.png ./
```

Screenshots can show:
- Whether the date picker worked correctly
- If the Export CSV button was clicked
- Any error dialogs or modals

## Step-by-Step Debugging

### Step 1: Verify Service Health
```bash
curl http://localhost:8097/health
```
Expected: `{"status":"healthy","service":"slack-analytics-export","script":true,"auth_file":true}`

### Step 2: Test Endpoint
```bash
curl -X POST http://localhost:8097/trigger-export \
  -H "Content-Type: application/json" \
  -d '{"analytics_type":"channels","days_ago":3,"date_range_days":1}' \
  -v
```
Check for:
- HTTP 200 response
- `"success": true` in response
- Detailed stdout showing automation steps

### Step 3: Check Logs
```bash
docker logs slack-analytics-mcp-server --tail 50 --follow
```
Watch for:
- "Triggering Slack analytics export"
- "Slack analytics export succeeded" or "failed"
- Any error messages

### Step 4: Verify Script Execution
```bash
# Check if script ran
docker logs slack-analytics-mcp-server | grep -A 10 "Triggering Slack"

# Check return code
docker logs slack-analytics-mcp-server | grep "returncode"
```

### Step 5: Check Slack Files
1. Open Slack web interface
2. Go to Files
3. Filter by CSV files
4. Look for files created in the last 10 minutes
5. Check file names match the date range requested

## Environment Variables

Check these are set correctly in `docker-compose.yml`:

```yaml
SLACK_ANALYTICS_SCRIPT_PATH=/app/slack_analytics_with_dates.py
SLACK_ANALYTICS_AUTH_FILE=/app/slack_auth_state.json
SLACK_ANALYTICS_SCREENSHOT_DIR=/app/slack_analytics_screenshots
SLACK_ANALYTICS_TIMEOUT=150
SLACK_ANALYTICS_HEADLESS=true
```

## Manual Script Test

If the service isn't working, test the script directly:

```bash
docker exec -it slack-analytics-mcp-server bash

# Inside container
python /app/slack_analytics_with_dates.py \
  --type channels \
  --start-date 2025-12-09 \
  --end-date 2025-12-09 \
  --headless \
  --auth-file /app/slack_auth_state.json \
  --screenshot-dir /app/slack_analytics_screenshots
```

## Getting Help

If issues persist, collect this information:

1. **Service logs**: `docker logs slack-analytics-mcp-server --tail 200`
2. **Health check**: `curl http://localhost:8097/health`
3. **Test response**: Full JSON response from test endpoint call
4. **Screenshots**: Latest screenshot from `/app/slack_analytics_screenshots/`
5. **Tool response**: What the Letta tool actually returned to the agent

