# Postman OAuth 2.1 Setup for Atlassian Rovo MCP

Based on [Atlassian's documentation](https://support.atlassian.com/rovo/docs/authentication-and-authorization/), here's how to set up OAuth in Postman.

## Step 1: Configure OAuth 2.0 in Postman

1. Open Postman
2. Create a new request (or use the imported collection)
3. Go to the **Authorization** tab
4. Select **OAuth 2.0** as the type
5. Click **Get New Access Token**

## Step 2: Fill in OAuth Details

Use these values:

- **Token Name**: `Atlassian Rovo MCP`
- **Grant Type**: `Authorization Code`
- **Callback URL**: `http://localhost:3334/oauth/callback`
  - ⚠️ **Note**: The MCP server uses `https://mcp.atlassian.com/v1/callback`, but Postman needs a localhost callback. You may need to set up a local callback server.
- **Auth URL**: `https://auth.atlassian.com/authorize`
- **Access Token URL**: `https://auth.atlassian.com/oauth/token`
- **Client ID**: `pVrZtjGOkBraHr0ge4iVlstqGVRJfi3` (from previous attempts)
- **Client Secret**: ⚠️ **We don't have this** - this might be the issue
- **Scope**: 
  ```
  offline_access read:comment:confluence read:confluence-user read:hierarchical-content:confluence read:jira-work read:me read:page:confluence read:space:confluence search:confluence write:comment:confluence write:jira-work write:page:confluence
  ```
- **State**: (Postman can generate this)
- **Client Authentication**: `Send as Basic Auth header`

## Step 3: The Problem

The MCP server's OAuth flow requires:
1. A **context/JWT parameter** that the MCP server generates
2. The OAuth URL must be initiated by the MCP server, not manually constructed

This means Postman's standard OAuth 2.0 flow might not work directly because:
- We don't have the Client Secret
- The MCP server needs to generate the OAuth URL with a specific context

## Alternative: Use Postman to Capture Token After Manual OAuth

If you can get the OAuth URL from somewhere else (like Letta's interface or a script), you can:

1. Complete OAuth in the browser
2. Use Postman to make authenticated requests with the token
3. Extract the token from browser DevTools and use it in Postman

## Step 4: Test with Token

Once you have a token:

1. In Postman, go to **Authorization** tab
2. Select **Bearer Token**
3. Paste your token
4. Make a request to: `https://mcp.atlassian.com/v1/mcp`
5. Body: MCP initialize request (see collection)

## The Real Solution

Since the MCP server doesn't provide OAuth URLs automatically, we need to:

1. **Check if Letta has OAuth support** - Letta might handle OAuth automatically when you try to use a tool
2. **Use browser DevTools** - After any OAuth flow completes, capture the token
3. **Contact Atlassian Support** - Ask how to get the OAuth URL for the MCP server

## Next Steps

Try this:
1. Open Letta web interface: `http://localhost:8283`
2. Try to use a Jira/Confluence tool
3. See if Letta opens OAuth automatically
4. If not, check Letta's documentation for OAuth 2.1 support

