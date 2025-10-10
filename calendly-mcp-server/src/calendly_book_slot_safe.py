#!/usr/bin/env python3
"""
Safe Calendly slot booking with dry-run mode and comprehensive validation.

Features:
- Dry-run mode (validates flow without submitting)
- Screenshot capture before submission
- Pre-flight availability check (optional)
- Cross-platform time format handling
- Detailed step-by-step reporting
- Explicit confirmation required for actual booking

Usage:
  # Dry-run (safe - no submission)
  python calendly_book_slot_safe.py \
    "https://calendly.com/zarek-drozda/30min" \
    --date 2025-10-29 --time "3:30pm" \
    --name "Ada Lovelace" --email "ada@example.com" \
    --dry-run

  # Real booking (after dry-run succeeds)
  python calendly_book_slot_safe.py \
    "https://calendly.com/zarek-drozda/30min" \
    --date 2025-10-29 --time "3:30pm" \
    --name "Ada Lovelace" --email "ada@example.com" \
    --confirm-booking
"""

from __future__ import annotations
import asyncio, argparse, re, sys, json, time as time_module
from typing import Dict, Any, List, Optional
from datetime import datetime as _dt, date
from urllib.parse import urlparse
import platform

# Platform detection for time formatting
IS_WINDOWS = platform.system() == "Windows"

def _run(coro):
    """Run async coroutine from sync context."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _time_variants(t: str) -> List[str]:
    """
    Generate time format variants for matching.
    Handles both 12h and 24h formats, cross-platform.
    """
    t = t.strip().lower()
    variants = {t}
    
    try:
        # Parse 12h format (e.g., "3:30pm")
        if "am" in t or "pm" in t:
            dt = _dt.strptime(t.replace(" ", ""), "%I:%M%p")
            # Add 24h format
            variants.add(dt.strftime("%H:%M"))
            # Add variants with/without leading zero
            variants.add(dt.strftime("%I:%M%p").lower())
            variants.add(dt.strftime("%I:%M%p").lower().lstrip("0"))
            
        # Parse 24h format (e.g., "15:30")
        else:
            dt = _dt.strptime(t, "%H:%M")
            # Add 12h format
            if IS_WINDOWS:
                # Windows: %I keeps leading zero
                variants.add(dt.strftime("%I:%M%p").lower())
                variants.add(dt.strftime("%I:%M%p").lower().lstrip("0"))
            else:
                # Unix: %-I removes leading zero
                variants.add(dt.strftime("%-I:%M%p").lower())
            variants.add(dt.strftime("%I:%M%p").lower())
            
    except Exception as e:
        # If parsing fails, just use original
        pass
    
    return list(variants)


async def book_slot(
    event_url: str,
    date_iso: str,
    time_str: str,
    invitee_name: str,
    invitee_email: str,
    timezone: str,
    answers: Dict[str, str],
    guests: List[str],
    dry_run: bool = True,
    headless: bool = True,
    click_months_ahead: int = 4,
    settle_ms: int = 1000,
    screenshot_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Book a Calendly slot with comprehensive validation and safety features.
    
    Args:
        event_url: Calendly event URL
        date_iso: Target date (YYYY-MM-DD)
        time_str: Target time (HH:MM or h:mma)
        invitee_name: Full name
        invitee_email: Email address
        timezone: IANA timezone
        answers: Custom question answers {label_substring: answer}
        guests: Guest email addresses
        dry_run: If True, stops before submission (DEFAULT: True for safety)
        headless: Run headless browser
        click_months_ahead: Max months to advance
        settle_ms: Wait after submit before checking confirmation
        screenshot_dir: Directory to save screenshots (default: /tmp)
        
    Returns:
        Result dict with detailed step information
    """
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        return {"ok": False, "reason": "playwright_not_installed", "detail": str(e)}
    
    screenshot_dir = screenshot_dir or "/tmp"
    target_day = str(_dt.fromisoformat(date_iso).day)
    time_variants = _time_variants(time_str)
    
    results = {
        "ok": False,
        "event_url": event_url,
        "date_requested": date_iso,
        "time_requested": time_str,
        "time_variants": time_variants,
        "dry_run": dry_run,
        "steps": {},
        "screenshots": []
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(timezone_id=timezone, locale="en-US")
        page = await ctx.new_page()
        
        # Step 1: Navigate
        try:
            await page.goto(event_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)  # Let JS initialize
            results["steps"]["navigation"] = {"ok": True, "url": page.url}
        except Exception as e:
            results["steps"]["navigation"] = {"ok": False, "error": str(e)}
            await browser.close()
            return results
        
        # Step 2: Dismiss cookie/GDPR banners
        dismissed = False
        await page.wait_for_timeout(1000)  # Give banner time to appear
        
        for sel in ['#onetrust-accept-btn-handler', 'button:has-text("Accept All")',
                    'button:has-text("Accept")', 'button:has-text("Got it")', 
                    'button:has-text("I agree")']:
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.click(timeout=2000)
                    dismissed = True
                    await page.wait_for_timeout(1500)  # Wait for banner to disappear
                    break
            except Exception:
                pass
        results["steps"]["cookie_banner"] = {"dismissed": dismissed}
        
        # Additional wait for page to stabilize after banner dismissal
        await page.wait_for_timeout(1000)
        
        # Step 3: Find and click target date
        async def click_day() -> bool:
            # Try aria-label with "Times available"
            try:
                day_btn = page.locator('button[aria-label*="Times available"]').filter(has_text=target_day).first
                if await day_btn.count():
                    await day_btn.click(timeout=3000)
                    return True
            except Exception:
                pass
            # Try any button with just the day number
            try:
                day_btn = page.locator('button').filter(has_text=re.compile(rf"^\s*{re.escape(target_day)}\s*$"))
                if await day_btn.count():
                    await day_btn.first.click(timeout=3000)
                    return True
            except Exception:
                pass
            return False
        
        found_day = await click_day()
        months_navigated = 0
        
        # Advance months if needed
        if not found_day:
            for i in range(click_months_ahead):
                try:
                    next_btn = page.get_by_role("button", name=re.compile("(Next|Next month)", re.I))
                    if await next_btn.count():
                        await next_btn.first.click(timeout=2500)
                        await page.wait_for_timeout(500)
                        months_navigated += 1
                        if await click_day():
                            found_day = True
                            break
                except Exception:
                    break
        
        results["steps"]["date_selection"] = {
            "ok": found_day,
            "target_day": target_day,
            "months_navigated": months_navigated
        }
        
        if not found_day:
            results["reason"] = f"date_not_found: Day {target_day} not visible after checking {months_navigated + 1} months"
            # Screenshot for debugging
            try:
                screenshot = f"{screenshot_dir}/calendly_date_not_found_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=screenshot)
                results["screenshots"].append(screenshot)
            except Exception:
                pass
            await browser.close()
            return results
        
        # Wait for time slots to appear after clicking date
        await page.wait_for_timeout(1000)
        
        # Step 4: Find and click time slot
        clicked_time = False
        matched_variant = None
        
        # Try data-start-time attribute first
        for variant in time_variants:
            try:
                btn = page.locator(f'[data-container="time-button"][data-start-time*="{variant}"]').first
                if await btn.count():
                    await btn.click(timeout=3000)
                    clicked_time = True
                    matched_variant = variant
                    break
            except Exception:
                pass
        
        # Fallback: visible text in time buttons
        if not clicked_time:
            for variant in time_variants:
                try:
                    btn = page.locator('[data-container="time-button"]').filter(
                        has_text=re.compile(re.escape(variant), re.I)
                    ).first
                    if await btn.count():
                        await btn.click(timeout=3000)
                        clicked_time = True
                        matched_variant = variant
                        break
                except Exception:
                    pass
        
        results["steps"]["time_selection"] = {
            "ok": clicked_time,
            "time_variants_tried": time_variants,
            "matched_variant": matched_variant
        }
        
        if not clicked_time:
            results["reason"] = f"time_not_found: None of {time_variants} matched available time buttons"
            # Screenshot for debugging
            try:
                screenshot = f"{screenshot_dir}/calendly_time_not_found_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=screenshot)
                results["screenshots"].append(screenshot)
            except Exception:
                pass
            await browser.close()
            return results
        
        # Step 4.5: Click "Next" button after time selection
        # After clicking time, Calendly shows the selected time + a "Next" button
        await page.wait_for_timeout(500)  # Wait for slide animation
        
        next_clicked = False
        try:
            # The Next button appears in the selected-spot container
            next_btn = page.locator('[data-container="selected-spot"] button[aria-label*="Next"]').first
            if await next_btn.count():
                await next_btn.click(timeout=3000)
                next_clicked = True
            else:
                # Fallback: any Next button (but be careful not to match month navigation)
                next_btn = page.get_by_role("button", name=re.compile(r"^Next\s+\d", re.I)).first
                if await next_btn.count():
                    await next_btn.click(timeout=3000)
                    next_clicked = True
        except Exception as e:
            results["steps"]["next_button"] = {"ok": False, "error": str(e)}
        
        results["steps"]["next_button"] = {
            "ok": next_clicked,
            "message": "Clicked Next to proceed to form" if next_clicked else "Next button not found"
        }
        
        if not next_clicked:
            results["reason"] = "next_button_not_found"
            try:
                screenshot = f"{screenshot_dir}/calendly_no_next_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=screenshot)
                results["screenshots"].append(screenshot)
            except Exception:
                pass
            await browser.close()
            return results
        
        # Wait for form to appear - use explicit wait for form inputs
        try:
            await page.wait_for_selector('input[name="full_name"], input[name="name"], input[type="email"]', timeout=10000)
        except Exception:
            # Fallback to time-based wait
            await page.wait_for_timeout(2000)
        
        # Step 5: Verify and fill form fields (name, email, guests, custom questions)
        async def fill_if_present(selectors: List[str], value: str) -> bool:
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    if await el.count():
                        await el.fill(value, timeout=2500)
                        # Verify it was filled
                        filled_value = await el.input_value()
                        return filled_value == value
                except Exception:
                    pass
            return False
        
        async def fill_by_label(pattern: str, value: str) -> bool:
            try:
                el = page.get_by_label(re.compile(pattern, re.I))
                if await el.count():
                    await el.first.fill(value, timeout=2500)
                    filled_value = await el.first.input_value()
                    return filled_value == value
            except Exception:
                pass
            return False
        
        # Fill name
        name_filled = await fill_if_present(
            ['input[name="name"]', 'input[name="full_name"]', 'input[name="first_name"]'],
            invitee_name
        ) or await fill_by_label(r"(name|your name|full name|first name)", invitee_name)
        
        # Fill email
        email_filled = await fill_if_present(
            ['input[name="email"]', 'input[type="email"]'],
            invitee_email
        ) or await fill_by_label(r"(email)", invitee_email)
        
        results["steps"]["form_filling"] = {
            "ok": name_filled and email_filled,
            "name_filled": name_filled,
            "email_filled": email_filled,
            "name_value": invitee_name,
            "email_value": invitee_email
        }
        
        if not (name_filled and email_filled):
            results["reason"] = f"form_field_error: name_filled={name_filled}, email_filled={email_filled}"
            # Screenshot for debugging
            try:
                screenshot = f"{screenshot_dir}/calendly_form_error_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=screenshot)
                results["screenshots"].append(screenshot)
            except Exception:
                pass
            await browser.close()
            return results
        
        # Optional: Add guests
        guests_added = []
        add_guests_clicked = False
        if guests:
            try:
                # Find the "Add Guests" button - try specific text first
                add_btn = page.locator('button:has-text("Add Guests")').first
                if not await add_btn.count():
                    # Fallback to role-based search
                    add_btn = page.get_by_role("button", name=re.compile("Add Guests?", re.I)).first
                
                if await add_btn.count():
                    await add_btn.click(timeout=2000)
                    add_guests_clicked = True
                    await page.wait_for_timeout(500)  # Wait for guest input to appear
                    
                    # Guest email input has specific id and aria-label
                    guest_input = page.locator('#invitee_guest_input')
                    if not await guest_input.count():
                        # Fallback to aria-label
                        guest_input = page.locator('input[aria-label="Guest Email(s)"]').first
                    if not await guest_input.count():
                        # Fallback to data-testid container
                        guest_input = page.locator('[data-testid="event_guest_emails"] input[type="email"]').first
                    
                    if await guest_input.count():
                        for g in guests:
                            try:
                                await guest_input.fill(g)
                                await page.keyboard.press("Enter")
                                await page.wait_for_timeout(300)  # Wait for tag to be created
                                guests_added.append(g)
                                # Clear for next guest
                                await guest_input.clear()
                            except Exception as e:
                                # Log failure but continue with other guests
                                pass
            except Exception:
                pass
        
        results["steps"]["guests"] = {
            "requested": guests,
            "add_button_clicked": add_guests_clicked,
            "added": guests_added,
            "ok": len(guests) == 0 or len(guests_added) == len(guests)
        }
        
        # Step 5.5: Discover and handle custom question fields (including required fields marked with *)
        # First, discover all fields and identify which are required
        required_fields = []  # Fields with asterisk (*)
        optional_fields = []  # Fields without asterisk
        all_field_info = []   # Detailed info for all fields
        
        labels = page.locator('label')
        label_count = await labels.count()
        
        for i in range(label_count):
            try:
                label_text = (await labels.nth(i).text_content() or "").strip()
                label_html = await labels.nth(i).inner_html()
                
                # Skip empty labels
                if not label_text:
                    continue
                
                # Check if this label has an asterisk (indicating required field)
                # Asterisk can be: 1) At end of text, 2) In a span.szghqnp, 3) Just a * character
                has_asterisk = (
                    label_text.endswith('*') or
                    '*' in label_text or
                    'szghqnp' in label_html or
                    '<span>*</span>' in label_html or
                    'asterisk' in label_html.lower()
                )
                
                # Clean label text (remove asterisk and extra whitespace)
                clean_label = label_text.replace('*', '').strip()
                
                # Skip standard name/email fields (handled separately)
                label_lower = clean_label.lower()
                if label_lower in ['name', 'email', 'full name', 'email address', 'your name', 'your email']:
                    continue
                
                # Skip cookie consent and generic labels
                skip_patterns = ['cookie', 'checkbox label', 'guest email(s)']
                if any(pattern in label_lower for pattern in skip_patterns):
                    continue
                
                # Get the associated input
                label_for = await labels.nth(i).get_attribute('for')
                if label_for:
                    # Find input by id
                    field_input = page.locator(f'#{label_for}').first
                    if await field_input.count():
                        field_type = await field_input.get_attribute('type') or 'text'
                        field_name = await field_input.get_attribute('name') or label_for
                        
                        # Additional check: skip if field name suggests it's name/email
                        if field_name and ('email' in field_name.lower() or 
                                          (field_name.lower() == 'name' and field_type == 'text')):
                            continue
                        
                        field_info = {
                            "label": clean_label,
                            "original_label": label_text,
                            "required": has_asterisk,
                            "field_id": label_for,
                            "field_name": field_name,
                            "field_type": field_type
                        }
                        
                        all_field_info.append(field_info)
                        
                        if has_asterisk:
                            required_fields.append(clean_label)
                        else:
                            optional_fields.append(clean_label)
            except Exception:
                continue
        
        results["steps"]["field_discovery"] = {
            "total_fields": len(all_field_info),
            "required_fields": required_fields,
            "optional_fields": optional_fields,
            "all_fields": all_field_info
        }
        
        # Check if we have answers for all required fields
        missing_required = []
        for req_field in required_fields:
            # Check if any answer key matches this field (substring match, case-insensitive)
            matched = False
            for answer_key in answers.keys():
                if answer_key.lower() in req_field.lower() or req_field.lower() in answer_key.lower():
                    matched = True
                    break
            if not matched:
                missing_required.append(req_field)
        
        # If required fields are missing, return error before proceeding
        if missing_required:
            results["steps"]["required_field_validation"] = {
                "ok": False,
                "missing_required_fields": missing_required,
                "hint": f"This event requires {len(missing_required)} additional field(s). "
                       f"Provide values using --answer parameter. "
                       f"Example: --answer \"title the meeting=My Meeting Title\""
            }
            results["reason"] = f"required_fields_missing: {', '.join(missing_required)}"
            results["ok"] = False
            
            # Screenshot showing the form with missing fields
            try:
                screenshot = f"{screenshot_dir}/calendly_required_fields_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=screenshot, full_page=True)
                results["screenshots"].append(screenshot)
            except Exception:
                pass
            
            await browser.close()
            return results
        
        results["steps"]["required_field_validation"] = {
            "ok": True,
            "all_required_fields_provided": True
        }
        
        # Now fill all custom fields (both required and optional)
        answers_filled = {}
        for field_info in all_field_info:
            label = field_info["label"]
            field_id = field_info["field_id"]
            
            # Find matching answer
            matched_value = None
            matched_key = None
            for answer_key, answer_val in answers.items():
                if answer_key.lower() in label.lower() or label.lower() in answer_key.lower():
                    matched_value = answer_val
                    matched_key = answer_key
                    break
            
            if matched_value:
                try:
                    field_input = page.locator(f'#{field_id}').first
                    if await field_input.count():
                        # Check field type
                        tag = await field_input.evaluate("e => e.tagName")
                        if tag.lower() == "select":
                            await field_input.select_option(label=matched_value)
                        else:
                            await field_input.fill(matched_value)
                        
                        # Verify it was filled
                        if tag.lower() == "textarea":
                            filled_val = await field_input.text_content()
                        else:
                            filled_val = await field_input.input_value()
                        
                        if filled_val == matched_value:
                            answers_filled[matched_key] = {
                                "label": label,
                                "value": matched_value,
                                "required": field_info["required"]
                            }
                except Exception as e:
                    # Log but continue
                    pass
        
        results["steps"]["custom_answers"] = {
            "requested": answers,
            "filled": answers_filled,
            "ok": len(answers_filled) >= len([f for f in all_field_info if f["required"]])
        }
        
        # Step 6: Locate submit button (Schedule/Confirm/Book)
        submit_btn = None
        submit_text = None
        for name in ["Schedule Event", "Schedule", "Confirm", "Book", "Schedule now"]:
            try:
                btn = page.get_by_role("button", name=re.compile(name, re.I))
                if await btn.count():
                    submit_btn = btn.first
                    submit_text = name
                    break
            except Exception:
                pass
        
        results["steps"]["submit_button"] = {
            "found": submit_btn is not None,
            "text_pattern": submit_text
        }
        
        if not submit_btn:
            results["reason"] = "submit_button_not_found"
            try:
                screenshot = f"{screenshot_dir}/calendly_no_submit_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=screenshot)
                results["screenshots"].append(screenshot)
            except Exception:
                pass
            await browser.close()
            return results
        
        # Step 7: Take pre-submission screenshot for verification
        try:
            screenshot = f"{screenshot_dir}/calendly_pre_submit_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=screenshot, full_page=True)
            results["screenshots"].append(screenshot)
            results["pre_submit_screenshot"] = screenshot
        except Exception:
            pass
        
        # Step 8: DRY-RUN CHECK - Stop here unless confirm_booking is True
        if dry_run:
            results["steps"]["submission"] = {
                "ok": True,  # Validation passed, ready to submit
                "dry_run": True,
                "message": "DRY-RUN MODE: All validation passed. Would submit booking now.",
                "ready_to_submit": True
            }
            results["ok"] = True  # Validation succeeded
            results["message"] = "Dry-run complete - ready for actual booking"
            await browser.close()
            return results
        
        # Step 9: ACTUAL SUBMISSION (only if dry_run=False)
        # Check for form validation errors first
        validation_errors = []
        try:
            error_msgs = page.locator('[class*="error"], [aria-invalid="true"], [class*="invalid"]')
            if await error_msgs.count() > 0:
                for i in range(min(5, await error_msgs.count())):
                    try:
                        text = await error_msgs.nth(i).text_content()
                        if text and text.strip():
                            validation_errors.append(text.strip())
                    except:
                        pass
        except:
            pass
        
        if validation_errors:
            results["steps"]["submission"] = {
                "ok": False,
                "error": "form_validation_errors",
                "validation_errors": validation_errors
            }
            results["reason"] = f"form_validation_errors: {', '.join(validation_errors)}"
            await browser.close()
            return results
        
        # Click submit and wait for navigation
        submission_error = None
        navigation_occurred = False
        
        try:
            # Wait for navigation after clicking submit (timeout 10s)
            async with page.expect_navigation(timeout=10000):
                await submit_btn.click(timeout=5000)
            navigation_occurred = True
            results["steps"]["submission"] = {
                "ok": True,
                "clicked": True,
                "button_text": submit_text,
                "navigation_occurred": True
            }
        except Exception as e:
            # Submit may have worked even if navigation timeout occurred
            submission_error = str(e)
            results["steps"]["submission"] = {
                "ok": True,  # Assume ok unless proven otherwise
                "clicked": True,
                "button_text": submit_text,
                "navigation_occurred": False,
                "navigation_timeout": "timeout" in str(e).lower(),
                "error_detail": str(e)
            }
        
        # Wait for confirmation page to load/render
        await page.wait_for_timeout(settle_ms)
        
        # Step 10: Verify confirmation (multiple signals)
        confirmed = False
        confirmation_text = None
        
        # Signal 1: Wait for URL to change to confirmation page
        current_url = page.url
        url_changed = current_url != event_url
        invitee_id_in_url = "/invitees/" in current_url
        scheduled_in_url = "/scheduled_events/" in current_url
        
        # If URL changed, wait a bit more for content
        if url_changed:
            await page.wait_for_timeout(1000)
            current_url = page.url  # Update after wait
        
        # Signal 2: Look for confirmation text
        try:
            conf = page.get_by_text(re.compile(
                r"You (are|'re|re) scheduled|Event scheduled|You're all set|Confirmed|"
                r"Check your email|We (sent|emailed)|successfully scheduled|booking confirmed",
                re.I
            ))
            if await conf.count():
                confirmed = True
                try:
                    confirmation_text = await conf.first.text_content()
                except:
                    pass
        except Exception:
            pass
        
        # Signal 3: Check for calendar "Add to Calendar" buttons (common on confirmation)
        add_to_calendar = False
        try:
            calendar_btns = page.locator('a[href$=".ics"], button:has-text("Add to Calendar")')
            add_to_calendar = await calendar_btns.count() > 0
        except Exception:
            pass
        
        # Get ICS link if available
        ics_url = None
        try:
            ics_link = page.locator('a[href$=".ics"], a[href*=".ics?"]').first
            if await ics_link.count():
                ics_url = await ics_link.get_attribute("href")
        except Exception:
            pass
        
        # Confirmation is OK if ANY of these signals are true
        confirmation_ok = confirmed or invitee_id_in_url or scheduled_in_url or add_to_calendar
        
        results["steps"]["confirmation"] = {
            "ok": confirmation_ok,
            "confirmation_text_found": confirmed,
            "confirmation_text": confirmation_text,
            "url_changed": url_changed,
            "invitee_id_in_url": invitee_id_in_url,
            "scheduled_in_url": scheduled_in_url,
            "add_to_calendar_found": add_to_calendar,
            "final_url": current_url,
            "ics_url": ics_url
        }
        
        # Post-submission screenshot
        try:
            screenshot = f"{screenshot_dir}/calendly_post_submit_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=screenshot, full_page=True)
            results["screenshots"].append(screenshot)
            results["confirmation_screenshot"] = screenshot
        except Exception:
            pass
        
        await browser.close()
        
        # Overall success determination
        if not dry_run:
            # For actual booking, check all steps including confirmation
            booking_successful = (
                results["steps"]["navigation"]["ok"] and
                results["steps"]["date_selection"]["ok"] and
                results["steps"]["time_selection"]["ok"] and
                results["steps"]["next_button"]["ok"] and
                results["steps"]["form_filling"]["ok"] and
                results["steps"]["submission"]["ok"] and
                results["steps"]["confirmation"]["ok"]
            )
            results["ok"] = booking_successful
            results["invitee_name"] = invitee_name
            results["invitee_email"] = invitee_email
            results["confirmation_url"] = current_url if booking_successful else None
            results["ics_url"] = ics_url
            
            if not booking_successful:
                results["reason"] = "booking_failed_after_submit"
                # Determine specific failure
                if not results["steps"]["confirmation"]["ok"]:
                    results["reason"] = "confirmation_not_detected"
        # else: dry_run already set results["ok"] = True above
        
        return results


def main():
    ap = argparse.ArgumentParser(
        description="Safe Calendly slot booking with dry-run mode (default: dry-run ON for safety)."
    )
    ap.add_argument("event_url", help="Calendly event URL")
    ap.add_argument("--date", required=True, help="Target date (YYYY-MM-DD)")
    ap.add_argument("--time", required=True, help='Target time "HH:MM" or "h:mma"')
    ap.add_argument("--name", required=True, dest="invitee_name", help="Invitee name")
    ap.add_argument("--email", required=True, dest="invitee_email", help="Invitee email")
    ap.add_argument("--tz", default="America/New_York", dest="timezone", help="IANA timezone")
    ap.add_argument("--answer", action="append", default=[], help='Custom Q&A: "Label=Answer"')
    ap.add_argument("--guest", action="append", default=[], help="Guest email(s)")
    ap.add_argument("--months-ahead", type=int, default=4, help="Months to advance if needed")
    ap.add_argument("--headful", action="store_true", help="Run visible browser")
    ap.add_argument("--settle-ms", type=int, default=1000, help="Wait after submit for confirmation")
    ap.add_argument("--screenshot-dir", default="/tmp", help="Screenshot directory")
    
    # Safety flags
    booking_group = ap.add_mutually_exclusive_group()
    booking_group.add_argument("--dry-run", action="store_true", default=True,
                              help="Validate flow without submitting (DEFAULT - safe mode)")
    booking_group.add_argument("--confirm-booking", action="store_true",
                              help="⚠️  ACTUALLY SUBMIT the booking (creates real calendar event!)")
    
    ap.add_argument("--json", action="store_true", help="Output JSON")
    args = ap.parse_args()
    
    # Parse answers
    answers = {}
    for item in args.answer:
        if "=" in item:
            k, v = item.split("=", 1)
            answers[k.strip()] = v.strip()
    
    # Determine dry-run mode
    is_dry_run = not args.confirm_booking
    
    # Warn if real booking
    if not is_dry_run:
        print("⚠️  WARNING: --confirm-booking flag set!")
        print("⚠️  This will create a REAL calendar booking!")
        print("")
        response = input("Type 'YES' to confirm: ")
        if response.strip() != "YES":
            print("Cancelled.")
            sys.exit(0)
        print("")
    
    result = _run(book_slot(
        event_url=args.event_url,
        date_iso=args.date,
        time_str=args.time,
        invitee_name=args.invitee_name,
        invitee_email=args.invitee_email,
        timezone=args.timezone,
        answers=answers,
        guests=args.guest or [],
        dry_run=is_dry_run,
        headless=not args.headful,
        click_months_ahead=args.months_ahead,
        settle_ms=args.settle_ms,
        screenshot_dir=args.screenshot_dir
    ))
    
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 70)
        if result.get("dry_run"):
            print("CALENDLY BOOKING DRY-RUN TEST RESULTS")
        else:
            print("CALENDLY BOOKING ATTEMPT RESULTS")
        print("=" * 70)
        print()
        
        # Report each step
        for step_name, step_data in result.get("steps", {}).items():
            status = "✅" if step_data.get("ok") else "❌"
            print(f"{status} {step_name.replace('_', ' ').title()}: {step_data.get('ok', False)}")
            if not step_data.get("ok") and "error" in step_data:
                print(f"   Error: {step_data['error']}")
            if step_data.get("message"):
                print(f"   {step_data['message']}")
        
        print()
        
        if result.get("screenshots"):
            print(f"📸 Screenshots: {len(result['screenshots'])}")
            for ss in result["screenshots"]:
                print(f"   {ss}")
            print()
        
        if result.get("ok"):
            if result.get("dry_run"):
                print("✅ DRY-RUN SUCCESSFUL!")
                print("   All validation steps passed.")
                print("   Ready for actual booking with --confirm-booking flag.")
            else:
                print("✅ BOOKING SUCCESSFUL!")
                print(f"   Confirmation URL: {result.get('confirmation_url')}")
                if result.get("ics_url"):
                    print(f"   ICS Download: {result['ics_url']}")
        else:
            print("❌ FAILED")
            print(f"   Reason: {result.get('reason', 'unknown')}")
        
        print()
        print("=" * 70)
    
    sys.exit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()

