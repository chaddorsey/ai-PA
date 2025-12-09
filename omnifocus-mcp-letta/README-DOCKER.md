# Running OmniFocus MCP Server in Docker

The OmniFocus MCP server requires access to macOS's `osascript` to communicate with OmniFocus. Since Docker containers run Linux, we use a **host bridge service** pattern.

## Architecture

```
Docker Container (OmniFocus MCP Server)
    ↓ HTTP
Host Bridge Service (runs on macOS)
    ↓ osascript
OmniFocus Application
```

## Setup Steps

### 1. Start the Host Bridge Service

The host bridge service must run on your macOS host:

```bash
cd omnifocus-mcp-letta
./start-host-bridge.sh
```

Or manually:
```bash
node host-bridge-service.js 8889
```

Keep this running in a terminal or run it as a background service.

### 2. Start the Docker Container

The Docker container will automatically use the host bridge service:

```bash
docker-compose up -d omnifocus-mcp-server
```

The container is configured to connect to `http://host.docker.internal:8889` (the host bridge service).

### 3. Verify It's Working

Check the container logs:
```bash
docker logs omnifocus-mcp-server
```

You should see the server starting without osascript errors.

Test the MCP endpoint:
```bash
curl -X POST http://localhost:8888/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "clientInfo": {"name": "test", "version": "1.0"}}}'
```

## Running Host Bridge as a Service (Optional)

You can run the host bridge service automatically on macOS startup using `launchd`:

1. Create `~/Library/LaunchAgents/com.omnifocus.mcp.bridge.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.omnifocus.mcp.bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/node</string>
        <string>/path/to/ai-PA/omnifocus-mcp-letta/host-bridge-service.js</string>
        <string>8889</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/omnifocus-bridge.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/omnifocus-bridge.error.log</string>
</dict>
</plist>
```

2. Load the service:
```bash
launchctl load ~/Library/LaunchAgents/com.omnifocus.mcp.bridge.plist
```

## Troubleshooting

### "Connection refused" errors

- Ensure the host bridge service is running on port 8889
- Check that `host.docker.internal` resolves correctly (Docker Desktop should handle this)

### "Plugin not found" errors

- Ensure the OmniFocus plugin is installed: `./rst.sh` in the omnifocus-mcp-letta directory
- Restart OmniFocus after installing the plugin

### Port conflicts

- Change the host bridge port by editing `HOST_BRIDGE_URL` in docker-compose.yml
- Update the start script: `./start-host-bridge.sh <port>`

