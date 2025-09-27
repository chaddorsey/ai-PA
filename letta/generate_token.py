#!/usr/bin/env python3
"""
Generate LiveKit access token for browser client
"""
import os
import sys
import argparse
from dotenv import load_dotenv
from livekit import api

load_dotenv()

def generate_access_token(room="voice-test", identity="browser-user", quiet=False):
    """Generate access token for browser client"""
    
    livekit_url = os.getenv('LIVEKIT_URL')
    api_key = os.getenv('LIVEKIT_API_KEY')
    api_secret = os.getenv('LIVEKIT_API_SECRET')
    
    if not all([livekit_url, api_key, api_secret]):
        if not quiet:
            print("❌ Missing LiveKit environment variables")
        return None
    
    # Create token
    token = api.AccessToken(api_key, api_secret)
    token.with_identity(identity)
    token.with_name("Browser Voice Client")
    token.with_grants(api.VideoGrants(
        room_join=True,
        room=room,
        can_subscribe=True,
        can_publish=True,
    ))
    
    jwt_token = token.to_jwt()
    
    if not quiet:
        print("🔑 Generated LiveKit Access Token:")
        print("=" * 50)
        print(jwt_token)
        print("=" * 50)
        print()
        print("📋 Instructions:")
        print("1. Copy the token above")
        print("2. Open voice_client.html in your browser")
        print("3. Replace 'your-access-token-here' with this token")
        print("4. Start your voice agent: arch -arm64 python3 minimal_working_agent.py connect --room voice-test")
        print("5. Connect in the browser")
    else:
        # Quiet mode - only output the token
        print(jwt_token)
    
    return jwt_token

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate LiveKit access token')
    parser.add_argument('--room', default='voice-test', help='Room name')
    parser.add_argument('--identity', default='browser-user', help='User identity')
    parser.add_argument('--quiet', action='store_true', help='Only output the token (no instructions)')
    
    args = parser.parse_args()
    generate_access_token(room=args.room, identity=args.identity, quiet=args.quiet)
