#!/usr/bin/env python3
"""
Configure Letta MCP servers using the Letta API.
This script sets up all MCP servers for the unified PA ecosystem.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MCP Server Configuration
MCP_SERVERS = {
    "gmail-tools": {
        "server_name": "gmail-tools",
        "type": "streamable_http",
        "server_url": "http://gmail-mcp-server:8080/mcp",
        "auth_header": None,
        "auth_token": None,
        "custom_headers": {
            "Content-Type": "application/json"
        }
    },
    "slack-tools": {
        "server_name": "slack-tools", 
        "type": "streamable_http",
        "server_url": "http://slack-mcp-server:8081/mcp",
        "auth_header": None,
        "auth_token": None,
        "custom_headers": {
            "Content-Type": "application/json"
        }
    },
    "graphiti-tools": {
        "server_name": "graphiti-tools",
        "type": "streamable_http", 
        "server_url": "http://graphiti-mcp-server:8082/mcp",
        "auth_header": None,
        "auth_token": None,
        "custom_headers": {
            "Content-Type": "application/json"
        }
    },
    "rag-tools": {
        "server_name": "rag-tools",
        "type": "streamable_http",
        "server_url": "http://rag-mcp-server:8083/mcp", 
        "auth_header": None,
        "auth_token": None,
        "custom_headers": {
            "Content-Type": "application/json"
        }
    }
}

class LettaMCPConfigurator:
    """Configure Letta MCP servers using the Letta API."""
    
    def __init__(self, letta_base_url: str = "http://letta:8283"):
        self.letta_base_url = letta_base_url
        self.session = None
        
    async def __aenter__(self):
        import aiohttp
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_letta_connection(self) -> bool:
        """Test connection to Letta server."""
        try:
            async with self.session.get(f"{self.letta_base_url}/v1/health/") as response:
                if response.status == 200:
                    logger.info("Successfully connected to Letta server")
                    return True
                else:
                    logger.error(f"Letta server returned status {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Failed to connect to Letta server: {e}")
            return False
    
    async def list_existing_servers(self) -> Dict[str, Any]:
        """List existing MCP servers."""
        try:
            async with self.session.get(f"{self.letta_base_url}/v1/tools/mcp/servers") as response:
                if response.status == 200:
                    servers = await response.json()
                    logger.info(f"Found {len(servers)} existing MCP servers")
                    return servers
                else:
                    logger.warning(f"Failed to list existing servers: {response.status}")
                    return {}
        except Exception as e:
            logger.warning(f"Failed to list existing servers: {e}")
            return {}
    
    async def add_mcp_server(self, server_config: Dict[str, Any]) -> bool:
        """Add a new MCP server to Letta."""
        try:
            async with self.session.put(
                f"{self.letta_base_url}/v1/tools/mcp/servers",
                json=server_config
            ) as response:
                if response.status in [200, 201]:
                    logger.info(f"Successfully added MCP server: {server_config['server_name']}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to add MCP server {server_config['server_name']}: {response.status} - {error_text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to add MCP server {server_config['server_name']}: {e}")
            return False
    
    async def test_mcp_server(self, server_name: str) -> bool:
        """Test connection to an MCP server."""
        try:
            async with self.session.post(
                f"{self.letta_base_url}/v1/tools/mcp/servers/{server_name}/test"
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"MCP server {server_name} test: {result}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"MCP server {server_name} test failed: {response.status} - {error_text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to test MCP server {server_name}: {e}")
            return False
    
    async def configure_all_servers(self) -> bool:
        """Configure all MCP servers."""
        logger.info("Starting MCP server configuration...")
        
        # Test Letta connection
        if not await self.test_letta_connection():
            logger.error("Cannot connect to Letta server. Aborting configuration.")
            return False
        
        # List existing servers
        existing_servers = await self.list_existing_servers()
        existing_names = {server.get('server_name') for server in existing_servers}
        
        success_count = 0
        total_count = len(MCP_SERVERS)
        
        for server_name, server_config in MCP_SERVERS.items():
            logger.info(f"Configuring MCP server: {server_name}")
            
            # Skip if server already exists
            if server_name in existing_names:
                logger.info(f"MCP server {server_name} already exists, skipping...")
                success_count += 1
                continue
            
            # Add the server
            if await self.add_mcp_server(server_config):
                success_count += 1
                
                # Test the server
                await self.test_mcp_server(server_name)
            else:
                logger.error(f"Failed to configure MCP server: {server_name}")
        
        logger.info(f"Configuration complete: {success_count}/{total_count} servers configured successfully")
        return success_count == total_count

async def main():
    """Main function to configure MCP servers."""
    letta_url = os.getenv("LETTA_BASE_URL", "http://letta:8283")
    
    logger.info(f"Configuring MCP servers for Letta at {letta_url}")
    
    async with LettaMCPConfigurator(letta_url) as configurator:
        success = await configurator.configure_all_servers()
        
        if success:
            logger.info("All MCP servers configured successfully!")
            sys.exit(0)
        else:
            logger.error("Some MCP servers failed to configure")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

