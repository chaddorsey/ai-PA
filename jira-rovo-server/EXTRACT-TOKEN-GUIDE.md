# Step-by-Step Guide to Extract OAuth Token

## Quick Method: Browser DevTools

### Step 1: Open Browser DevTools
1. Open your browser
2. Press `F12` or `Cmd+Option+I` (Mac) to open DevTools
3. Go to the **Network** tab
4. Make sure "Preserve log" is checked

### Step 2: Complete OAuth Flow
1. Navigate to: `https://mcp.atlassian.com/v1/sse`
2. Complete the OAuth authorization
3. Watch the Network tab for requests

### Step 3: Find the Token
Look for these in the Network tab:

**Option A: Check Request Headers**
- Find any request to `mcp.atlassian.com`
- Click on it
- Go to "Headers" tab
- Look for `Authorization: Bearer <token>`
- Copy the token after "Bearer "

**Option B: Check Response**
- Find the request to `mcp.atlassian.com/v1/callback` or similar
- Click on it
- Go to "Response" or "Preview" tab
- Look for `"access_token": "..."` 
- Copy the token value

**Option C: Check URL**
- After OAuth, check the current URL
- Look for `access_token=` in the URL
- Copy the token value

### Step 4: Save the Token
```bash
echo "YOUR_TOKEN_HERE" > ~/.atlassian-rovo-token.txt
```

## Alternative: Browser Console Script

1. Complete OAuth flow in browser
2. Open DevTools Console (F12 → Console tab)
3. Copy and paste the contents of `browser-console-extract.js`
4. Press Enter
5. The script will search for tokens and display them

## Alternative: Use Proxy Server

Run the proxy server to intercept requests:

```bash
node extract-token.js
```

Then configure your browser to use the proxy, or use it with curl.

## Testing the Token

Once you have the token, test it:

```bash
TOKEN=$(cat ~/.atlassian-rovo-token.txt)
curl "https://mcp.atlassian.com/v1/sse" \
  -H "Accept: text/event-stream" \
  -H "Authorization: Bearer $TOKEN"
```

If you get a 200 response (not 401), the token works!

