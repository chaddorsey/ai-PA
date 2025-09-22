#!/bin/bash
# Configure Letta MCP servers

set -e

echo "Configuring Letta MCP servers..."

# Wait for Letta to be ready
echo "Waiting for Letta server to be ready..."
until curl -f http://letta:8283/v1/health/ > /dev/null 2>&1; do
    echo "Waiting for Letta server..."
    sleep 5
done

echo "Letta server is ready. Configuring MCP servers..."

# Install Python dependencies
pip install -r requirements.txt

# Run the configuration script
python configure_mcp_servers.py

echo "MCP server configuration complete!"

