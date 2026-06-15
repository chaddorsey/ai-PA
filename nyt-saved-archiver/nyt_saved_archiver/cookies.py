"""Parse a Netscape cookies.txt export into Playwright add_cookies() dicts.

Plan B: reuse the session the user's real Chrome already earned (exported via a
'Get cookies.txt' extension), instead of logging in through automation.
"""

HTTPONLY_PREFIX = "#HttpOnly_"


def parse_cookies_txt(path: str) -> list[dict]:
    out = []
    for line in open(path, encoding="utf-8"):
        raw = line.rstrip("\n")
        if not raw.strip():
            continue
        http_only = False
        if raw.startswith(HTTPONLY_PREFIX):
            http_only = True
            raw = raw[len(HTTPONLY_PREFIX):]
        elif raw.startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) != 7:
            continue
        domain, _include_sub, path_, secure, expiry, name, value = parts
        try:
            exp = int(expiry)
        except ValueError:
            exp = 0
        out.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path_,
            "secure": secure.upper() == "TRUE",
            "httpOnly": http_only,
            "expires": exp if exp > 0 else -1,
            "sameSite": "Lax",
        })
    return out
