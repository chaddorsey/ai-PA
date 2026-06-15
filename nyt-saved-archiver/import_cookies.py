"""Import a Netscape cookies.txt (exported from the user's logged-in regular Chrome)
into the fetch profile, so the fetch loop reuses that already-earned NYT session.

MUST launch with channel="chrome" (same as fetch) — Chrome and bundled Chromium
encrypt cookie values with different keys, so a mismatch would make NYT-S unreadable.
Skips the exported DataDome token to keep this profile's own (fingerprint-matched) one.
"""
import sys

from playwright.sync_api import sync_playwright

from nyt_saved_archiver.cookies import parse_cookies_txt

SKIP = {"datadome", "_dd_s", "_dd_s_v2"}


def main() -> int:
    profile, cookies_file = sys.argv[1], sys.argv[2]
    cookies = [c for c in parse_cookies_txt(cookies_file) if c["name"] not in SKIP]
    nyt_s = any(c["name"] == "NYT-S" for c in cookies)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile, channel="chrome", headless=True)
        ctx.add_cookies(cookies)
        ctx.close()
    print(f"imported {len(cookies)} cookies into {profile}")
    print(f"NYT-S present in import: {nyt_s}")
    if not nyt_s:
        print("WARNING: no NYT-S in the export — you may not have been logged in when you exported.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
