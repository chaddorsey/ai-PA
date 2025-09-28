# OmniFocus Plugin Installation Guide

## ⚠️ **CRITICAL REQUIREMENT**

The OmniFocus MCP server **requires** the `omnifocus-mcp` plugin to be installed in OmniFocus for it to function. Without this plugin, the MCP server will fail with "Plugin not found" errors.

## Plugin File

- **Location**: `extra-files/omnifocus-mcp.omnijs`
- **Plugin ID**: `omnifocus-mcp`
- **Version**: `0.1.1`
- **Author**: Chad Dorsey

## Installation Steps

### 1. Install the Plugin File

```bash
# Copy the plugin to your OmniFocus plugins directory
cp extra-files/omnifocus-mcp.omnijs ~/Library/Containers/com.omnigroup.OmniFocus4/Data/Library/Application\ Support/Plug-Ins/
```

### 2. Create Symbolic Link (Recommended)

For development workflow, create a symbolic link so the plugin file stays in sync:

```bash
# Remove the source file
rm extra-files/omnifocus-mcp.omnijs

# Create symbolic link to the actual plugin location
ln -s ~/Library/Containers/com.omnigroup.OmniFocus4/Data/Library/Application\ Support/Plug-Ins/omnifocus-mcp.omnijs \
      extra-files/omnifocus-mcp.omnijs
```

### 3. Enable the Plugin in OmniFocus

1. Open OmniFocus
2. Go to **OmniFocus** → **Preferences** → **Plug-Ins**
3. Find `omnifocus-mcp` in the list
4. Check the box to enable it
5. Restart OmniFocus if prompted

### 4. Verify Installation

The plugin should appear in OmniFocus preferences and be ready to receive requests from the MCP server.

## Development Workflow Benefits

With the symbolic link approach:

✅ **Automatic Sync**: Changes made in OmniFocus are immediately reflected in the repository
✅ **No Manual Sync**: Eliminates the need for `sac.sh` copy operations  
✅ **Reduced Errors**: No risk of stale copies or sync conflicts
✅ **Simplified Workflow**: Direct development in OmniFocus with automatic version control

The `rst.sh` script has been updated to skip the plugin copy operation (since it's now a symbolic link) and will still work for building and restarting services. The `sac.sh` script becomes unnecessary with the symbolic link.

## How It Works

The MCP server communicates with OmniFocus through this architecture:

```
MCP Server → AppleScript → OmniFocus JavaScript Engine → omnifocus-mcp Plugin → OmniFocus Database
```

1. **MCP Server** receives a request
2. **Bridge** (`bridge.ts`) creates temporary AppleScript
3. **AppleScript** tells OmniFocus to find the `omnifocus-mcp` plugin
4. **Plugin** processes the request and returns JSON
5. **Bridge** parses and returns the result

## Troubleshooting

### Plugin Not Found Error

If you see errors like "Plugin not found":
1. Verify the plugin file is in the correct directory
2. Check that the plugin is enabled in OmniFocus preferences
3. Restart OmniFocus completely
4. Check that OmniFocus has JavaScript execution enabled

### Testing the Plugin

You can test the plugin by running a simple MCP request:
```bash
curl -X POST http://localhost:8888/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

## Docker Considerations

When running in Docker:
- The plugin must be installed on the **host machine** (where OmniFocus is running)
- The MCP server in Docker will communicate with the host's OmniFocus instance
- Ensure OmniFocus is running and accessible from the Docker container
- **Symbolic links**: The Docker build process will follow the symbolic link and include the actual plugin file in the container image
- **Development**: Changes to the plugin on the host will be reflected in the Docker container if the volume mount includes the plugins directory

## Security Note

The plugin requires OmniFocus to execute JavaScript, which may require additional permissions depending on your macOS security settings.

## Planned Date Support
- Requires OmniFocus 4.7.1 or later (first release with `plannedDate` and `effectivePlannedDate`).
- MCP responses now include these fields for tasks; ensure the plugin copy above is deployed before testing.
