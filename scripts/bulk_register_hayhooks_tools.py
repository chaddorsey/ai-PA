#!/usr/bin/env python3
"""
Bulk-register Hayhooks /run pipelines as Letta tools and (optionally) attach them to an agent.

Fixes vs. previous script:
- All generated function params default to None (or schema default), avoiding
  "non-default argument follows default argument" errors.
- Payload is built from locals() with a None filter (no nested/indented blocks),
  avoiding IndentationError during Letta's exec().
- Every tool json_schema includes a "required": [] list to satisfy Letta's shim.
- Agent attach merges with existing tools (no removal of core tools).
- Interactive "Register all (Y/n)" + simple checkbox menu to deselect endpoints.

Env vars:
  HAYHOOKS_BASE        (default: http://localhost:1416)
  LETTA_BASE           (default: http://localhost:8283)
  AGENT_ID             (optional: attach tools to this agent)
  RETURN_CHAR_LIMIT    (default: 200000)
  INCLUDE_NON_RUN      (optional: if "1", also list non-/run POST endpoints)
"""

import os
import sys
import json
import re
import urllib.request
import urllib.parse

HAYHOOKS_BASE = os.environ.get("HAYHOOKS_BASE", "http://localhost:1416")
LETTA_BASE = os.environ.get("LETTA_BASE", "http://localhost:8283")
AGENT_ID = os.environ.get("AGENT_ID")  # optional
RETURN_CHAR_LIMIT = int(os.environ.get("RETURN_CHAR_LIMIT", "200000"))
INCLUDE_NON_RUN = os.environ.get("INCLUDE_NON_RUN", "").strip() == "1"

# ---------- HTTP helpers ----------
def _http_request(url: str, data: dict | None = None, method: str | None = None):
    try:
        if data is not None:
            payload = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(url)
        if method:
            req.method = method
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8")
        except Exception:
            detail = str(e)
        raise RuntimeError(f"HTTP {e.code} {url}\n{detail}")

def http_get(url: str):
    return _http_request(url)

def http_post(url: str, payload: dict):
    return _http_request(url, payload, method="POST")

def http_patch(url: str, payload: dict):
    return _http_request(url, payload, method="PATCH")

def http_delete(url: str):
    return _http_request(url, method="DELETE")

# ---------- OpenAPI parsing ----------
def load_openapi():
    return http_get(f"{HAYHOOKS_BASE}/openapi.json")

def list_post_endpoints(openapi):
    """
    Return list of tuples: (path, post_obj). If INCLUDE_NON_RUN is False, only /run suffix.
    """
    paths = openapi.get("paths", {})
    out = []
    for path, methods in paths.items():
        post = (methods or {}).get("post")
        if not post:
            continue
        if not INCLUDE_NON_RUN and not path.endswith("/run"):
            continue
        out.append((path, post))
    out.sort()
    return out

def resolve_schema(openapi, schema_node):
    """Return a concrete JSON schema dict (resolve $ref if present)."""
    if not schema_node:
        return None
    if "$ref" in schema_node:
        ref = schema_node["$ref"]  # e.g., "#/components/schemas/searchRunRequest"
        m = re.match(r"#/components/schemas/(?P<key>.+)", ref)
        if not m:
            return None
        key = m.group("key")
        return (openapi.get("components", {}).get("schemas", {}) or {}).get(key)
    return schema_node

def get_request_schema(openapi, post_obj):
    rb = (post_obj or {}).get("requestBody", {})
    content = (rb.get("content") or {})
    appjson = content.get("application/json", {})
    schema = appjson.get("schema")
    return resolve_schema(openapi, schema)

# ---------- Codegen for tool function ----------
def sanitize_name(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", s)
    if re.match(r"^\d", s):
        s = "_" + s
    return s

def derive_tool_name_from_path(path: str) -> str:
    # /search/run            -> hayhooks_search
    # /search_emails/run     -> hayhooks_search_emails
    # /foo/bar/custom        -> hayhooks_foo_bar_custom  (if INCLUDE_NON_RUN=1)
    parts = [p for p in path.strip("/").split("/") if p]
    if parts and parts[-1] == "run":
        parts = parts[:-1]
    return "hayhooks_" + "_".join(parts) if parts else "hayhooks_root"

def _py_type(prop_type: str | None) -> str:
    return {
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "list",
        "object": "dict",
        "string": "str",
    }.get(prop_type or "string", "str")

def _default_literal(prop: dict) -> str:
    # If the OpenAPI has a default, use it; else default to None so ALL params remain optional.
    if prop and "default" in prop:
        d = prop["default"]
        return "=" + (json.dumps(d) if isinstance(d, str) else repr(d))
    return "=None"

def generate_function_code(tool_name: str, path: str, schema: dict | None) -> str:
    """
    Safer generator:
      - All params default to None (or schema default) to avoid default-order errors.
      - Build payload from locals() and skip None (no large multiline dict literals).
    """
    props = (schema or {}).get("properties", {}) if schema else {}
    keys = sorted(props.keys())

    sig_parts = []
    doc_args_lines = []
    for k in keys:
        prop = props.get(k, {}) or {}
        ann = _py_type(prop.get("type"))
        sig_parts.append(f"{sanitize_name(k)}: {ann}{_default_literal(prop)}")
        desc = (prop.get("description") or "").strip()
        if desc:
            doc_args_lines.append(f"        {k} ({ann}): {desc}")
        else:
            doc_args_lines.append(f"        {k} ({ann})")

    sig = ", ".join(sig_parts)
    doc_args = "\n".join(doc_args_lines) if doc_args_lines else "        (No parameters)"

    func = f'''import os, json, urllib.request

HAYHOOKS_BASE_URL = os.environ.get("HAYHOOKS_BASE_URL", "{HAYHOOKS_BASE}")
PIPELINE_PATH = {json.dumps(path)}

def _post_json(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={{"Content-Type":"application/json"}},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))

def {tool_name}({sig}) -> str:
    """
    Call Hayhooks endpoint {path}

    Args:
{doc_args}

    Returns:
        str: The pipeline "result" string, or the raw JSON if "result" is missing.
    """
    # Build payload from provided args (skip None)
    _locals = locals()
    payload = {{ k: v for k, v in _locals.items()
                if k not in ("HAYHOOKS_BASE_URL","PIPELINE_PATH") and v is not None }}

    url = f"{{HAYHOOKS_BASE_URL}}{{PIPELINE_PATH}}"
    out = _post_json(url, payload)
    return out.get("result", json.dumps(out))
'''
    return func

# ---------- Letta helpers ----------
def tool_exists_by_name(name: str) -> str | None:
    url = f"{LETTA_BASE}/v1/tools/?limit=1&name={urllib.parse.quote(name)}"
    arr = http_get(url) or []
    for t in arr:
        if t.get("name") == name:
            return t.get("id")
    return None

def create_tool(source_code: str, json_schema: dict | None):
    payload = {"source_code": source_code, "return_char_limit": RETURN_CHAR_LIMIT}
    if json_schema:
        payload["json_schema"] = json_schema
    return http_post(f"{LETTA_BASE}/v1/tools/", payload)

def attach_tools_to_agent(agent_id: str, tool_ids: list[str]) -> dict:
    # Merge with existing
    agent = http_get(f"{LETTA_BASE}/v1/agents/{agent_id}") or {}
    existing = [t.get("id") for t in (agent.get("tools") or []) if t.get("id")]
    merged = list(dict.fromkeys(existing + tool_ids))  # dedupe, preserve order
    return http_patch(f"{LETTA_BASE}/v1/agents/{agent_id}", {"tool_ids": merged})

def ensure_schema_required(schema_params: dict | None) -> dict:
    """
    Ensure schema has the structure Letta expects, especially "required": [].
    """
    if schema_params is None:
        schema_params = {"type": "object", "properties": {}, "required": []}
        return schema_params
    if "type" not in schema_params:
        schema_params = dict(schema_params)
        schema_params["type"] = "object"
    if "properties" not in schema_params or schema_params["properties"] is None:
        schema_params = dict(schema_params)
        schema_params["properties"] = {}
    if "required" not in schema_params or schema_params["required"] is None:
        schema_params = dict(schema_params)
        schema_params["required"] = []
    return schema_params

# ---------- Interactive UI ----------
def prompt_yes_no(prompt: str, default_yes=True) -> bool:
    default = "Y/n" if default_yes else "y/N"
    resp = input(f"{prompt} ({default}) ").strip().lower()
    if not resp:
        return default_yes
    return resp in ("y", "yes")

def checkbox_menu(items: list[str]) -> list[bool]:
    """
    items: list of strings. Returns list of booleans (selected).
    Controls:
      - Enter: continue
      - numbers (1-based), space/comma separated: toggle those indices
      - a: toggle all
      - q: abort
    """
    selected = [True] * len(items)
    while True:
        print("\nSelect endpoints to register (toggle by number, 'a' toggle all, Enter to continue, 'q' to quit):")
        for i, s in enumerate(items, 1):
            mark = "[x]" if selected[i - 1] else "[ ]"
            print(f" {i:>2}. {mark}  {s}")
        cmd = input("> ").strip().lower()
        if cmd == "":
            return selected
        if cmd == "q":
            print("Aborted.")
            sys.exit(1)
        if cmd == "a":
            all_on = not all(selected)
            selected = [all_on] * len(items)
            continue
        toks = re.split(r"[,\s]+", cmd)
        for t in toks:
            if not t:
                continue
            if t.isdigit():
                idx = int(t) - 1
                if 0 <= idx < len(items):
                    selected[idx] = not selected[idx]
            else:
                print(f"Ignoring input: {t}")

# ---------- Main ----------
def main():
    print(f"HAYHOOKS_BASE = {HAYHOOKS_BASE}")
    print(f"LETTA_BASE    = {LETTA_BASE}")
    if AGENT_ID:
        print(f"AGENT_ID      = {AGENT_ID} (will attach tools)")
    else:
        print("AGENT_ID      = (not set; tools will NOT be attached)")
    print(f"INCLUDE_NON_RUN = {'1' if INCLUDE_NON_RUN else '0'}  (list non-/run POST endpoints: {INCLUDE_NON_RUN})")

    openapi = load_openapi()
    posts = list_post_endpoints(openapi)
    if not posts:
        print("No matching POST endpoints found in Hayhooks OpenAPI.")
        sys.exit(1)

    # Build (name, path, schema) entries
    entries = []
    for path, post in posts:
        schema = get_request_schema(openapi, post)
        name = derive_tool_name_from_path(path)
        entries.append((name, path, schema))

    print(f"\nFound {len(entries)} endpoint(s).")
    if prompt_yes_no("Register all?", default_yes=True):
        selected = [True] * len(entries)
    else:
        selected = checkbox_menu([f"{name}  ({path})" for (name, path, _) in entries])

    to_register = [e for e, sel in zip(entries, selected) if sel]
    if not to_register:
        print("Nothing selected.")
        sys.exit(0)

    created_ids: list[str] = []
    for (tool_name, path, schema) in to_register:
        # Generate function
        source_code = generate_function_code(tool_name, path, schema)

        # Build json_schema (ensure "required": [])
        schema_params = ensure_schema_required(schema)
        json_schema = {
            "name": tool_name,
            "description": f"Call Hayhooks endpoint {path}",
            "parameters": schema_params,
        }

        # Skip if already exists
        existing_id = tool_exists_by_name(tool_name)
        if existing_id:
            print(f"= tool exists: {tool_name}  (id={existing_id})")
            created_ids.append(existing_id)
            continue

        try:
            resp = create_tool(source_code, json_schema)
            tid = (resp or {}).get("id")
            tname = (resp or {}).get("name", tool_name)
            print(f"+ created tool: {tname}  (id={tid})  <- {path}")
            if tid:
                created_ids.append(tid)
        except RuntimeError as e:
            print(f"! failed to create {tool_name} for {path}:\n{e}")

    if AGENT_ID and created_ids:
        try:
            patched = attach_tools_to_agent(AGENT_ID, created_ids)
            final_tools = [t.get("name") for t in (patched.get("tools") or [])]
            print(f"\nAttached {len(created_ids)} tools to agent {AGENT_ID}.")
            print("Agent tools now:", ", ".join(final_tools) if final_tools else "(none)")
        except RuntimeError as e:
            print(f"! failed to attach tools to agent {AGENT_ID}:\n{e}")

    print("\nDone.")

if __name__ == "__main__":
    main()