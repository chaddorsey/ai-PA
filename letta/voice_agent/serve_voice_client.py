#!/usr/bin/env python3
"""
Simple HTTP server to serve the voice client HTML file
This avoids CORS issues when loading external scripts
"""

import http.server
import socketserver
import os
import sys

PORT = 8088

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers to allow external script loading
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def do_POST(self):
        if self.path == '/generate_token':
            # Handle token generation
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                import json
                import subprocess
                import os
                
                # Parse the request data
                data = json.loads(post_data.decode('utf-8'))
                room_name = data.get('room', 'default-room')
                identity = data.get('identity', 'browser-user')
                
                # Generate token using the Python script
                env = os.environ.copy()
                result = subprocess.run([
                    'arch', '-arm64', 'python3', 'generate_token.py', 
                    '--room', room_name, '--identity', identity, '--quiet'
                ], capture_output=True, text=True, cwd=os.getcwd(), env=env)
                
                if result.returncode == 0:
                    token = result.stdout.strip()
                    response_data = {'token': token}
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(response_data).encode('utf-8'))
                else:
                    self.send_response(500)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': result.stderr}).encode('utf-8'))
                    
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_OPTIONS(self):
        # Handle preflight requests
        self.send_response(200)
        self.end_headers()

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
        print(f"🌐 Voice client server running at http://localhost:{PORT}")
        print(f"📱 Open http://localhost:{PORT}/voice_client.html in your browser")
        print("Press Ctrl+C to stop the server")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server stopped")
            sys.exit(0)
