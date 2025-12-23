# Docker and macOS Metadata Files

## Problem

When Docker containers (especially Letta) try to clean up directories, they can encounter errors like:

```
FileNotFoundError: [Errno 2] No such file or directory: '._RECORD'
```

This happens because macOS creates metadata files (`.DS_Store`, `._*`) on external drives and in mounted volumes. These files can interfere with container operations.

## Solution 1: Prevent Creation (Recommended)

Configure macOS to not create these files on external/USB drives:

```bash
# Run once to configure system
bash scripts/prevent-macos-metadata.sh
```

This sets:
- `DSDontWriteNetworkStores` - Prevents .DS_Store on network volumes
- `DSDontWriteUSBStores` - Prevents .DS_Store on USB/external drives

**Note**: You may need to log out and log back in for changes to take effect.

## Solution 2: Clean Existing Files

Clean up existing metadata files:

```bash
bash scripts/clean-macos-metadata.sh
```

This removes:
- All `._*` files (resource forks)
- All `.DS_Store` files

From:
- `letta/` directory
- `letta/env/` (virtual environment)
- `~/.gmail-mcp/` (OAuth credentials)

## Solution 3: Use Helper Script

Use the helper script to start Letta with automatic cleanup:

```bash
bash scripts/docker-start-letta.sh
```

This:
1. Cleans metadata files
2. Starts the Letta container
3. Shows logs

## For File Operations

To prevent `._*` files during file operations (cp, tar, etc.), add to your `~/.zshrc`:

```bash
export COPYFILE_DISABLE=1
```

Then reload:
```bash
source ~/.zshrc
```

## When to Clean

Clean metadata files:
- Before starting Letta if you see restart loops
- After copying files to external drives
- Periodically to prevent accumulation
- Before Docker operations that might fail due to metadata

## Troubleshooting

If Letta container keeps restarting:

1. Stop the container:
   ```bash
   docker stop ai-pa-letta-1
   ```

2. Clean metadata files:
   ```bash
   bash scripts/clean-macos-metadata.sh
   ```

3. Remove and recreate venv (if needed):
   ```bash
   rm -rf letta/env
   ```

4. Start container:
   ```bash
   docker-compose up -d letta
   ```

5. Check logs:
   ```bash
   docker logs -f ai-pa-letta-1
   ```
