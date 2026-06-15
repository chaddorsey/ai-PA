"""Load + normalize the saved-URL list (format-tolerant)."""
from urllib.parse import urlsplit, urlunsplit


def _normalize(u: str) -> str:
    parts = urlsplit(u.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))  # drop query/fragment


def load_urls(path: str) -> list[str]:
    seen, out = set(), []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "nytimes.com" not in line:
            continue
        n = _normalize(line)
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out
