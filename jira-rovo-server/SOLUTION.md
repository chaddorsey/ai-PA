# Solution: Using Atlassian Rovo MCP with Letta

## The Challenge

The Atlassian Rovo MCP server uses OAuth 2.1 with server-side session management. The OAuth callback goes to the MCP server itself (`https://mcp.atlassian.com/v1/callback`), not to a local callback, so we can't directly capture the token.

## The Solution

Since the MCP server maintains the session server-side, you have two options:

### Option 1: Use MCP Server Directly (Recommended)

Configure Letta to connect to the MCP server. When Letta connects:
1. If you're not authenticated, the MCP server will redirect to OAuth
2. Complete the OAuth flow in the browser
3. The MCP server stores your session
4. Letta can then use the MCP server

**Configuration:**
```python
# In letta/configure_mcp_servers.py
"jira-rovo-tools": {
    "server_name": "jira-rovo-tools",
    "type": "streamable_http",
    "server_url": "https://mcp.atlassian.com/v1/sse",
    "auth_header": None,
    "auth_token": None,
    "custom_headers": {
        "Content-Type": "application/json"
    }
}
```

**Steps:**
1. Add this configuration to Letta
2. When Letta tries to connect, it should trigger OAuth
3. Complete OAuth in the browser
4. Letta should then be able to use the MCP server

### Option 2: Extract Token from Browser (If Needed)

If Letta requires a direct token, you can try to extract it:

1. **Complete OAuth through browser:**
   - Open: `https://mcp.atlassian.com/v1/sse`
   - Complete the OAuth flow
   - The MCP server stores your session

2. **Extract token from browser:**
   - Open DevTools → Network tab
   - Look for requests to `mcp.atlassian.com`
   - Check for `Authorization: Bearer` headers
   - Or check cookies/localStorage for token values

3. **Use the token:**
   ```python
   "jira-rovo-tools": {
       "server_name": "jira-rovo-tools",
       "type": "streamable_http",
       "server_url": "https://mcp.atlassian.com/v1/sse",
       "custom_headers": {
           "Content-Type": "application/json",
           "Authorization": f"Bearer {extracted_token}"
       }
   }
   ```

## Current Status

- ✅ Site admin has authorized "Atlassian MCP" for `concord-consortium.atlassian.net`
- ✅ OAuth URLs are being generated (but expire after ~1 hour)
- ⚠️ Need to complete OAuth flow quickly before JWT expires
- ⚠️ Token is stored server-side, not directly accessible

## Next Steps

1. **Try Option 1 first** - Configure Letta to use the MCP server directly
2. If Letta doesn't trigger OAuth automatically, complete it manually:
   - Open `https://mcp.atlassian.com/v1/sse` in browser
   - Complete OAuth authorization
   - Then Letta should be able to connect

3. **If you need the actual token**, use browser DevTools to extract it after completing OAuth

## Testing

After completing OAuth, test the connection:

```bash
# Should work if session is established
curl "https://mcp.atlassian.com/v1/sse" \
  -H "Accept: text/event-stream" \
  -v
```

If you get 401, the session might not be established. Try completing OAuth again.

