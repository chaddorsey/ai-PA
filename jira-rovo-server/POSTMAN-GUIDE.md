# Postman Guide: Getting OAuth Token for Atlassian Rovo MCP

## Step 1: Import the Collection

1. Open Postman
2. Click **Import** button (top left)
3. Select the file: `Atlassian-Rovo-MCP.postman_collection.json`
4. Click **Import**

## Step 2: Try MCP Initialize Request

1. In Postman, open the collection **"Atlassian Rovo MCP"**
2. Click on **"MCP Initialize"** request
3. Click **Send**

### What to Look For:

- **Status Code**: Check if it's 401, 302 (redirect), or 200
- **Response Body**: Look for any OAuth URLs or instructions
- **Response Headers**: Check for `Location` header (redirect)
- **Postman Console**: View → Show Postman Console to see full request/response

### Expected Responses:

#### If you get 401:
- The server requires OAuth but isn't providing the URL automatically
- Check the response body for any OAuth-related information
- Check the `WWW-Authenticate` header for OAuth realm info

#### If you get 302/303/307:
- This is a redirect to OAuth!
- Check the `Location` header
- Copy the URL and open it in your browser

#### If you get 200:
- Check the response body for OAuth URL or next steps

## Step 3: Try SSE Endpoint

1. Click on **"SSE Endpoint"** request
2. Click **Send**

Note: Postman may not display event streams properly. Check the **Console** for full response.

## Step 4: Check Letta Logs

If Postman doesn't trigger OAuth, check if Letta is getting different responses:

```bash
docker logs ai-pa-letta-1 --tail 100 | grep -i "rovo\|atlassian\|oauth"
```

## Step 5: Manual OAuth URL Construction

If neither approach works, we may need to construct the OAuth URL manually. The Atlassian OAuth 2.1 flow typically uses:

- **Authorization URL**: `https://api.atlassian.com/oauth2/authorize`
- **Client ID**: `pVrZtjGOkBraHr0ge4iVlstqGVRJfi3` (from previous attempts)
- **Redirect URI**: `https://mcp.atlassian.com/v1/callback`

But we need the proper `state` and `context` parameters from the MCP server.

## Step 6: Extract Token After OAuth

Once you complete OAuth (through any method):

1. **Open Browser DevTools** (F12)
2. Go to **Network** tab
3. Look for requests to `mcp.atlassian.com`
4. Find requests with `Authorization: Bearer <token>` header
5. Copy the token value
6. Save it:
   ```bash
   echo "YOUR_TOKEN_HERE" > ~/.atlassian-rovo-token.txt
   ```

## Alternative: Use Letta's Interface

1. Open `http://localhost:8283` in your browser
2. Navigate to MCP Servers / Tools section
3. Find **"jira-rovo-tools"**
4. Try to use a tool or connect
5. This might trigger OAuth in Letta's interface
6. Complete OAuth when prompted
7. Check browser DevTools for token

## Troubleshooting

### "Invalid token" errors:
- This is expected - we're trying to trigger OAuth
- The server should provide an OAuth URL, but it's not doing so automatically

### No OAuth URL in response:
- The MCP server may require a specific client configuration
- Try checking Letta's documentation for OAuth 2.1 support
- Or contact Atlassian support about OAuth URL generation

### Postman Console Tips:
- View → Show Postman Console
- This shows full HTTP request/response details
- Look for redirects, headers, and response bodies

## Next Steps

After you try Postman:
1. Share what response you get (status code, body, headers)
2. We can analyze it to find the OAuth URL
3. Or we can try a different approach

