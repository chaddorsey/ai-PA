#!/usr/bin/env python3
"""
Calendly MCP Server - HTTP Streamable Wrapper

FastAPI application providing HTTP Streamable transport for Calendly availability checking.
Compatible with Letta's HTTP streamable transport requirements.
"""

import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import MCP server components
from . import mcp_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get configuration from environment
SERVER_NAME = os.getenv("MCP_SERVER_NAME", "calendly-tools")
SERVER_VERSION = os.getenv("MCP_SERVER_VERSION", "1.0.0")
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8086"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    logger.info(f"Starting {SERVER_NAME} v{SERVER_VERSION}")
    logger.info("Calendly MCP Server initialized successfully")
    
    yield
    
    logger.info("Shutting down Calendly MCP Server...")


# Create FastAPI app
app = FastAPI(
    title=SERVER_NAME,
    description="HTTP Streamable transport wrapper for Calendly availability checking",
    version=SERVER_VERSION,
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


@app.get("/")
async def root():
    """Root endpoint with server information."""
    return {
        "service": SERVER_NAME,
        "version": SERVER_VERSION,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "mcp": "/mcp"
        }
    }


@app.get("/health")
@app.head("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": SERVER_NAME,
        "version": SERVER_VERSION,
        "transport": "http-streamable"
    }


@app.post("/mcp")
async def mcp_endpoint(request: Request, response: Response):
    """
    Main MCP endpoint for HTTP Streamable transport.
    
    Handles JSON-RPC requests following the MCP protocol specification.
    """
    try:
        # Check for mcp-session-id header (required for Letta)
        session_id = request.headers.get("mcp-session-id")
        if not session_id:
            # Generate a new session ID if not provided
            session_id = str(uuid.uuid4())
            logger.debug(f"Generated new session ID: {session_id}")
        
        # Set the session ID in response headers
        response.headers["mcp-session-id"] = session_id
        
        # Get the raw request body
        body = await request.body()
        
        # Parse JSON-RPC request
        try:
            rpc_request = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Extract JSON-RPC fields
        method = rpc_request.get("method", "")
        params = rpc_request.get("params")
        request_id = rpc_request.get("id")
        
        logger.info(f"[{session_id}] Received request: method={method}, id={request_id}")
        
        # Handle the request
        try:
            result = await mcp_server.handle_mcp_request(method, params)
            
            # Build JSON-RPC success response
            rpc_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
            
            logger.info(f"[{session_id}] Request successful: method={method}")
            return rpc_response
            
        except ValueError as e:
            # Method-specific error
            logger.error(f"[{session_id}] Request error: {e}")
            rpc_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32602,  # Invalid params
                    "message": str(e)
                }
            }
            return rpc_response
            
        except Exception as e:
            # Unexpected error
            logger.error(f"[{session_id}] Unexpected error: {e}", exc_info=True)
            rpc_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,  # Internal error
                    "message": f"Internal server error: {str(e)}"
                }
            }
            return rpc_response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fatal error in MCP endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def main():
    """Main entry point for running the server."""
    logger.info(f"Starting {SERVER_NAME} (HTTP Streamable) on {SERVER_HOST}:{SERVER_PORT}")
    
    # Run the server
    uvicorn.run(
        "src.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="info",
        reload=False
    )


if __name__ == "__main__":
    main()

