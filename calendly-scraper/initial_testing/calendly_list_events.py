#!/usr/bin/env python3
import asyncio, argparse, re
from urllib.parse import urlparse, urljoin

from playwright.async_api import async_playwright

async def list_events(profile_url: str, wait: float = 8.0):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(profile_url, wait_until="domcontentloaded")

        # Try to dismiss cookie/GDPR banners if present
        for sel in [
            '#onetrust-accept-btn-handler',
            'button:has-text("Accept")',
            'button:has-text("Got it")',
            'button:has-text("I agree")',
        ]:
            try:
                btn = page.locator(sel)
                if await btn.count():
                    await btn.click(timeout=1500)
                    break
            except Exception:
                pass

        # Prefer data-id selector used on many Calendly pages
        anchors = page.locator('a[data-id="event-type"]')
        # Wait briefly for JS to render anchors
        try:
            await anchors.first.wait_for(timeout=int(wait * 1000))
        except Exception:
            pass

        items = []
        count = await anchors.count()
        for i in range(count):
            a = anchors.nth(i)
            href = await a.get_attribute("href")
            title_node = a.locator('[data-id="event-type-header-title"]').first
            title = (await title_node.text_content()) if await title_node.count() else (await a.text_content())
            if href:
                purl = urlparse(profile_url)
                abs_url = urljoin(f"{purl.scheme}://{purl.netloc}/", href.lstrip("/")).split("?")[0]
                items.append((abs_url.strip(), (title or "").strip()))

        # Fallback selector: any anchor to /<owner>/<slug>
        if not items:
            purl = urlparse(profile_url)
            owner = [x for x in purl.path.split("/") if x][0]
            alt = page.locator(f'a[href*="/{owner}/"]')
            for i in range(await alt.count()):
                a = alt.nth(i)
                href = await a.get_attribute("href")
                if not href:
                    continue
                abs_url = urljoin(f"{purl.scheme}://{purl.netloc}/", href.lstrip("/")).split("?")[0]
                parts = [x for x in urlparse(abs_url).path.split("/") if x]
                if len(parts) == 2:  # canonical /owner/slug
                    title = (await a.text_content()) or ""
                    items.append((abs_url.strip(), title.strip()))

        await browser.close()
        # de-dupe while preserving order
        seen = set()
        out = []
        for u, t in items:
            if u not in seen:
                out.append((u, t)); seen.add(u)
        return out

async def main():
    ap = argparse.ArgumentParser(description="List Calendly event URLs from a public profile (rendered DOM)")
    ap.add_argument("profile_url", help="https://calendly.com/<owner>")
    ap.add_argument("--wait", type=float, default=8.0, help="Seconds to wait for event links to render")
    args = ap.parse_args()
    events = await list_events(args.profile_url, wait=args.wait)
    if not events:
        print("(no events discovered)")
        return
    for url, title in events:
        print(f"{url}\t{title}")

if __name__ == "__main__":
    asyncio.run(main())
