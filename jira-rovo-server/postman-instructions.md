# Using Postman to Trigger OAuth

Based on [Atlassian's documentation](https://support.atlassian.com/atlassian-rovo-mcp-server/docs/using-with-other-supported-mcp-clients/), you can use Postman as an MCP client to trigger OAuth.

## Postman Setup

### Step 1: Make MCP Initialize Request

1. Open Postman
2. Create a new request
3. Set method to **POST**
4. Set URL to: `https://mcp.atlassian.com/v1/mcp`
5. Go to **Headers** tab:
   - `Content-Type`: `application/json`
   - `Accept`: `application/json`
6. Go to **Body** tab, select **raw** and **JSON**, paste:

```json
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

7. Click **Send**

### Step 2: Check Response

The response should either:
- Return an OAuth URL in the response body
- Return a redirect (check response headers for `Location`)
- Return an error with OAuth instructions

### Step 3: Complete OAuth

1. If you get an OAuth URL, open it in your browser
2. Complete the authorization
3. Check Postman's **Console** (View → Show Postman Console) for any redirects or tokens

### Step 4: Extract Token

After OAuth completes:
1. Check browser DevTools → Network tab
2. Look for requests to `mcp.atlassian.com`
3. Find `Authorization: Bearer <token>` in request headers
4. Copy the token

## Alternative: Use SSE Endpoint

Try the SSE endpoint instead:

1. Method: **GET**
2. URL: `https://mcp.atlassian.com/v1/sse`
3. Headers:
   - `Accept`: `text/event-stream`
   - `Cache-Control`: `no-cache`
4. Click **Send**

This might trigger OAuth redirect automatically.

