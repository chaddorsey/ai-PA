# ✅ Success! Token Extracted

## Token Location

The access token has been extracted from `mcp-remote`'s storage and saved to:
```
~/.atlassian-rovo-token.txt
```

## Token Value

```
70121-cecc6a6e-e07f-440f-bcef-0e1b8d0fe274:qe97rgirCzv2J2Zm:dtuBjxRRDg55P0ZcnG-2VoqbVgQbMeza
```

## Next Steps

### 1. Add Token to Environment

Add to your `.env` file or `docker-compose.yml`:

```bash
ATLASSIAN_ROVO_TOKEN=70121-cecc6a6e-e07f-440f-bcef-0e1b8d0fe274:qe97rgirCzv2J2Zm:dtuBjxRRDg55P0ZcnG-2VoqbVgQbMeza
```

### 2. Update Letta Configuration

The configuration in `letta/configure_mcp_servers.py` has been updated to:
- Use the correct endpoint: `https://mcp.atlassian.com/v1/mcp`
- Set `auth_header` to `"Authorization"`
- Include the token in `custom_headers`

### 3. Restart Letta

```bash
docker-compose restart letta
```

### 4. Reconfigure MCP Servers

```bash
docker-compose exec letta python /app/tools/letta/configure_mcp_servers.py
```

Or if running locally:
```bash
cd letta
python configure_mcp_servers.py
```

## Token Expiry

The token expires in **3300 seconds** (55 minutes). When it expires, you'll need to:
1. Run `mcp-remote` again to refresh
2. Extract the new token using: `node jira-rovo-server/extract-token-from-mcp-auth.js`
3. Update the environment variable
4. Restart Letta

## Verification

After restarting Letta, you can verify the connection by:
1. Opening Letta web UI: `http://localhost:8283`
2. Checking if `jira-rovo-tools` appears in the MCP servers list
3. Trying to use a Jira or Confluence tool

