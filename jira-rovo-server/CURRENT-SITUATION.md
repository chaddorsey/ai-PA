# Current Situation: OAuth Token for Atlassian Rovo MCP

## The Core Problem

The Atlassian Rovo MCP server:
- ✅ Requires OAuth 2.1 authentication
- ✅ Is configured in Letta
- ❌ **Does NOT provide OAuth URLs in error responses**
- ❌ **Does NOT trigger OAuth automatically when accessed**

## What We've Tried

1. ✅ Direct browser access → 401 error, no OAuth URL
2. ✅ MCP initialize requests → 401 error, no OAuth URL  
3. ✅ SSE endpoint → 401 error, no OAuth URL
4. ✅ Letta interface → Doesn't trigger OAuth
5. ✅ Postman → Will get same 401, no OAuth URL

## What Postman Will Show

When you use Postman to make the MCP initialize request:

**Request:**
```
POST https://mcp.atlassian.com/v1/mcp
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "postman-client",
      "version": "1.0.0"
    }
  }
}
```

**Response:**
```
Status: 401 Unauthorized
WWW-Authenticate: Bearer realm="OAuth"

{
  "error": "invalid_token",
  "error_description": "Missing or invalid access token"
}
```

**No OAuth URL provided.**

## Why This Happens

According to [Atlassian's documentation](https://support.atlassian.com/atlassian-rovo-mcp-server/docs/using-with-other-supported-mcp-clients/), the client should "complete the OAuth login when prompted" - but the server isn't prompting us with an OAuth URL.

The OAuth URL needs to include:
- A `context` parameter (JWT) that the MCP server generates
- Specific state and redirect parameters
- The MCP server must initiate the flow

## Possible Solutions

### Option 1: Check Letta's OAuth Support
Letta might have built-in OAuth 2.1 support that we haven't enabled:

1. Check Letta documentation for OAuth configuration
2. Look for environment variables or config for OAuth
3. Try using a tool through Letta's interface - it might trigger OAuth

### Option 2: Contact Atlassian Support
Ask Atlassian:
- How to get the OAuth URL for the Rovo MCP server
- If there's a specific endpoint or method to request OAuth
- If the MCP server should be providing OAuth URLs in responses

### Option 3: Use Browser DevTools After Any OAuth
If you can trigger OAuth through any method:
1. Complete OAuth in browser
2. Open DevTools → Network tab
3. Find requests to `mcp.atlassian.com`
4. Extract `Authorization: Bearer <token>` from headers
5. Save token and use it

### Option 4: Check MCP Protocol Specification
The MCP protocol might have a specific method to request OAuth:
- Look for `mcp/oauth/request` or similar
- Check if there's a capabilities negotiation that triggers OAuth
- See if SSE events contain OAuth URLs

## Next Steps

1. **Try Postman anyway** - Import the collection and see what you get
2. **Check Letta logs** - See if there are any OAuth-related messages
3. **Review Letta docs** - Look for OAuth 2.1 configuration options
4. **Contact Atlassian** - Ask about OAuth URL generation

## Files Created

- `Atlassian-Rovo-MCP.postman_collection.json` - Postman collection
- `POSTMAN-GUIDE.md` - Step-by-step Postman instructions
- `POSTMAN-OAUTH-SETUP.md` - OAuth 2.0 configuration guide
- `mcp-initialize.js` - Node.js MCP client
- `mcp-sse-client.js` - SSE event stream client

All scripts are ready to use, but they'll all get the same 401 response without an OAuth URL.

