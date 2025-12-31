# Get Cookies from Browser After OAuth

## Step-by-Step Instructions

### Step 1: Complete OAuth Flow
1. Open: `https://mcp.atlassian.com/v1/sse` in your browser
2. Complete the OAuth authorization:
   - Log in to Atlassian
   - Approve the authorization
   - Select apps (Jira, Confluence)
3. **Important**: Stay on the page after authorization completes

### Step 2: Extract Cookies

**Method A: Using DevTools**
1. Press `F12` (or `Cmd+Option+I` on Mac) to open DevTools
2. Go to **Application** tab (Chrome) or **Storage** tab (Firefox)
3. In the left sidebar, expand **Cookies**
4. Click on `https://mcp.atlassian.com`
5. You'll see all cookies for that domain
6. Copy the cookie values (especially ones with names like `session`, `token`, `auth`, etc.)

**Method B: Using Browser Console**
1. Open DevTools Console (F12 → Console tab)
2. Paste this and press Enter:
```javascript
// Get all cookies for mcp.atlassian.com
const cookies = document.cookie;
console.log('All cookies:', cookies);

// Format for curl/requests
const cookieString = document.cookie.split(';').map(c => c.trim()).join('; ');
console.log('\nCookie string for requests:');
console.log(cookieString);

// Copy this output
```

### Step 3: Save Cookies

Save the cookies to a file:
```bash
echo "YOUR_COOKIE_STRING_HERE" > ~/.atlassian-mcp-cookies.txt
```

### Step 4: Test with Cookies

Run the test script:
```bash
node get-token-from-session.js
```

This will use the cookies to connect to the MCP server.

## Alternative: Use Browser Extension

You can also use a browser extension like:
- **EditThisCookie** - to export cookies
- **Cookie-Editor** - to view and copy cookies

## What Cookies to Look For

Look for cookies with names like:
- `session`
- `sessionid`
- `token`
- `access_token`
- `auth`
- `oauth`
- Any cookie with a long random-looking value

Copy ALL cookies from `mcp.atlassian.com` - you might need multiple ones.

