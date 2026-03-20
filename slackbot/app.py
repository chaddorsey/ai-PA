# app.py
import os
import sys
import logging
import threading
import time

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from listeners.listeners import register_listeners
from health_check import start_health_server

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

app = App(token=os.environ["SLACK_BOT_TOKEN"])
register_listeners(app)

# Probe bot permissions on startup
def probe_bot_permissions():
    """Probe and log current bot permissions."""
    try:
        auth_response = app.client.auth_test()
        logger.error(f"🔍 BOT PERMISSIONS PROBE:")
        logger.error(f"  Bot User ID: {auth_response.get('user_id')}")
        logger.error(f"  Team ID: {auth_response.get('team_id')}")
        logger.error(f"  URL: {auth_response.get('url')}")
        logger.error(f"  User: {auth_response.get('user')}")
        logger.error(f"  Bot ID: {auth_response.get('bot_id')}")
        logger.error(f"  Full Response: {auth_response}")
        
        # Try to call a simple API that requires specific scopes
        try:
            # Test users.list (requires users:read scope)
            users_response = app.client.users_list(limit=1)
            if users_response.get('ok'):
                logger.error(f"✅ users:read scope - WORKING")
            else:
                logger.error(f"❌ users:read scope - FAILED: {users_response.get('error')}")
        except Exception as users_error:
            logger.error(f"❌ users:read scope - EXCEPTION: {users_error}")
            
        # Test im.list (requires im:read scope if it exists)
        try:
            im_response = app.client.im_list()
            if im_response.get('ok'):
                logger.error(f"✅ im:read scope - WORKING")
            else:
                logger.error(f"❌ im:read scope - FAILED: {im_response.get('error')}")
        except Exception as im_error:
            logger.error(f"❌ im:read scope - EXCEPTION: {im_error}")
            
    except Exception as auth_error:
        logger.error(f"❌ AUTH TEST FAILED: {auth_error}")

# Run permissions probe
probe_bot_permissions()

def start_health_check():
    """Start health check server in a separate thread."""
    try:
        health_port = int(os.getenv('HEALTH_CHECK_PORT', '8081'))
        logger.info(f"Starting health check server on port {health_port}")
        start_health_server(health_port)
    except Exception as e:
        logger.error(f"Failed to start health check server: {e}")

if __name__ == "__main__":
    # Start health check server in background thread
    health_thread = threading.Thread(target=start_health_check, daemon=True)
    health_thread.start()
    
    # Start Slack bot
    logger.info("Starting Slack bot...")
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
