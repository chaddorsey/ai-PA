"""One-time NYT hand-login into a persistent browser profile the fetch loop reuses.

Run as a real file (NOT via stdin heredoc) so input() can read from the terminal.
"""
import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    profile = sys.argv[1]
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile, headless=False)
        page = ctx.new_page()
        page.goto("https://www.nytimes.com/saved")
        input("Log in fully in the opened window, confirm you can see your Saved page, then press Enter here...")
        ctx.close()
    print("login session saved to", profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
