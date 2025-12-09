# OmniFocus Host Bridge Service

This service runs on the macOS host and executes `osascript` commands that the Docker container cannot execute directly.

## Automatic Startup

The service is configured to start automatically on system boot via macOS launchd.

**Service Name:** `com.omnifocus.bridge`  
**Port:** `8889`  
**Plist Location:** `~/Library/LaunchAgents/com.omnifocus.bridge.plist`

## Management Commands

### Check Service Status
```bash
launchctl list com.omnifocus.bridge
```

### Start Service
```bash
launchctl load ~/Library/LaunchAgents/com.omnifocus.bridge.plist
```

### Stop Service
```bash
launchctl unload ~/Library/LaunchAgents/com.omnifocus.bridge.plist
```

### Restart Service
```bash
launchctl unload ~/Library/LaunchAgents/com.omnifocus.bridge.plist
launchctl load ~/Library/LaunchAgents/com.omnifocus.bridge.plist
```

### View Logs
```bash
# Standard output
tail -f ~/ai-PA/omnifocus-mcp-letta/bridge-service.log

# Error output
tail -f ~/ai-PA/omnifocus-mcp-letta/bridge-service.error.log
```

### Test Service
```bash
curl -X POST http://localhost:8889/execute \
  -H "Content-Type: application/json" \
  -d '{"command": "listRemaining", "args": {}}'
```

## How It Works

1. The Docker container (OmniFocus MCP server) runs inside Docker and cannot access macOS `osascript` directly
2. The Docker container makes HTTP requests to `host.docker.internal:8889/execute`
3. This host bridge service receives the requests and executes the AppleScript commands
4. Results are returned to the Docker container, which then processes them for the MCP protocol

## Troubleshooting

If the service isn't working:

1. **Check if it's running:**
   ```bash
   launchctl list | grep omnifocus
   ```

2. **Check the logs:**
   ```bash
   cat ~/ai-PA/omnifocus-mcp-letta/bridge-service.error.log
   ```

3. **Verify the port is listening:**
   ```bash
   lsof -i :8889
   ```

4. **Restart the service:**
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.omnifocus.bridge.plist
   launchctl load ~/Library/LaunchAgents/com.omnifocus.bridge.plist
   ```

## Updating the Service

If you modify `host-bridge-service.js` or need to change the port:

1. Update the plist file if needed:
   ```bash
   nano ~/Library/LaunchAgents/com.omnifocus.bridge.plist
   ```

2. Reload the service:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.omnifocus.bridge.plist
   launchctl load ~/Library/LaunchAgents/com.omnifocus.bridge.plist
   ```

## Removing the Service

To stop and remove the automatic startup:

```bash
launchctl unload ~/Library/LaunchAgents/com.omnifocus.bridge.plist
rm ~/Library/LaunchAgents/com.omnifocus.bridge.plist
```

