#!/bin/bash
# Wrapper script for launchd to start the OmniFocus host bridge service
# This ensures the service starts correctly even with external volumes

cd /Volumes/main-drive/ai-PA/omnifocus-mcp-letta || exit 1
exec /opt/homebrew/bin/node host-bridge-service.js 8889
