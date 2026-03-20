from __future__ import annotations

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
DEFAULT_PLUGIN_ID = "omnifocus-mcp"
DEFAULT_LIBRARY_ID = "omnifocus-mcp"
BRIDGE_TIMEOUT = int(os.environ.get("OMNIFOCUS_BRIDGE_TIMEOUT", "120"))

# Inline base64 decoder used inside OmniFocus evaluate javascript.
# Pure ASCII, no characters that need escaping in AppleScript strings.
_B64_DECODE_JS = (
    "var C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',"
    "s='{b64}',r='';"
    "for(var i=0;i<s.length;)"
    "{{var a=C.indexOf(s[i++]),b=C.indexOf(s[i++]),"
    "c=C.indexOf(s[i++]),d=C.indexOf(s[i++]);"
    "r+=String.fromCharCode((a<<2)|(b>>4));"
    "if(c>=0)r+=String.fromCharCode(((b&15)<<4)|(c>>2));"
    "if(d>=0)r+=String.fromCharCode(((c&3)<<6)|d)}}"
)


def _is_default_plugin(plugin: str | None, library: str | None) -> bool:
    """Return True when the target is the default MCP plugin."""
    return (
        (plugin is None or plugin == DEFAULT_PLUGIN_ID)
        and (library is None or library == DEFAULT_LIBRARY_ID)
    )


def build_payload(method: str, params: dict | None = None) -> str:
    """Build the JSON payload for the OmniFocus plugin."""
    return json.dumps({"method": method, "params": params or {}})


def build_applescript(
    method: str,
    params: dict | None = None,
    *,
    plugin: str | None = None,
    library: str | None = None,
) -> str:
    """Build AppleScript that calls an OmniFocus plugin via base64-encoded JSON.

    When *plugin*/*library* are ``None`` (or match the defaults), the legacy
    MCP ``request()`` dispatcher path is used — identical to the previous
    behaviour.  When a different plugin is specified the generated script
    calls the library method directly.
    """
    resolved_params = params or {}

    if _is_default_plugin(plugin, library):
        # --- Legacy MCP path (unchanged) ---
        payload = build_payload(method, resolved_params)
        b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")
        js_body = _B64_DECODE_JS.format(b64=b64)
        js_body += (
            f"var p=PlugIn.find('{DEFAULT_PLUGIN_ID}');"
            "if(!p)throw new Error('Plugin not found');"
            f"var lib=p.library('{DEFAULT_LIBRARY_ID}');"
            "JSON.stringify(lib.request(r))"
        )
    else:
        # --- Direct library call path ---
        # Use base64 encoding (same as MCP path) but with unique variable names
        # to avoid any potential conflicts in the OmniFocus JS context.
        plug_id = plugin or DEFAULT_PLUGIN_ID
        lib_id = library or DEFAULT_LIBRARY_ID
        params_json = json.dumps(resolved_params)
        b64 = base64.b64encode(params_json.encode("utf-8")).decode("ascii")
        # Use _X prefix for decoder vars to avoid conflicts
        js_body = (
            f"var _C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',"
            f"_s='{b64}',_r='';"
            "for(var _i=0;_i<_s.length;){"
            "var _a=_C.indexOf(_s[_i++]),_b=_C.indexOf(_s[_i++]),"
            "_c=_C.indexOf(_s[_i++]),_d=_C.indexOf(_s[_i++]);"
            "_r+=String.fromCharCode((_a<<2)|(_b>>4));"
            "if(_c>=0)_r+=String.fromCharCode(((_b&15)<<4)|(_c>>2));"
            "if(_d>=0)_r+=String.fromCharCode(((_c&3)<<6)|_d)}"
            f"var _p=PlugIn.find('{plug_id}');"
            f"if(!_p)throw new Error('Plugin {plug_id} not found');"
            f"var _lib=_p.library('{lib_id}');"
            f"if(!_lib)throw new Error('Library {lib_id} not found');"
            "var _params=JSON.parse(_r);"
            "var _keys=Object.keys(_params);"
            "var _out;"
            f"if(_keys.length===0)_out=_lib.{method}();"
            f"else if(_keys.length===1)_out=_lib.{method}(_params[_keys[0]]);"
            f"else _out=_lib.{method}(_params);"
            "JSON.stringify(_out)"
        )

    return f"""tell application "OmniFocus"
  set _res to evaluate javascript "{js_body}"
end tell
return _res
"""


def _call_via_osascript(
    method: str,
    params: dict | None = None,
    *,
    plugin: str | None = None,
    library: str | None = None,
) -> dict:
    """Call OmniFocus via osascript and return parsed JSON result."""
    script = build_applescript(method, params, plugin=plugin, library=library)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".applescript", delete=False) as f:
        f.write(script)
        script_path = Path(f.name)
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", str(script_path)],
            capture_output=True, text=True, timeout=BRIDGE_TIMEOUT,
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


def _call_via_http(
    method: str,
    params: dict | None = None,
    *,
    plugin: str | None = None,
    library: str | None = None,
) -> dict:
    """Call OmniFocus via HTTP bridge and return parsed JSON result."""
    bridge_url = os.environ.get("OMNIFOCUS_BRIDGE_URL", DEFAULT_BRIDGE_URL)
    url = f"{bridge_url}/execute"
    payload: dict = {"command": method, "args": params or {}}
    # Only include plugin/library when they differ from defaults so
    # existing bridge servers that don't understand these fields keep working.
    if not _is_default_plugin(plugin, library):
        payload["plugin"] = plugin or DEFAULT_PLUGIN_ID
        payload["library"] = library or DEFAULT_LIBRARY_ID
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=BRIDGE_TIMEOUT) as resp:
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


def call_omnifocus(
    method: str,
    params: dict | None = None,
    *,
    plugin: str | None = None,
    library: str | None = None,
) -> dict:
    """Call OmniFocus via osascript (local) or HTTP bridge (Docker).

    Parameters
    ----------
    method:
        The method name to invoke on the target plugin library.
    params:
        Optional dictionary of parameters.
    plugin:
        OmniFocus plugin identifier.  Defaults to the MCP plugin.
    library:
        Library name within the plugin.  Defaults to the MCP library.
    """
    if shutil.which("osascript"):
        return _call_via_osascript(method, params, plugin=plugin, library=library)
    return _call_via_http(method, params, plugin=plugin, library=library)
