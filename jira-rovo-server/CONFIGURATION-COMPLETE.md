# ✅ Atlassian Rovo MCP Server Configuration Complete

## Configuration Status

The Atlassian Rovo MCP server has been successfully configured in Letta!

### Server Details

- **Server Name**: `jira-rovo-tools`
- **Type**: `streamable_http`
- **URL**: `https://mcp.atlassian.com/v1/mcp`
- **Authentication**: Token configured in `custom_headers` with `Authorization: Bearer <token>`

### Current Configuration

```json
{
  "server_name": "jira-rovo-tools",
  "type": "streamable_http",
  "server_url": "https://mcp.atlassian.com/v1/mcp",
  "auth_header": null,
  "auth_token": null,
  "custom_headers": {
    "Content-Type": "application/json",
    "Authorization": "Bearer 70121-cecc6a6e-e07f-440f-bcef-0e1b8d0fe274:qe97rgirCzv2J2Zm:dtuBjxRRDg55P0ZcnG-2VoqbVgQbMeza"
  }
}
```

## Token Information

- **Token Location**: `~/.atlassian-rovo-token.txt`
- **Token Expiry**: 3300 seconds (55 minutes)
- **Token Source**: Extracted from `mcp-remote` storage at `~/.mcp-auth/mcp-remote-0.1.36/`

## Next Steps

1. **Test the Connection**:
   - Open Letta web UI: `http://localhost:8283`
   - Try using a Jira or Confluence tool
   - The server should be available in the tools list

2. **Refresh Token When Expired**:
   When the token expires (after ~55 minutes), you'll need to:
   ```bash
   # Extract new token from mcp-remote
   node jira-rovo-server/extract-token-from-mcp-auth.js
   
   # Update docker-compose.yml with new token
   # Restart Letta
   docker-compose restart letta
   
   # Reconfigure (delete and recreate)
   curl -X DELETE http://localhost:8283/v1/tools/mcp/servers/jira-rovo-tools
   # Then use PUT to recreate with new token
   ```

3. **Available Tools**:
   The server provides tools for:
   - Jira: Create issues, search, update, comment, etc.
   - Confluence: Create pages, search, get pages, etc.
   - Compass: Service components, dependencies, etc.

## Verification

To verify the server is working:

```bash
# Check server status
curl http://localhost:8283/v1/tools/mcp/servers/jira-rovo-tools

# Test connection (if endpoint exists)
curl http://localhost:8283/v1/tools/mcp/servers/jira-rovo-tools/test
```

## Troubleshooting

If the server doesn't work:

1. **Check token expiry**: The token expires after 55 minutes
2. **Verify token**: Make sure the token in `custom_headers` matches `~/.atlassian-rovo-token.txt`
3. **Check Letta logs**: `docker logs ai-pa-letta-1 --tail 50`
4. **Re-extract token**: Run `node jira-rovo-server/extract-token-from-mcp-auth.js` to get a fresh token

## Files Modified

- `docker-compose.yml`: Added `ATLASSIAN_ROVO_TOKEN` environment variable
- `letta/configure_mcp_servers.py`: Updated with correct endpoint and auth configuration
- Letta MCP server configuration: Added via API

