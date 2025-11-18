#!/usr/bin/env python3
"""
Download Slack Analytics CSV files using browser automation.

This script uses Playwright to:
1. Log into Slack (or use existing session)
2. Navigate to the analytics page
3. Click the "Export CSV" button
4. Download the file

Usage:
    python slack_analytics_export.py --type channels
    python slack_analytics_export.py --type members --headless
    python slack_analytics_export.py --type messages --download-dir ./analytics
"""

import asyncio
import argparse
from pathlib import Path
from playwright.async_api import async_playwright
from datetime import datetime

SLACK_WORKSPACE_URL = "https://concord-consortium.slack.com"
ANALYTICS_PAGES = {
    "channels": f"{SLACK_WORKSPACE_URL}/admin/stats#channels",
    "members": f"{SLACK_WORKSPACE_URL}/admin/stats#members",
    "messages": f"{SLACK_WORKSPACE_URL}/admin/stats#messages",
}

async def download_slack_analytics(
    analytics_type: str = "channels",
    headless: bool = False,
    download_dir: str = "./downloads",
    auth_save_path: str = "./slack_auth_state.json"
):
    """
    Download Slack analytics CSV using browser automation.
    
    Args:
        analytics_type: Type of analytics (channels, members, messages)
        headless: Run browser in headless mode
        download_dir: Directory to save downloaded files
        auth_save_path: Path to save/load authentication state
    """
    
    # Ensure download directory exists
    download_path = Path(download_dir).resolve()
    download_path.mkdir(parents=True, exist_ok=True)
    
    auth_path = Path(auth_save_path)
    
    results = {
        "success": False,
        "analytics_type": analytics_type,
        "download_path": None,
        "errors": []
    }
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=headless)
        
        # Try to load existing auth state
        context_options = {
            "accept_downloads": True,
        }
        
        if auth_path.exists():
            print(f"✓ Loading saved authentication from {auth_path}")
            context_options["storage_state"] = str(auth_path)
        else:
            print("⚠ No saved authentication found. You'll need to log in.")
        
        context = await browser.new_context(**context_options)
        page = await context.new_page()
        
        # Navigate to analytics page
        target_url = ANALYTICS_PAGES.get(analytics_type)
        if not target_url:
            results["errors"].append(f"Unknown analytics type: {analytics_type}")
            await browser.close()
            return results
        
        print(f"→ Navigating to {target_url}")
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
        except Exception as e:
            results["errors"].append(f"Navigation failed: {e}")
            await browser.close()
            return results
        
        # Check if we're at login page
        current_url = page.url
        if "/signin" in current_url or "slack.com/workspace-signin" in current_url:
            print("\n⚠ Not logged in. Please log in to Slack...")
            print("   The browser will stay open for you to authenticate.")
            print("   After logging in, the script will continue automatically.\n")
            
            # Wait for successful login (navigation away from signin page)
            try:
                await page.wait_for_url(
                    lambda url: "/signin" not in url and "workspace-signin" not in url,
                    timeout=120000  # 2 minutes to log in
                )
                print("✓ Login successful!")
                
                # Save authentication state for future use
                await context.storage_state(path=str(auth_path))
                print(f"✓ Authentication saved to {auth_path}")
                
                # Navigate to analytics page again
                await page.goto(target_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                
            except Exception as e:
                results["errors"].append(f"Login timeout or failed: {e}")
                await browser.close()
                return results
        else:
            print("✓ Already authenticated")
        
        # Wait for the page to load
        await page.wait_for_timeout(3000)
        
        # Take a screenshot for debugging
        screenshot_path = download_path / f"slack_analytics_{analytics_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await page.screenshot(path=str(screenshot_path))
        print(f"✓ Screenshot saved: {screenshot_path}")
        
        # Find and click the Export CSV button
        print("→ Looking for Export CSV button...")
        
        # Try multiple selectors for the button
        button_selectors = [
            'button[aria-label="Export CSV"]',
            'button[data-qa="analytics_channels_csv-header-action"]',
            'button:has-text("Export CSV")',
            'button.c-data_table_header_action:has-text("Export")',
        ]
        
        button_found = False
        for selector in button_selectors:
            try:
                button = page.locator(selector).first
                if await button.count() > 0:
                    print(f"✓ Found button with selector: {selector}")
                    
                    # Set up download listener BEFORE clicking
                    async with page.expect_download(timeout=30000) as download_info:
                        await button.click()
                        print("✓ Clicked Export CSV button")
                    
                    download = await download_info.value
                    
                    # Save the downloaded file
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"slack_analytics_{analytics_type}_{timestamp}.csv"
                    save_path = download_path / filename
                    
                    await download.save_as(save_path)
                    print(f"✓ Downloaded: {save_path}")
                    
                    results["success"] = True
                    results["download_path"] = str(save_path)
                    button_found = True
                    break
                    
            except Exception as e:
                print(f"  × Selector failed: {selector} - {e}")
                continue
        
        if not button_found:
            # Debug: print page content to see what's available
            content = await page.content()
            debug_file = download_path / f"slack_page_debug_{analytics_type}.html"
            debug_file.write_text(content)
            
            results["errors"].append(
                f"Could not find Export CSV button. Page HTML saved to {debug_file}"
            )
        
        # Save final state
        await context.storage_state(path=str(auth_path))
        await browser.close()
    
    return results


async def main():
    parser = argparse.ArgumentParser(
        description="Download Slack Analytics CSV files"
    )
    parser.add_argument(
        "--type",
        choices=["channels", "members", "messages"],
        default="channels",
        help="Type of analytics to download"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no visible window)"
    )
    parser.add_argument(
        "--download-dir",
        default="./slack_analytics_downloads",
        help="Directory to save downloaded files"
    )
    parser.add_argument(
        "--auth-file",
        default="./slack_auth_state.json",
        help="Path to save/load authentication state"
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"Slack Analytics Downloader")
    print(f"{'='*60}\n")
    
    results = await download_slack_analytics(
        analytics_type=args.type,
        headless=args.headless,
        download_dir=args.download_dir,
        auth_save_path=args.auth_file
    )
    
    print(f"\n{'='*60}")
    if results["success"]:
        print("✓ SUCCESS")
        print(f"  File: {results['download_path']}")
    else:
        print("✗ FAILED")
        for error in results["errors"]:
            print(f"  Error: {error}")
    print(f"{'='*60}\n")
    
    return 0 if results["success"] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

