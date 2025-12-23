#!/usr/bin/env python3
"""
Test Calendar Credentials Loading in Container

This script tests credential loading directly in the Docker container
to diagnose authentication issues.
"""

import os
import sys
import json
from pathlib import Path

# Add letta directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_credential_loading():
    """Test credential loading with detailed diagnostics."""
    
    print("="*60)
    print("Calendar Credentials Diagnostic Test")
    print("="*60)
    print()
    
    # Check paths
    TOKEN_PATH = "/root/.gmail-mcp/calendar.credentials.json"
    OAUTH_KEY_FILE = "/root/.gmail-mcp/gcp-oauth.calendar.desktop.json"
    
    print("1. Checking file paths...")
    print(f"   TOKEN_PATH: {TOKEN_PATH}")
    print(f"   OAUTH_KEY_FILE: {OAUTH_KEY_FILE}")
    print()
    
    # Check if files exist
    print("2. Checking if files exist...")
    token_exists = os.path.exists(TOKEN_PATH)
    oauth_exists = os.path.exists(OAUTH_KEY_FILE)
    print(f"   TOKEN_PATH exists: {token_exists}")
    print(f"   OAUTH_KEY_FILE exists: {oauth_exists}")
    print()
    
    if not token_exists:
        print("   ✗ TOKEN_PATH does not exist!")
        return False
    
    if not oauth_exists:
        print("   ✗ OAUTH_KEY_FILE does not exist!")
        return False
    
    # Check file permissions
    print("3. Checking file permissions...")
    try:
        token_stat = os.stat(TOKEN_PATH)
        oauth_stat = os.stat(OAUTH_KEY_FILE)
        print(f"   TOKEN_PATH: readable={os.access(TOKEN_PATH, os.R_OK)}, size={token_stat.st_size}")
        print(f"   OAUTH_KEY_FILE: readable={os.access(OAUTH_KEY_FILE, os.R_OK)}, size={oauth_stat.st_size}")
    except Exception as e:
        print(f"   ✗ Error checking permissions: {e}")
        return False
    print()
    
    # Try to read and parse JSON
    print("4. Testing JSON parsing...")
    try:
        with open(TOKEN_PATH, 'r') as f:
            token_data = json.load(f)
        print(f"   ✓ TOKEN_PATH is valid JSON")
        print(f"   Keys in token file: {list(token_data.keys())}")
        
        # Check required keys
        required_keys = ['token', 'refresh_token', 'client_id', 'client_secret', 'token_uri']
        missing_keys = [k for k in required_keys if k not in token_data]
        if missing_keys:
            print(f"   ⚠ Missing required keys: {missing_keys}")
        else:
            print(f"   ✓ All required keys present")
            
    except json.JSONDecodeError as e:
        print(f"   ✗ TOKEN_PATH is not valid JSON: {e}")
        return False
    except Exception as e:
        print(f"   ✗ Error reading TOKEN_PATH: {e}")
        return False
    print()
    
    # Try to load credentials using google.oauth2
    print("5. Testing credential loading with google.oauth2...")
    try:
        from google.oauth2.credentials import Credentials
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        print(f"   ✓ Credentials loaded successfully")
        print(f"   Valid: {creds.valid}")
        print(f"   Expired: {creds.expired}")
        
        if hasattr(creds, 'expiry'):
            print(f"   Expiry: {creds.expiry}")
        
        if hasattr(creds, 'scopes'):
            print(f"   Scopes: {creds.scopes}")
            
    except ImportError as e:
        print(f"   ✗ Could not import google.oauth2: {e}")
        print(f"   This suggests dependencies are not installed")
        return False
    except Exception as e:
        print(f"   ✗ Error loading credentials: {e}")
        import traceback
        traceback.print_exc()
        return False
    print()
    
    # Try refreshing if expired
    if hasattr(creds, 'expired') and creds.expired:
        print("6. Testing token refresh...")
        try:
            from google.auth.transport.requests import Request
            
            if creds.refresh_token:
                print("   Attempting to refresh token...")
                creds.refresh(Request())
                print(f"   ✓ Token refreshed successfully")
                print(f"   Valid after refresh: {creds.valid}")
            else:
                print("   ⚠ No refresh_token available, cannot refresh")
        except Exception as e:
            print(f"   ✗ Error refreshing token: {e}")
            import traceback
            traceback.print_exc()
            return False
        print()
    
    # Test building the service
    print("7. Testing Calendar API service build...")
    try:
        from googleapiclient.discovery import build
        
        service = build("calendar", "v3", credentials=creds)
        print(f"   ✓ Calendar service built successfully")
        
        # Try a simple API call
        print("   Testing API call: calendarList().list()...")
        result = service.calendarList().list().execute()
        calendars = result.get('items', [])
        print(f"   ✓ API call successful! Found {len(calendars)} calendars")
        
    except ImportError as e:
        print(f"   ✗ Could not import googleapiclient: {e}")
        return False
    except Exception as e:
        print(f"   ✗ Error building service or making API call: {e}")
        import traceback
        traceback.print_exc()
        return False
    print()
    
    print("="*60)
    print("✓ All tests passed! Credentials are working correctly.")
    print("="*60)
    return True

if __name__ == "__main__":
    success = test_credential_loading()
    sys.exit(0 if success else 1)
