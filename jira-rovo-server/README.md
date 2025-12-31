# Atlassian Rovo MCP Server for Letta

This directory contains the integration between Letta and Atlassian's Rovo MCP Server, providing access to Jira, Confluence, and Compass tools.

## Architecture

```
Letta (Docker) 
    ↓ HTTP
host.docker.internal:9999 
    ↓ 
supergateway (Mac host)
    ↓ STDIO
mcp-remote 
    ↓ StreamableHTTP + OAuth
Atlassian MCP (https://mcp.atlassian.com/v1/mcp)
```

**Why this architecture?**
- Atlassian's MCP server uses OAuth 2.1 with server-side session management
- Letta's direct StreamableHTTP connection has timeout/compatibility issues
- `mcp-remote` handles OAuth properly and maintains the session
- `supergateway` bridges mcp-remote's STDIO to HTTP for Letta

## Quick Start

### 1. Initial OAuth Setup (one-time)

Complete OAuth authorization with Atlassian:

```bash
npx mcp-remote https://mcp.atlassian.com/v1/mcp
```

This opens a browser for OAuth. Complete the flow and approve scopes for Jira/Confluence.

### 2. Start the Service

**Option A: Manual start**
```bash
./supergateway-service.sh start
./supergateway-service.sh status
```

**Option B: Install as launchd service (auto-start on login)**
```bash
./install-launchd-service.sh
```

### 3. Letta Configuration

The MCP server is already configured in Letta as `atlassian-via-supergateway`:
- URL: `http://host.docker.internal:9999/mcp`
- Type: `streamable_http`

## Available Tools (28 total)

### Jira
- `createJiraIssue` - Create new issues
- `getJiraIssue` - Get issue details
- `editJiraIssue` - Update issues
- `searchJiraIssuesUsingJql` - Search with JQL
- `transitionJiraIssue` - Change issue status
- `addCommentToJiraIssue` - Add comments
- `addWorklogToJiraIssue` - Log work
- And more...

### Confluence
- `getConfluencePage` - Get page content
- `createConfluencePage` - Create pages
- `updateConfluencePage` - Update pages
- `getConfluenceSpaces` - List spaces
- `searchConfluenceUsingCql` - Search with CQL
- And more...

### Rovo Search
- `search` - Unified search across Jira and Confluence
- `fetch` - Get resources by ARI

## Token Management

OAuth tokens expire after ~55 minutes. The service handles this automatically:

- **Daemon mode** (`./supergateway-service.sh daemon`): Refreshes every 50 minutes
- **Manual refresh**: `./supergateway-service.sh refresh`

## Troubleshooting

### Check service status
```bash
./supergateway-service.sh status
```

### View logs
```bash
tail -f /tmp/supergateway-atlassian.log
```

### Test connection directly
```bash
curl -X POST "http://localhost:9999/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Re-authenticate (if token issues)
```bash
./supergateway-service.sh stop
npx mcp-remote https://mcp.atlassian.com/v1/mcp
# Complete OAuth in browser
./supergateway-service.sh start
```

### Check Letta tools
```bash
curl -s "http://localhost:8283/v1/mcp-servers/{server-id}/tools" | python3 -m json.tool
```

## Files

| File | Purpose |
|------|---------|
| `supergateway-service.sh` | Main service script (start/stop/refresh) |
| `install-launchd-service.sh` | Install as macOS startup service |
| `com.ai-pa.supergateway-atlassian.plist` | launchd configuration |
| `extract-token-from-mcp-auth.js` | Extract token from mcp-remote storage |

## Requirements

- Node.js 18+
- npm packages (global):
  - `mcp-remote` - OAuth and MCP client
  - `supergateway` - STDIO to HTTP bridge
- Atlassian Cloud site with MCP enabled
- Site admin approval for "Atlassian MCP" app

## References

- [Atlassian Rovo MCP Docs](https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/)
- [Troubleshooting Guide](https://support.atlassian.com/atlassian-rovo-mcp-server/docs/troubleshooting-and-verifying-your-setup/)
