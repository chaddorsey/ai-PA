#!/usr/bin/env python3
"""
Auto-Madden Companion UI.

Web-based chat interface for the real-time game companion.
"""

import json
import logging
import os
import threading
from datetime import datetime

import requests
from flask import Flask, render_template, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
# For local dev, default to localhost. Docker uses env vars to override.
INSIGHT_ENGINE_URL = os.environ.get('INSIGHT_ENGINE_URL', 'http://localhost:5131')
INSIGHT_ENGINE_WS_URL = os.environ.get('INSIGHT_ENGINE_WS_URL', 'ws://localhost:5131/ws')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Set log level
logging.getLogger().setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))


@app.route('/')
def index():
    """Serve the main companion UI."""
    return render_template('index.html', ws_url=INSIGHT_ENGINE_WS_URL)


@app.route('/simple')
def simple():
    """Serve a simple test UI for debugging."""
    return render_template('simple.html')


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'auto-madden-companion-ui',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/config', methods=['GET'])
def config():
    """Get configuration for the frontend."""
    return jsonify({
        'insight_engine_url': INSIGHT_ENGINE_URL,
        'ws_url': INSIGHT_ENGINE_WS_URL
    })


if __name__ == '__main__':
    logger.info("Starting Auto-Madden Companion UI")
    app.run(host='0.0.0.0', port=5130, debug=False, threaded=True)

