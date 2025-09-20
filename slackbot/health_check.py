#!/usr/bin/env python3
"""
Health check script for Slackbot MCP server.
Provides HTTP health check endpoint for Docker health checks.
"""

import os
import sys
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check endpoint."""
    
    def do_GET(self):
        """Handle GET requests to health check endpoint."""
        if self.path == '/health':
            self.send_health_response()
        else:
            self.send_error(404, "Not Found")
    
    def send_health_response(self):
        """Send health check response."""
        try:
            # Check if required environment variables are set
            required_vars = ['SLACK_BOT_TOKEN', 'SLACK_APP_TOKEN', 'LETTA_AGENT_ID']
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            
            if missing_vars:
                self.send_error(503, f"Missing required environment variables: {', '.join(missing_vars)}")
                return
            
            # Basic health check - if we can respond, we're healthy
            health_status = {
                "status": "healthy",
                "timestamp": time.time(),
                "service": "slackbot-mcp",
                "version": "1.0.0"
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(health_status).encode())
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.send_error(503, f"Health check failed: {str(e)}")
    
    def log_message(self, format, *args):
        """Override to reduce log noise."""
        pass

def start_health_server(port=8081):
    """Start the health check HTTP server."""
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info(f"Health check server started on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start health check server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Start health check server in a separate thread
    health_port = int(os.getenv('HEALTH_CHECK_PORT', '8081'))
    health_thread = Thread(target=start_health_server, args=(health_port,), daemon=True)
    health_thread.start()
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Health check server stopped")
        sys.exit(0)
