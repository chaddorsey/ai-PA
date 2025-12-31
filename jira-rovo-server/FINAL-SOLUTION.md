# Final Solution: Getting Atlassian Rovo MCP Token

## The Core Problem

The Atlassian Rovo MCP server:
- Requires OAuth 2.1 authentication
- Stores sessions server-side (callback goes to `https://mcp.atlassian.com/v1/callback`)
- Only triggers OAuth when accessed through a proper MCP client
- Does NOT trigger OAuth when you visit the URL directly in a browser

## Why Direct Browser Access Doesn't Work

When you visit `https://mcp.atlassian.com/v1/sse` directly:
- The server returns `401 Invalid token`
- It does NOT redirect to OAuth
- It expects an MCP client to initiate the OAuth flow

## Solution Options

### Option 1: Use Letta's Web Interface (Try This First)

1. Open Letta web UI: `http://localhost:8283`
2. Navigate to MCP Servers / Tool Manager
3. Add new MCP server:
   - Type: Streamable HTTP
   - URL: `https://mcp.atlassian.com/v1/sse`
4. When you save/connect, Letta should trigger OAuth
5. Complete OAuth in the browser that opens
6. Letta should capture and use the session

**If this doesn't work**, Letta may not support OAuth 2.1 for external servers yet.

### Option 2: Install and Use MCP CLI Tools

The documentation mentions MCP CLI tools. Try installing:

```bash
# Try these packages
npm install -g @modelcontextprotocol/tools
npm install -g mcp
npm install -g @modelcontextprotocol/cli

# Or check what's available
npm search @modelcontextprotocol
```

Then use the CLI to connect:
```bash
mcp connect https://mcp.atlassian.com/v1/sse
# or
mcp-remote https://mcp.atlassian.com/v1/sse
```

### Option 3: Use Browser DevTools to Capture Token

After completing OAuth (through Letta or CLI):

1. Open DevTools (F12) → Network tab
2. Look for requests to `mcp.atlassian.com`
3. Check Request Headers for `Authorization: Bearer <token>`
4. Copy the token value
5. Save it: `echo "TOKEN" > ~/.atlassian-rovo-token.txt`

### Option 4: Use Atlassian API Directly (Bypass MCP Server)

Since your site admin has authorized the app, you might be able to use Atlassian's API directly:

1. Go to: https://developer.atlassian.com/console
2. Find the "Atlassian MCP" app
3. Check if there's a way to generate tokens
4. Or create your own OAuth app and use that instead

### Option 5: Check Letta Logs

If Letta is trying to connect but failing:

```bash
docker logs ai-pa-letta-1 --tail 100 | grep -i "rovo\|atlassian\|oauth"
```

This might show what's happening when Letta tries to connect.

## Current Configuration

I've added the Rovo server to `letta/configure_mcp_servers.py`:

```python
"jira-rovo-tools": {
    "server_name": "jira-rovo-tools",
    "type": "streamable_http",
    "server_url": "https://mcp.atlassian.com/v1/sse",
    "auth_header": None,
    "auth_token": os.getenv("ATLASSIAN_ROVO_TOKEN"),
    "custom_headers": {
        "Content-Type": "application/json"
    }
}
```

## Next Steps

1. **Try Letta's web interface first** - Add the server there and see if it triggers OAuth
2. **Check Letta logs** - See what happens when it tries to connect
3. **Try MCP CLI tools** - If available, use them to get the token
4. **Use browser DevTools** - If OAuth completes, capture token from network requests

The token extraction is challenging because the MCP server handles everything server-side. The best approach is to let Letta or an MCP client handle the OAuth flow automatically.

