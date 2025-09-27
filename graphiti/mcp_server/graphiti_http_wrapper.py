#!/usr/bin/env python3
"""
Graphiti MCP Server - HTTP Streamable Wrapper

This wrapper provides HTTP Streamable transport for the Graphiti MCP server,
making it compatible with Letta's HTTP streamable transport requirements.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager

# Add the current directory to Python path to import graphiti_mcp_server
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the original Graphiti MCP server components
from graphiti_mcp_server import (
    mcp, 
    initialize_graphiti,
    GRAPHITI_MCP_INSTRUCTIONS,
    logger,
    graphiti_client,
    add_memory,
    search_memory_nodes,
    search_memory_facts,
    delete_entity_edge,
    delete_episode,
    get_entity_edge,
    get_episodes,
    clear_graph
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variable to store the initialized Graphiti client
graphiti_client = None

# Track initialized sessions
initialized_sessions = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    global graphiti_client
    try:
        # Initialize Graphiti client
        await initialize_graphiti()
        logger.info("Graphiti client initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize Graphiti client: {e}")
        logger.warning("Continuing with limited functionality - some tools may not work")
    
    yield
    
    # Cleanup if needed
    logger.info("Shutting down Graphiti MCP Server...")

# Create FastAPI app
app = FastAPI(
    title="Graphiti MCP Server - HTTP Streamable",
    description="HTTP Streamable transport wrapper for Graphiti MCP server",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
@app.head("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": "2025-09-27T05:00:00Z",
        "service": "graphiti-tools",
        "version": "1.0.0",
        "transport": "http-streamable"
    }

# Tool registry for mapping tool names to functions
TOOL_REGISTRY = {
    "add_memory": add_memory,
    "search_memory_nodes": search_memory_nodes,
    "search_memory_facts": search_memory_facts,
    "delete_entity_edge": delete_entity_edge,
    "delete_episode": delete_episode,
    "get_entity_edge": get_entity_edge,
    "get_episodes": get_episodes,
    "clear_graph": clear_graph,
}

# MCP endpoint for HTTP Streamable transport
@app.post("/mcp")
async def mcp_endpoint(request: Request, response: Response):
    """Main MCP endpoint for HTTP Streamable transport."""
    try:
        # Check for mcp-session-id header (required for Letta)
        session_id = request.headers.get("mcp-session-id")
        if not session_id:
            # Generate a new session ID if not provided
            session_id = str(uuid.uuid4())
        
        # Set the session ID in response headers
        response.headers["mcp-session-id"] = session_id
        
        # Get the raw request body
        body = await request.body()
        
        # Parse JSON-RPC request
        try:
            rpc_request = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        method = rpc_request.get("method", "")
        params = rpc_request.get("params", {})
        request_id = rpc_request.get("id")
        
        if method == "initialize":
            # Mark session as initialized
            initialized_sessions.add(session_id)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "graphiti-tools",
                        "version": "1.0.0"
                    }
                }
            }
        elif method == "tools/list":
            # Check if session is initialized (proper MCP protocol)
            if session_id not in initialized_sessions:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32000,
                        "message": "Bad Request: Server not initialized"
                    }
                }
            
            # Return the available tools from Graphiti
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "add_memory",
                            "description": "Add episodes, nodes, or facts to the knowledge graph",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Name/identifier for the memory"},
                                    "episode_body": {"type": "string", "description": "Content to add to memory"},
                                    "source": {"type": "string", "enum": ["text", "messages", "json"], "default": "text"},
                                    "source_description": {"type": "string", "description": "Description of the source"},
                                    "group_id": {"type": "string", "description": "Group ID for organizing related data"}
                                },
                                "required": ["name", "episode_body"]
                            }
                        },
                        {
                            "name": "search_memory_nodes",
                            "description": "Search for nodes (entities) in the knowledge graph",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "Natural language search query"},
                                    "group_ids": {"type": "array", "items": {"type": "string"}, "description": "Filter by group IDs"},
                                    "max_nodes": {"type": "integer", "default": 10, "description": "Maximum number of results"},
                                    "center_node_uuid": {"type": "string", "description": "Center search around this node"}
                                },
                                "required": ["query"]
                            }
                        },
                        {
                            "name": "search_memory_facts",
                            "description": "Search for facts (relationships) in the knowledge graph",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "Natural language search query"},
                                    "group_ids": {"type": "array", "items": {"type": "string"}, "description": "Filter by group IDs"},
                                    "max_facts": {"type": "integer", "default": 10, "description": "Maximum number of results"},
                                    "center_node_uuid": {"type": "string", "description": "Center search around this node"}
                                },
                                "required": ["query"]
                            }
                        },
                        {
                            "name": "delete_entity_edge",
                            "description": "Delete an entity edge from the graph memory",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "uuid": {"type": "string", "description": "UUID of the entity edge to delete"}
                                },
                                "required": ["uuid"]
                            }
                        },
                        {
                            "name": "delete_episode",
                            "description": "Delete an episode from the graph memory",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "uuid": {"type": "string", "description": "UUID of the episode to delete"}
                                },
                                "required": ["uuid"]
                            }
                        },
                        {
                            "name": "get_entity_edge",
                            "description": "Get an entity edge from the graph memory by UUID",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "uuid": {"type": "string", "description": "UUID of the entity edge to retrieve"}
                                },
                                "required": ["uuid"]
                            }
                        },
                        {
                            "name": "get_episodes",
                            "description": "Get the most recent memory episodes for a specific group",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "group_id": {"type": "string", "description": "Group ID to filter episodes"},
                                    "last_n": {"type": "integer", "default": 10, "description": "Number of recent episodes to retrieve"}
                                }
                            }
                        },
                        {
                            "name": "clear_graph",
                            "description": "Clear all data from the graph memory and rebuild indices",
                            "inputSchema": {
                                "type": "object",
                                "properties": {}
                            }
                        }
                    ]
                }
            }
        elif method == "tools/call":
            # Handle tool calls
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            
            if tool_name not in TOOL_REGISTRY:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}"
                    }
                }
            
            try:
                # Call the actual Graphiti tool function
                tool_func = TOOL_REGISTRY[tool_name]
                result = await tool_func(**tool_args)
                
                # Format the result for MCP
                if isinstance(result, dict):
                    content = [{"type": "text", "text": json.dumps(result, indent=2)}]
                else:
                    content = [{"type": "text", "text": str(result)}]
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": content
                    }
                }
            except Exception as e:
                logger.error(f"Tool call error for {tool_name}: {e}")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32603,
                        "message": f"Tool execution error: {str(e)}"
                    }
                }
        elif method == "notifications/initialized":
            # Standard MCP notification - no response needed
            return {"jsonrpc": "2.0", "id": None}
        else:
            raise HTTPException(status_code=400, detail=f"Unknown method: {method}")
            
    except Exception as e:
        logger.error(f"MCP endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_SERVER_PORT", "8000"))
    
    logger.info(f"Starting Graphiti MCP Server (HTTP Streamable) on {host}:{port}")
    
    # Run the server
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )
