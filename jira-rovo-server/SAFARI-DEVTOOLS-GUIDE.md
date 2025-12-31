# Safari Developer Tools Guide

## Enable Developer Tools in Safari

1. **Open Safari Preferences**:
   - Safari → Settings (or Preferences)
   - Or press `Cmd + ,`

2. **Enable Developer Menu**:
   - Go to the **Advanced** tab
   - Check the box: **"Show features for web developers"**
   - Close Preferences

3. **Open Developer Tools**:
   - Safari menu → **Develop** → **Show Web Inspector**
   - Or press `Cmd + Option + I`
   - Or right-click on the page → **Inspect Element**

## Using Network Tab to Get Token

1. **Open Developer Tools** (`Cmd + Option + I`)

2. **Go to Network Tab**:
   - Click the **Network** tab in the Developer Tools window
   - If you don't see it, click the **>>** icon to show more tabs

3. **Filter Requests**:
   - In the search/filter box, type: `mcp.atlassian.com`
   - This will show only requests to the Atlassian MCP server

4. **Find the Token**:
   - Look for requests to `https://mcp.atlassian.com/v1/mcp` or `/v1/sse`
   - Click on one of these requests
   - In the **Headers** section, look for:
     - **Request Headers** → `Authorization: Bearer <token>`
   - The token is everything after "Bearer " (including the space)

5. **Copy the Token**:
   - Select and copy the token value
   - Save it: `echo "YOUR_TOKEN" > ~/.atlassian-rovo-token.txt`

## Alternative: Use Chrome/Edge for DevTools

If Safari's DevTools are difficult to use, you can:

1. **Open the OAuth URL in Chrome/Edge**:
   - Copy the OAuth URL from mcp-remote output
   - Open it in Chrome or Edge
   - Complete OAuth there
   - Use Chrome/Edge DevTools (F12) which are more familiar

2. **Or use the same browser session**:
   - If you completed OAuth in Safari, the token might be in cookies
   - But the Authorization header in Network tab is the easiest way

## Quick Steps Summary

1. Safari → Settings → Advanced → ✓ Show features for web developers
2. Safari → Develop → Show Web Inspector (or `Cmd + Option + I`)
3. Network tab → Filter: `mcp.atlassian.com`
4. Click request → Headers → Find `Authorization: Bearer <token>`
5. Copy token and save it

