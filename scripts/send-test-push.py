#!/usr/bin/env python3
"""Send a synthetic push to every subscribed device for one email.

Convenience wrapper around the curator's POST /push/test endpoint.
Useful when sanity-checking pushes from CLI rather than poking the
profile-popover button in a browser.

Usage:
    ./scripts/send-test-push.py cdorsey@concord.org
"""
import sys
import urllib.parse
import urllib.request


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    email = sys.argv[1]
    url = ("http://127.0.0.1:5141/push/test?"
            + urllib.parse.urlencode({"email": email}))
    req = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='ignore')}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
