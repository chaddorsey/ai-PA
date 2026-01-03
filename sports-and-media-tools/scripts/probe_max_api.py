#!/usr/bin/env python3
"""
Probe Max (HBO) API for watch history endpoints.

This script attempts to discover and access Max's internal APIs
for viewing history and continue watching data.

Usage:
    1. Export cookies from max.com using Cookie-Editor extension
    2. Save as max_cookies.json in the same directory
    3. Run: python3 probe_max_api.py
"""

import json
import os
import requests
from pathlib import Path

# Known Max/HBO API endpoints to try
ENDPOINTS = [
    # Continue Watching / My Stuff
    "https://default.any-any.prd.api.max.com/cms/routes/my-stuff",
    "https://default.any-any.prd.api.max.com/cms/routes/continue-watching",
    "https://default.any-any.prd.api.max.com/users/me/continue-watching",
    "https://default.any-any.prd.api.max.com/users/me/history",
    "https://default.any-any.prd.api.max.com/users/me/viewing-history",
    
    # Profile-based endpoints
    "https://default.any-any.prd.api.max.com/profiles/me",
    "https://default.any-any.prd.api.max.com/profiles/me/history",
    "https://default.any-any.prd.api.max.com/profiles/me/watchlist",
    
    # Legacy HBO Max endpoints
    "https://comet.api.hbo.com/content/continue-watching",
    "https://comet.api.hbo.com/express-content/continue-watching",
    "https://comet.api.hbo.com/users/me/watch-history",
    
    # Discovery+ style (WBD unified platform)
    "https://default.any-any.prd.api.max.com/playback/v2/play-history",
    "https://us.api.max.com/users/me/history",
]

# Common headers for Max API
BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.max.com",
    "Referer": "https://www.max.com/",
}


def load_cookies(cookie_file: str) -> dict:
    """Load cookies from a JSON file (Cookie-Editor export format)."""
    with open(cookie_file, 'r') as f:
        cookies_list = json.load(f)
    
    # Convert list format to dict
    cookies = {}
    for cookie in cookies_list:
        name = cookie.get('name', cookie.get('Name', ''))
        value = cookie.get('value', cookie.get('Value', ''))
        if name and value:
            cookies[name] = value
    
    return cookies


def cookies_to_header(cookies: dict) -> str:
    """Convert cookies dict to Cookie header string."""
    return "; ".join([f"{k}={v}" for k, v in cookies.items()])


def probe_endpoint(url: str, cookies: dict, headers: dict) -> dict:
    """Probe a single endpoint and return results."""
    try:
        # Add cookies to headers
        full_headers = {**headers}
        full_headers["Cookie"] = cookies_to_header(cookies)
        
        # Also try with Authorization header if we have a token
        if "AccessToken" in cookies:
            full_headers["Authorization"] = f"Bearer {cookies['AccessToken']}"
        elif "access_token" in cookies:
            full_headers["Authorization"] = f"Bearer {cookies['access_token']}"
        
        response = requests.get(url, headers=full_headers, timeout=10)
        
        return {
            "url": url,
            "status": response.status_code,
            "content_type": response.headers.get("Content-Type", ""),
            "size": len(response.content),
            "preview": response.text[:500] if response.status_code == 200 else response.text[:200]
        }
    except Exception as e:
        return {
            "url": url,
            "status": "error",
            "error": str(e)
        }


def main():
    print("="*60)
    print("Max (HBO) API Probe")
    print("="*60)
    
    # Look for cookies file
    script_dir = Path(__file__).parent
    cookie_file = script_dir / "max_cookies.json"
    
    if not cookie_file.exists():
        print("\n❌ No cookies file found!")
        print(f"\nPlease export your max.com cookies to:")
        print(f"  {cookie_file}")
        print("\nSteps:")
        print("1. Install Cookie-Editor browser extension")
        print("2. Go to max.com and log in")
        print("3. Click Cookie-Editor icon")
        print("4. Click 'Export' → 'Export as JSON'")
        print("5. Save to the path above")
        return
    
    print(f"\n✓ Found cookies file: {cookie_file}")
    
    # Load cookies
    cookies = load_cookies(str(cookie_file))
    print(f"✓ Loaded {len(cookies)} cookies")
    
    # Show cookie names (not values for security)
    print("\nCookie names found:")
    for name in sorted(cookies.keys()):
        value_preview = cookies[name][:20] + "..." if len(cookies[name]) > 20 else cookies[name]
        print(f"  - {name}: {value_preview}")
    
    # Probe endpoints
    print("\n" + "="*60)
    print("Probing API endpoints...")
    print("="*60)
    
    successful = []
    for url in ENDPOINTS:
        print(f"\n→ {url}")
        result = probe_endpoint(url, cookies, BASE_HEADERS)
        
        if result.get("status") == 200:
            print(f"  ✓ SUCCESS! Status: 200")
            print(f"  Content-Type: {result.get('content_type')}")
            print(f"  Size: {result.get('size')} bytes")
            print(f"  Preview: {result.get('preview', '')[:100]}...")
            successful.append(result)
        elif result.get("status") == "error":
            print(f"  ❌ Error: {result.get('error')}")
        else:
            print(f"  ✗ Status: {result.get('status')}")
            if result.get("status") in [401, 403]:
                print(f"    (Authentication issue)")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"\nSuccessful endpoints: {len(successful)}")
    
    if successful:
        print("\nWorking endpoints:")
        for s in successful:
            print(f"  ✓ {s['url']}")
    else:
        print("\n⚠️ No endpoints returned data.")
        print("This could mean:")
        print("  1. Cookies expired - try re-exporting")
        print("  2. Missing auth token - check for AccessToken cookie")
        print("  3. API requires different headers")
        print("  4. Max uses a different API structure than expected")


if __name__ == "__main__":
    main()

