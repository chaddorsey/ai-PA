# How to Extract Token from Browser After OAuth

Since the OAuth callback goes to the MCP server (`https://mcp.atlassian.com/v1/callback`), 
the token is stored server-side. However, you can extract it from your browser session.

## Method 1: Browser DevTools Network Tab

1. Open browser DevTools (F12 or Cmd+Option+I)
2. Go to the **Network** tab
3. Complete the OAuth authorization
4. Look for the callback request to `https://mcp.atlassian.com/v1/callback`
5. Check the **Response** or **Headers** for the token
6. Or check if there's a subsequent request that includes an `Authorization: Bearer` header

## Method 2: Browser Application/Storage Tab

1. After completing OAuth, go to DevTools
2. Open the **Application** tab (Chrome) or **Storage** tab (Firefox)
3. Check:
   - **Cookies** for `mcp.atlassian.com`
   - **Local Storage** for `mcp.atlassian.com`
   - **Session Storage** for `mcp.atlassian.com`
4. Look for any token values

## Method 3: Test MCP Server Connection

After authorization, the MCP server should have your session. Test it:

```bash
# This should work if you're authenticated
curl "https://mcp.atlassian.com/v1/sse" \
  -H "Accept: text/event-stream" \
  -H "Cookie: [your browser cookies]"
```

## Method 4: Use Browser Extension

Install a browser extension that can capture OAuth tokens:
- OAuth Token Extractor
- ModHeader (to see request headers)

## Method 5: Configure Letta to Use MCP Server Directly

Since the MCP server maintains the session, you might not need the token directly.
Configure Letta to connect to the MCP server, and it should handle authentication:

```python
# In letta/configure_mcp_servers.py
"jira-rovo-tools": {
    "server_name": "jira-rovo-tools",
    "type": "streamable_http",
    "server_url": "https://mcp.atlassian.com/v1/sse",
    # No token needed - MCP server handles session
}
```

Then when Letta connects, if you're not authenticated, it will trigger OAuth automatically.

