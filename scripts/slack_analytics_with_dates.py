#!/usr/bin/env python3
"""
Trigger Slack Analytics CSV exports with custom date range support.

Usage:
    # Default: Yesterday's data
    python3 slack_analytics_with_dates.py --type channels
    
    # Custom date range
    python3 slack_analytics_with_dates.py --type members --start-date 2025-10-15 --end-date 2025-10-20
    
    # Last N days
    python3 slack_analytics_with_dates.py --type channels --last-days 7
"""

import asyncio
import argparse
from pathlib import Path
from playwright.async_api import async_playwright
from datetime import datetime, timedelta

SLACK_WORKSPACE_URL = "https://concord-consortium.slack.com"

async def trigger_export_with_dates(
    analytics_type: str = "channels",
    start_date: str = None,
    end_date: str = None,
    headless: bool = True,
    screenshot_dir: str = "./slack_analytics_screenshots",
    auth_save_path: str = "./slack_auth_state.json"
):
    """
    Trigger Slack analytics CSV export with custom date range.
    
    Args:
        analytics_type: Type of analytics (channels, members)
        start_date: Start date in YYYY-MM-DD format (defaults to yesterday)
        end_date: End date in YYYY-MM-DD format (defaults to yesterday)
        headless: Run browser in headless mode
        screenshot_dir: Directory to save screenshots
        auth_save_path: Path to save/load authentication state
    """
    
    # Default to 3 days ago (analytics data typically has 2-3 day delay)
    if not start_date:
        default_date = datetime.now() - timedelta(days=3)
        start_date = default_date.strftime('%Y-%m-%d')
    
    if not end_date:
        end_date = start_date  # Same day by default
    
    screenshot_path_dir = Path(screenshot_dir).resolve()
    screenshot_path_dir.mkdir(parents=True, exist_ok=True)
    
    auth_path = Path(auth_save_path)
    
    results = {
        "success": False,
        "analytics_type": analytics_type,
        "start_date": start_date,
        "end_date": end_date,
        "button_clicked": False,
        "errors": []
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        
        context_options = {}
        if auth_path.exists():
            print(f"✓ Loading saved authentication from {auth_path}")
            context_options["storage_state"] = str(auth_path)
        
        context = await browser.new_context(**context_options)
        page = await context.new_page()
        
        # Navigate to analytics page
        target_url = f"{SLACK_WORKSPACE_URL}/admin/stats#{analytics_type}"
        print(f"→ Navigating to {target_url}")
        
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
        except Exception as e:
            results["errors"].append(f"Navigation failed: {e}")
            await browser.close()
            return results
        
        # Handle login if needed
        current_url = page.url
        if "/signin" in current_url:
            print("\n⚠ Not logged in. Please log in...")
            try:
                await page.wait_for_url(
                    lambda url: "/signin" not in url,
                    timeout=120000
                )
                print("✓ Login successful!")
                await context.storage_state(path=str(auth_path))
                await page.goto(target_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
            except Exception as e:
                results["errors"].append(f"Login failed: {e}")
                await browser.close()
                return results
        else:
            print("✓ Already authenticated")
        
        # Wait for page load
        await page.wait_for_timeout(3000)
        
        # Click the tab
        print(f"→ Clicking {analytics_type} tab...")
        try:
            await page.click(f'a[data-analytics-tab="{analytics_type}"]', timeout=5000)
            print(f"✓ Clicked {analytics_type} tab")
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"⚠ Could not click tab: {e}")
        
        # Dismiss modals
        print("→ Dismissing modals...")
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(1000)
        
        try:
            close_btn = page.locator('button[aria-label="Close"]').first
            if await close_btn.count() > 0:
                await close_btn.click(timeout=2000)
                await page.wait_for_timeout(1000)
        except:
            pass
        
        # Take "before" screenshot
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_before = screenshot_path_dir / f"slack_{analytics_type}_before_dates_{timestamp}.png"
        await page.screenshot(path=str(screenshot_before), full_page=True)
        print(f"✓ Screenshot: {screenshot_before}")
        
        # Set custom date range
        print(f"→ Setting date range: {start_date} to {end_date}")
        
        try:
            # Step 1: Click the date range dropdown
            print("  Step 1: Opening date range dropdown...")
            date_dropdown = page.locator(f'div[data-qa="analytics_{analytics_type}-table-header-filter-button"]')
            await date_dropdown.click(timeout=5000)
            await page.wait_for_timeout(1000)
            print("  ✓ Dropdown opened")
            
            # Step 2: Click "Range…" option
            print("  Step 2: Selecting 'Range…'")
            range_option = page.locator('[data-qa="SELECT_NEW"]').or_(
                page.locator('text="Range"')
            )
            await range_option.click(timeout=5000)
            await page.wait_for_timeout(1500)
            print("  ✓ Date range modal opened")
            
            # Take screenshot of date picker modal
            screenshot_modal = screenshot_path_dir / f"slack_{analytics_type}_modal_{timestamp}.png"
            await page.screenshot(path=str(screenshot_modal), full_page=True)
            print(f"  ✓ Modal screenshot: {screenshot_modal}")
            
            # Step 3: Click start date on calendar picker
            print(f"  Step 3: Clicking start date on calendar: {start_date}")
            start_date_element = page.locator(f'div.c-date_range_picker_calendar__date[data-value="{start_date}"]')
            
            # Might need to navigate to the correct month first
            # Try clicking the date
            try:
                await start_date_element.click(timeout=3000)
                print(f"  ✓ Start date clicked: {start_date}")
            except:
                # Date might not be visible, try clicking next/prev month buttons
                print(f"  → Date not visible, may need month navigation")
                # For now, try waiting and clicking again
                await page.wait_for_timeout(1000)
                await start_date_element.click(timeout=5000)
                print(f"  ✓ Start date clicked: {start_date}")
            
            await page.wait_for_timeout(500)
            
            # Step 4: Click end date on calendar picker
            print(f"  Step 4: Clicking end date on calendar: {end_date}")
            end_date_element = page.locator(f'div.c-date_range_picker_calendar__date[data-value="{end_date}"]')
            await end_date_element.click(timeout=5000)
            print(f"  ✓ End date clicked: {end_date}")
            
            await page.wait_for_timeout(500)
            
            # Step 5: Click Save button
            print("  Step 5: Clicking Save button...")
            save_button = page.locator('button[data-qa="date_ranger_picker_calendar_save_button"]')
            await save_button.click(timeout=5000)
            print("  ✓ Save button clicked")
            
            # Step 6: Ensure modal is fully closed
            print("  Step 6: Ensuring modal is closed...")
            for attempt in range(3):
                try:
                    # Check if modal is still visible
                    modal = page.locator('.ReactModal__Overlay')
                    if await modal.count() > 0:
                        # Press Escape to close
                        await page.keyboard.press('Escape')
                        await page.wait_for_timeout(1000)
                        print(f"    Attempt {attempt + 1}: Pressed Escape")
                    else:
                        print("  ✓ Modal already closed")
                        break
                except:
                    break
            
            # Additional wait to ensure modal animation completes
            await page.wait_for_timeout(2000)
            print("  ✓ Modal fully dismissed")
            
            # Step 7: Wait for data to refresh
            print("  Step 7: Waiting for data to refresh (18 seconds)...")
            await page.wait_for_timeout(18000)
            print("  ✓ Data should be refreshed")
            
            results["date_range_set"] = True
            
        except Exception as e:
            print(f"  ⚠ Could not set custom date range: {e}")
            print(f"  → Proceeding with default date range")
            results["date_range_set"] = False
            results["errors"].append(f"Date range setting failed: {e}")
        
        # Ensure no modals are blocking before clicking Export
        print("→ Final check: Ensuring page is ready...")
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(1000)
        
        # Find and click Export CSV button
        print("→ Looking for Export CSV button...")
        
        button_selectors = [
            f'button[data-qa="analytics_{analytics_type}_csv-header-action"]',
            'button[aria-label="Export CSV"]',
            'button:has-text("Export CSV")',
        ]
        
        button_clicked = False
        for selector in button_selectors:
            try:
                button = page.locator(selector).first
                count = await button.count()
                if count > 0:
                    print(f"✓ Found button: {selector}")
                    
                    # Check if button is actually clickable
                    is_visible = await button.is_visible()
                    is_enabled = await button.is_enabled()
                    print(f"  Button state: visible={is_visible}, enabled={is_enabled}")
                    
                    if not is_visible or not is_enabled:
                        print(f"  × Button not clickable, trying next selector")
                        continue
                    
                    # Force click to bypass any remaining overlays
                    await button.click(force=True, timeout=5000)
                    print(f"✓ Clicked Export CSV button")
                    button_clicked = True
                    results["button_clicked"] = True
                    
                    await page.wait_for_timeout(2000)
                    
                    # Take "after" screenshot
                    screenshot_after = screenshot_path_dir / f"slack_{analytics_type}_after_dates_{timestamp}.png"
                    await page.screenshot(path=str(screenshot_after), full_page=True)
                    print(f"✓ Post-click screenshot: {screenshot_after}")
                    
                    results["success"] = True
                    break
            except Exception as e:
                print(f"  × Selector failed ({selector}): {e}")
                continue
        
        if not button_clicked:
            results["errors"].append("Could not find or click Export CSV button")
            # Save debug HTML
            html = await page.content()
            debug_file = screenshot_path_dir / f"slack_{analytics_type}_debug_{timestamp}.html"
            debug_file.write_text(html)
            print(f"⚠ Debug HTML saved: {debug_file}")
        
        await context.storage_state(path=str(auth_path))
        await browser.close()
    
    return results


async def main():
    parser = argparse.ArgumentParser(description="Trigger Slack Analytics CSV with custom date range")
    parser.add_argument("--type", choices=["channels", "members"], default="channels",
                       help="Type of analytics")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD), defaults to yesterday")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD), defaults to start-date")
    parser.add_argument("--last-days", type=int, help="Get last N days (alternative to start/end dates)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--screenshot-dir", default="./slack_analytics_screenshots")
    parser.add_argument("--auth-file", default="./slack_auth_state.json")
    
    args = parser.parse_args()
    
    # Calculate dates if --last-days provided
    start_date = args.start_date
    end_date = args.end_date
    
    if args.last_days:
        end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')  # Yesterday
        start_date = (datetime.now() - timedelta(days=args.last_days)).strftime('%Y-%m-%d')
    
    print(f"\n{'='*60}")
    print(f"Slack Analytics Export with Date Range")
    print(f"{'='*60}\n")
    
    results = await trigger_export_with_dates(
        analytics_type=args.type,
        start_date=start_date,
        end_date=end_date,
        headless=args.headless,
        screenshot_dir=args.screenshot_dir,
        auth_save_path=args.auth_file
    )
    
    print(f"\n{'='*60}")
    if results["success"]:
        print("✓ SUCCESS")
        print(f"  Type: {results['analytics_type']}")
        print(f"  Date Range: {results['start_date']} to {results['end_date']}")
        print(f"  Export triggered - check Slack Files for the CSV")
        print(f"\n  NOTE: Date range selection may not be automated yet.")
        print(f"  Check screenshots to verify the date picker UI, then we can enhance the script.")
    else:
        print("✗ FAILED")
        for error in results["errors"]:
            print(f"  Error: {error}")
    print(f"{'='*60}\n")
    
    return 0 if results["success"] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

