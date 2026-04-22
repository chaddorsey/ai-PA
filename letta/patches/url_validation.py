"""Patched Letta MCP SSRF guard (bind-mounted over /app/letta/helpers/url_validation.py).

Upstream 0.16.7 rejects any MCP server URL whose hostname resolves to a
non-globally-routable IP. That kills every MCP server we reach via
`host.docker.internal` or a Docker service name, since both resolve to
private/reserved IPs.

This patch keeps the original guard but adds two opt-in escape hatches:

1. `LETTA_MCP_ALLOWED_HOSTS` env var — comma-separated hostnames (or hostname
   suffixes prefixed with `.`) that skip IP resolution entirely. Example:
       LETTA_MCP_ALLOWED_HOSTS=host.docker.internal
2. `LETTA_MCP_ALLOW_PRIVATE_IPS=1` — blanket bypass for the IP-scope check
   (host-specific allowlist preferred; keep this for emergency unblock).

Default behavior (no env vars set) matches upstream exactly.
"""

import ipaddress
import os
import socket
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.",
    "metadata.google.internal",
    "metadata.google.internal.",
}

_BLOCKED_SUFFIXES = (
    ".local",
    ".localdomain",
    ".home.arpa",
    ".svc",
    ".cluster.local",
)


def _normalize_hostname(hostname: str) -> str:
    return hostname.rstrip(".").lower()


def _is_blocked_hostname(hostname: str) -> bool:
    normalized = _normalize_hostname(hostname)
    blocked_hostnames = {_normalize_hostname(value) for value in _BLOCKED_HOSTNAMES}
    return normalized in blocked_hostnames or any(normalized.endswith(suffix) for suffix in _BLOCKED_SUFFIXES)


def _allowlisted_hostname(hostname: str) -> bool:
    """Return True if hostname (or a suffix) is in LETTA_MCP_ALLOWED_HOSTS."""
    raw = os.environ.get("LETTA_MCP_ALLOWED_HOSTS", "").strip()
    if not raw:
        return False
    normalized = _normalize_hostname(hostname)
    for entry in raw.split(","):
        entry = _normalize_hostname(entry.strip())
        if not entry:
            continue
        if entry.startswith("."):
            if normalized.endswith(entry):
                return True
        elif normalized == entry:
            return True
    return False


def _allow_private_ips() -> bool:
    return os.environ.get("LETTA_MCP_ALLOW_PRIVATE_IPS", "").strip().lower() in ("1", "true", "yes")


def validate_mcp_server_url(url: str, *, resolve_hostname: bool = True) -> str:
    """Validate MCP HTTP(S) URLs and reject internal/private targets."""
    if not url:
        raise ValueError("server_url cannot be empty")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"server_url must start with 'http://' or 'https://', got: '{url}'")
    if not parsed.netloc:
        raise ValueError(f"server_url must have a valid host, got: '{url}'")
    if parsed.hostname is None:
        raise ValueError("Missing hostname")

    hostname = _normalize_hostname(parsed.hostname)
    if _is_blocked_hostname(hostname):
        raise ValueError(f"Blocked internal hostname: {parsed.hostname}")

    # Opt-in hostname allowlist: skip all further resolution/IP-scope checks.
    if _allowlisted_hostname(hostname):
        return url

    try:
        parsed_ip = ipaddress.ip_address(hostname)
    except ValueError:
        parsed_ip = None

    if parsed_ip is not None:
        if not parsed_ip.is_global and not _allow_private_ips():
            raise ValueError(f"Non-public IP not allowed: {parsed.hostname}")
        return url

    if not resolve_hostname:
        return url

    try:
        infos = socket.getaddrinfo(
            hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve hostname: {parsed.hostname}") from exc

    seen_ips = set()
    for _, _, _, _, sockaddr in infos:
        ip_text = sockaddr[0]
        if ip_text in seen_ips:
            continue
        seen_ips.add(ip_text)
        if not ipaddress.ip_address(ip_text).is_global and not _allow_private_ips():
            raise ValueError(f"Hostname resolves to non-public IP: {ip_text}")

    if not seen_ips:
        raise ValueError(f"Cannot resolve hostname: {parsed.hostname}")

    return url
