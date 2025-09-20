# Minimal app.py for testing Docker containerization
import os
import logging
import threading
import time
from health_check import start_health_server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    
    # Keep the main thread alive
    logger.info("Minimal Slackbot container started (health check only)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
