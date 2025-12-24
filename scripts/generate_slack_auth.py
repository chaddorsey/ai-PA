#!/usr/bin/env python3
"""
Generate Slack Authentication File

This script launches a browser in interactive (non-headless) mode,
allows you to log in to Slack, and saves the authentication state
to a file that can be used by the Slack analytics export scripts.

Usage:
    python3 generate_slack_auth.py
    python3 generate_slack_auth.py --auth-file /path/to/slack_auth_state.json
"""

import asyncio
import argparse
from pathlib import Path
from playwright.async_api import async_playwright

SLACK_WORKSPACE_URL = "https://concord-consortium.slack.com"


async def generate_auth_file(auth_save_path: str = "./slack_auth_state.json"):
    """
    Generate a Slack authentication file by logging in interactively.
    
    Args:
        auth_save_path: Path where the authentication state will be saved
    """
    auth_path = Path(auth_save_path).resolve()
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print("Slack Authentication File Generator")
    print(f"{'='*60}\n")
    print("This script will:")
    print("  1. Launch a browser window")
    print("  2. Navigate to Slack analytics page")
    print("  3. Allow you to log in interactively")
    print("  4. Save your authentication state")
    print(f"  5. Save to: {auth_path}\n")
    print("Please log in when the browser opens...\n")
    
    async with async_playwright() as p:
        # Launch browser in non-headless mode so user can interact
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Navigate to analytics page (will redirect to login if not authenticated)
        target_url = f"{SLACK_WORKSPACE_URL}/admin/stats#channels"
        print(f"→ Opening {target_url}...")
        
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"✗ Navigation failed: {e}")
            await browser.close()
            return False
        
        # Check current URL and page content
        current_url = page.url
        page_content = await page.content()
        
        # Check for sign-in page indicators
        is_signin_page = (
            "/signin" in current_url or 
            "Sign in to" in page_content or
            "You need to sign in" in page_content or
            "sign_in" in current_url.lower() or
            'data-qa="sign_in"' in page_content
        )
        
        if is_signin_page:
            print("\n⚠ Sign-in page detected.")
            print("  → Please log in using the browser window that opened.")
            print("  → After logging in, the script will automatically detect success.")
            print("  → Waiting for you to complete login...\n")
            
            # Wait for URL to change away from sign-in page (indicating successful login)
            try:
                original_url = current_url
                
                # Poll for URL/content change (more reliable than wait_for_function for this use case)
                print("  → Waiting for successful login (checking every 2 seconds)...")
                max_wait_time = 300  # 5 minutes total
                check_interval = 2  # Check every 2 seconds
                waited = 0
                
                while waited < max_wait_time:
                    await page.wait_for_timeout(check_interval * 1000)
                    waited += check_interval
                    
                    new_url = page.url
                    new_content = await page.content()
                    
                    # Check if we're no longer on sign-in page
                    still_signin = (
                        "/signin" in new_url or 
                        "Sign in to" in new_content or
                        "You need to sign in" in new_content
                    )
                    
                    if not still_signin and new_url != original_url:
                        print(f"  ✓ URL changed - login likely successful!")
                        break
                    
                    if waited % 10 == 0:  # Print status every 10 seconds
                        print(f"  → Still waiting... ({waited}s / {max_wait_time}s)")
                else:
                    # Timeout reached
                    print("✗ Login timeout reached. Please try again.")
                    await browser.close()
                    return False
                
                # Wait a bit more to ensure page is fully loaded and auth cookies are set
                await page.wait_for_timeout(3000)
                
                # Final verification
                final_url = page.url
                final_content = await page.content()
                
                still_signin = (
                    "/signin" in final_url or 
                    "Sign in to" in final_content or
                    "You need to sign in" in final_content
                )
                
                if still_signin:
                    print("✗ Still on sign-in page. Login may have failed.")
                    await browser.close()
                    return False
                
                print("✓ Login confirmed! Saving authentication state...")
                
            except Exception as e:
                print(f"✗ Login timeout or failed: {e}")
                print("  → The browser window will close in 5 seconds...")
                await page.wait_for_timeout(5000)
                await browser.close()
                return False
        else:
            print("✓ Already authenticated (or page loaded successfully)")
        
        # Save authentication state
        try:
            await context.storage_state(path=str(auth_path))
            print(f"✓ Authentication state saved to: {auth_path}")
            
            # Verify the file was created and has content
            if auth_path.exists() and auth_path.stat().st_size > 0:
                print(f"✓ File verified: {auth_path.stat().st_size} bytes")
                
                # Quick validation that it's valid JSON with cookies
                import json
                with open(auth_path, 'r') as f:
                    auth_data = json.load(f)
                    cookie_count = len(auth_data.get('cookies', []))
                    origins_count = len(auth_data.get('origins', []))
                    print(f"✓ Contains {cookie_count} cookies and {origins_count} origin(s)")
            else:
                print("⚠ Warning: Auth file appears to be empty")
                
        except Exception as e:
            print(f"✗ Failed to save authentication state: {e}")
            await browser.close()
            return False
        
        print("\n✓ Authentication file generation complete!")
        print("  → You can now close the browser window.")
        print("  → The auth file is ready to use with the export scripts.\n")
        
        # Keep browser open for a moment so user can see success
        await page.wait_for_timeout(2000)
        await browser.close()
    
    return True


async def main():
    parser = argparse.ArgumentParser(
        description="Generate Slack authentication file by logging in interactively"
    )
    parser.add_argument(
        "--auth-file",
        default="./slack_auth_state.json",
        help="Path where the authentication state will be saved (default: ./slack_auth_state.json)"
    )
    
    args = parser.parse_args()
    
    success = await generate_auth_file(args.auth_file)
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
