#!/usr/bin/env python3
"""
Flipper Zero IR Control API
HTTP API to allow Letta agents and Docker services to control Flipper Zero.

This service runs on the host (not in Docker) to access the USB serial connection,
or can run in a Docker container with privileged access to /dev.
"""

import os
import logging
from flask import Flask, request, jsonify

from send_ir import send_ir_command, tune_channel, get_available_commands, find_flipper_port

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
FLIPPER_PORT = os.environ.get('FLIPPER_PORT', None)  # Auto-detect if not set


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    port = FLIPPER_PORT or find_flipper_port()
    flipper_available = port is not None
    
    return jsonify({
        'status': 'healthy' if flipper_available else 'degraded',
        'service': 'flipper-api',
        'flipper_port': port,
        'flipper_available': flipper_available
    })


@app.route('/ir/<command>', methods=['POST'])
def send_ir(command: str):
    """Send IR command to Flipper Zero.
    
    Args:
        command: Name of the IR command (e.g., 'Power', 'Ok', '5')
    """
    try:
        port = request.args.get('port') or FLIPPER_PORT
        success = send_ir_command(command, port=port)
        
        if success:
            return jsonify({
                'success': True,
                'command': command,
                'message': f'Sent IR command: {command}'
            })
        else:
            return jsonify({
                'success': False,
                'command': command,
                'error': 'Failed to send command'
            }), 500
    except Exception as e:
        logger.error(f"Error sending IR command {command}: {e}")
        return jsonify({
            'success': False,
            'command': command,
            'error': str(e)
        }), 500


@app.route('/channel/<int:channel>', methods=['POST'])
def set_channel(channel: int):
    """Tune to specific channel.
    
    Args:
        channel: Channel number to tune to (1-9999)
    """
    try:
        if channel < 1 or channel > 9999:
            return jsonify({
                'success': False,
                'channel': channel,
                'error': 'Channel number must be between 1 and 9999'
            }), 400
        
        port = request.args.get('port') or FLIPPER_PORT
        success = tune_channel(channel, port=port)
        
        if success:
            return jsonify({
                'success': True,
                'channel': channel,
                'message': f'Tuned to channel {channel}'
            })
        else:
            return jsonify({
                'success': False,
                'channel': channel,
                'error': 'Failed to tune channel'
            }), 500
    except Exception as e:
        logger.error(f"Error tuning to channel {channel}: {e}")
        return jsonify({
            'success': False,
            'channel': channel,
            'error': str(e)
        }), 500


@app.route('/commands', methods=['GET'])
def list_commands():
    """List all available IR commands."""
    commands = get_available_commands()
    return jsonify({
        'commands': commands,
        'count': len(commands)
    })


@app.route('/sequence', methods=['POST'])
def send_sequence():
    """Send a sequence of IR commands with delays.
    
    Request body:
        {
            "commands": ["Power", "Ok", "5", "7", "0"],
            "delay": 0.5  // delay between commands in seconds
        }
    """
    try:
        import time
        
        data = request.get_json() or {}
        commands = data.get('commands', [])
        delay = data.get('delay', 0.5)
        
        if not commands:
            return jsonify({
                'success': False,
                'error': 'No commands provided'
            }), 400
        
        port = request.args.get('port') or FLIPPER_PORT
        results = []
        
        for cmd in commands:
            success = send_ir_command(cmd, port=port)
            results.append({
                'command': cmd,
                'success': success
            })
            if not success:
                break
            time.sleep(delay)
        
        all_success = all(r['success'] for r in results)
        
        return jsonify({
            'success': all_success,
            'results': results,
            'message': f'Sent {len([r for r in results if r["success"]])} of {len(commands)} commands'
        }), 200 if all_success else 500
        
    except Exception as e:
        logger.error(f"Error sending sequence: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    print("Starting Flipper Zero IR Control API...")
    print("Endpoints:")
    print("  POST /ir/<command>       - Send IR command")
    print("  POST /channel/<number>   - Tune to channel")
    print("  GET  /commands           - List available commands")
    print("  POST /sequence           - Send command sequence")
    print("  GET  /health             - Health check")
    print("")
    
    port = FLIPPER_PORT or find_flipper_port()
    if port:
        print(f"Flipper Zero detected at: {port}")
    else:
        print("WARNING: Flipper Zero not detected. Connect via USB and restart.")
    
    print("\nRunning on http://0.0.0.0:5124")
    app.run(host='0.0.0.0', port=5124, debug=False)

