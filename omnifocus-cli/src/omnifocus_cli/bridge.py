import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BRIDGE_URL = "http://host.docker.internal:8889"


def build_payload(method: str, params: dict | None = None) -> str:
    """Build the JSON payload for the OmniFocus plugin."""
    return json.dumps({"method": method, "params": params or {}})


def build_applescript(method: str, params: dict | None = None) -> str:
    """Build the AppleScript that calls the OmniFocus plugin via base64-encoded JSON."""
    payload = build_payload(method, params)
    b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return f"""tell application "OmniFocus"
  set _res to evaluate javascript "var C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',s='{b64}',r='';for(var i=0;i<s.length;){{var a=C.indexOf(s[i++]),b=C.indexOf(s[i++]),c=C.indexOf(s[i++]),d=C.indexOf(s[i++]);r+=String.fromCharCode((a<<2)|(b>>4));if(c>=0)r+=String.fromCharCode(((b&15)<<4)|(c>>2));if(d>=0)r+=String.fromCharCode(((c&3)<<6)|d)}}var p=PlugIn.find('omnifocus-mcp');if(!p)throw new Error('Plugin not found');var lib=p.library('omnifocus-mcp');JSON.stringify(lib.request(r))"
end tell
return _res
"""


def _call_via_osascript(method: str, params: dict | None = None) -> dict:
    """Call OmniFocus via osascript and return parsed JSON result."""
    script = build_applescript(method, params)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".applescript", delete=False) as f:
        f.write(script)
        script_path = Path(f.name)
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", str(script_path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"osascript failed (exit {result.returncode}): {result.stderr.strip()}")
        raw = result.stdout.strip()
        parsed = json.loads(raw)
        # osascript may double-encode: JSON.stringify wraps the plugin's
        # JSON string result in quotes, so first json.loads yields a str.
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        if isinstance(parsed, dict) and "error" in parsed:
            raise RuntimeError(f"OmniFocus plugin error: {parsed['error']}")
        if isinstance(parsed, dict):
            return parsed.get("result", parsed)
        return parsed
    finally:
        script_path.unlink(missing_ok=True)


def _call_via_http(method: str, params: dict | None = None) -> dict:
    """Call OmniFocus via HTTP bridge and return parsed JSON result."""
    bridge_url = os.environ.get("OMNIFOCUS_BRIDGE_URL", DEFAULT_BRIDGE_URL)
    url = f"{bridge_url}/execute"
    body = json.dumps({"command": method, "args": params or {}}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"HTTP bridge request failed: {exc}") from exc

    parsed = json.loads(raw)
    # Bridge returns {"success": true, "result": "<json-string>"}
    # The result value may be a JSON-encoded string that needs a second parse.
    if isinstance(parsed, dict) and "error" in parsed:
        raise RuntimeError(f"OmniFocus bridge error: {parsed['error']}")
    result = parsed.get("result", parsed)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (json.JSONDecodeError, ValueError):
            pass
    return result


def call_omnifocus(method: str, params: dict | None = None) -> dict:
    """Call OmniFocus via osascript (local) or HTTP bridge (Docker)."""
    if shutil.which("osascript"):
        return _call_via_osascript(method, params)
    return _call_via_http(method, params)
