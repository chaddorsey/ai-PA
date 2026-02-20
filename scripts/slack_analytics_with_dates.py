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
import json
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
    
    IMPORTANT: Slack does not allow exports when start_date == end_date.
    If both dates are the same, the end_date will be automatically adjusted to be one day later.
    
    Args:
        analytics_type: Type of analytics (channels, members)
        start_date: Start date in YYYY-MM-DD format (defaults to 3 days ago)
        end_date: End date in YYYY-MM-DD format (defaults to start_date + 1 day)
        headless: Run browser in headless mode
        screenshot_dir: Directory to save screenshots
        auth_save_path: Path to save/load authentication state
    """
    
    # Default to 3 days ago (analytics data typically has 2-3 day delay)
    if not start_date:
        default_date = datetime.now() - timedelta(days=3)
        start_date = default_date.strftime('%Y-%m-%d')
    
    if not end_date:
        # IMPORTANT: Slack requires start_date != end_date, so default to start_date + 1 day
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = start_dt + timedelta(days=1)
        end_date = end_dt.strftime('%Y-%m-%d')
        print(f"⚠ Note: end_date not specified. Using {end_date} (start_date + 1 day) to avoid Slack export error.")
    
    # Validate: Slack does not allow exports when start_date == end_date
    if start_date == end_date:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = start_dt + timedelta(days=1)
        end_date = end_dt.strftime('%Y-%m-%d')
        print(f"⚠ Warning: start_date and end_date were the same ({start_date}).")
        print(f"  Adjusted end_date to {end_date} to avoid Slack export error.")
        print(f"  Slack requires at least a 1-day range for CSV exports.")
    
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
        # Only load auth file if it exists and contains valid JSON
        if auth_path.exists() and auth_path.stat().st_size > 0:
            try:
                # Validate it's valid JSON before using it
                with open(auth_path, 'r') as f:
                    json.load(f)
                print(f"✓ Loading saved authentication from {auth_path}")
                context_options["storage_state"] = str(auth_path)
            except (json.JSONDecodeError, ValueError) as e:
                print(f"⚠ Auth file exists but is invalid JSON: {e}")
                print("  Will proceed without saved authentication")
        
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
        page_content = await page.content()
        
        # Check for sign-in page indicators (URL or page content)
        is_signin_page = (
            "/signin" in current_url or 
            "Sign in to" in page_content or
            "You need to sign in" in page_content or
            "sign_in" in current_url.lower() or
            'data-qa="sign_in"' in page_content
        )
        
        if is_signin_page:
            print("\n⚠ Not logged in. Detected sign-in page.")
            print(f"  URL: {current_url}")
            results["errors"].append("Authentication required but cannot log in in headless mode. Please provide a valid auth file.")
            await browser.close()
            return results
        else:
            print("✓ Already authenticated")
        
        # Wait for page load
        await page.wait_for_timeout(3000)
        
        # Diagnostic: Log current URL and page title
        current_url = page.url
        page_title = await page.title()
        print(f"→ Current URL: {current_url}")
        print(f"→ Page title: {page_title}")
        
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
            # Channels uses analytics_channels-table-header-filter-button
            # Members uses data_table_header-filter-button
            if analytics_type == "channels":
                date_dropdown_selector = 'div[data-qa="analytics_channels-table-header-filter-button"]'
            else:
                date_dropdown_selector = 'div[data-qa="data_table_header-filter-button"]'
            date_dropdown = page.locator(date_dropdown_selector)

            # Check if element exists before clicking
            count = await date_dropdown.count()
            if count == 0:
                print(f"  ⚠ Date dropdown not found with selector: {date_dropdown_selector}")
                print(f"  → Current URL: {page.url}")
                raise Exception(f"Date range dropdown button not found")
            
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
            
            # Step 3: Type start date into text input
            print(f"  Step 3: Setting start date: {start_date}")
            start_input = page.get_by_role("textbox", name="Start date")
            await start_input.click(timeout=5000)
            await start_input.fill("")
            await start_input.type(start_date)
            print(f"  ✓ Start date entered: {start_date}")

            await page.wait_for_timeout(300)

            # Step 4: Type end date into text input
            print(f"  Step 4: Setting end date: {end_date}")
            end_input = page.get_by_role("textbox", name="End date")
            await end_input.click(timeout=5000)
            await end_input.fill("")
            await end_input.type(end_date)
            print(f"  ✓ End date entered: {end_date}")

            # Press Enter to validate the date range (enables the Save button)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(500)

            # Step 5: Click Save button
            print("  Step 5: Clicking Save button...")
            save_button = page.get_by_role("button", name="Save")
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
                    
                    # Wait for any modals/notifications to appear
                    await page.wait_for_timeout(3000)
                    
                    # Check for error modals/toasts
                    print("→ Checking for error messages...")
                    error_detected = False
                    
                    # Look for error toast/modal
                    error_selectors = [
                        '.c-toast:has-text("Unable to export")',
                        '.c-toast:has-text("error")',
                        '.c-toast:has-text("Error")',
                        '[data-qa="toast"]:has-text("Unable")',
                        '.ReactModal__Content:has-text("Unable to export")',
                    ]
                    
                    for error_sel in error_selectors:
                        try:
                            error_element = page.locator(error_sel).first
                            if await error_element.count() > 0:
                                error_text = await error_element.text_content()
                                if error_text and ("Unable to export" in error_text or "error" in error_text.lower()):
                                    print(f"✗ Error detected: {error_text}")
                                    results["errors"].append(f"Export failed: {error_text}")
                                    results["success"] = False
                                    error_detected = True
                                    break
                        except Exception as e:
                            continue
                    
                    # Also check for the specific error message in toast elements
                    if not error_detected:
                        try:
                            # Check for toast with error message using the structure you provided
                            toast_selector = '.c-toast, .ReactModal__Content--after-open.c-toast'
                            toasts = page.locator(toast_selector)
                            toast_count = await toasts.count()
                            
                            for i in range(toast_count):
                                toast = toasts.nth(i)
                                toast_text = await toast.text_content()
                                if toast_text and ("Unable to export" in toast_text or "error" in toast_text.lower()):
                                    print(f"✗ Error toast detected: {toast_text}")
                                    results["errors"].append(f"Export failed: {toast_text.strip()}")
                                    results["success"] = False
                                    error_detected = True
                                    break
                        except Exception as e:
                            print(f"  Note: Could not check toasts: {e}")
                    
                    # Also check page content as fallback
                    if not error_detected:
                        try:
                            page_content = await page.content()
                            if "Unable to export your CSV" in page_content:
                                print("✗ Error message found in page: 'Unable to export your CSV'")
                                results["errors"].append("Export failed: Unable to export your CSV. Please try again later.")
                                results["success"] = False
                                error_detected = True
                        except:
                            pass
                    
                    # Check for success indicators (only if no error)
                    if not error_detected:
                        try:
                            # Look for success message with download icon
                            # Success modal has: "Generating CSV. It will be sent to you in Slack when it's ready."
                            # and includes data-qa="download" icon
                            success_selectors = [
                                '.c-toast:has([data-qa="download"]):has-text("Generating CSV")',
                                '.c-toast:has-text("Generating CSV")',
                                '.c-toast:has-text("It will be sent to you in Slack")',
                                '.c-toast:has([data-qa="download"])',
                            ]
                            success_found = False
                            for success_sel in success_selectors:
                                try:
                                    success_element = page.locator(success_sel).first
                                    if await success_element.count() > 0:
                                        success_text = await success_element.text_content()
                                        # Check for download icon
                                        download_icon = success_element.locator('[data-qa="download"]')
                                        has_download_icon = await download_icon.count() > 0
                                        
                                        if success_text and ("Generating CSV" in success_text or "sent to you in Slack" in success_text):
                                            print(f"✓ Success indicator found: {success_text}")
                                            if has_download_icon:
                                                print("  ✓ Download icon present - export is being generated")
                                            success_found = True
                                            break
                                except:
                                    continue
                            
                            if not success_found:
                                print("⚠ No clear success or error indicator found")
                                print("  → Checking for any toast messages...")
                                # Fallback: check for any toast that doesn't contain error text
                                try:
                                    all_toasts = page.locator('.c-toast')
                                    toast_count = await all_toasts.count()
                                    for i in range(toast_count):
                                        toast = all_toasts.nth(i)
                                        toast_text = await toast.text_content()
                                        if toast_text and "Unable to export" not in toast_text and "error" not in toast_text.lower():
                                            print(f"  → Found toast: {toast_text[:100]}")
                                except:
                                    pass
                        except Exception as e:
                            print(f"  Note: Could not check for success indicators: {e}")
                    
                    # Take "after" screenshot
                    screenshot_after = screenshot_path_dir / f"slack_{analytics_type}_after_dates_{timestamp}.png"
                    await page.screenshot(path=str(screenshot_after), full_page=True)
                    print(f"✓ Post-click screenshot: {screenshot_after}")
                    
                    # Only mark as success if no error was detected
                    if not error_detected:
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

