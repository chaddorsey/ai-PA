#!/usr/bin/env python3
"""
Register Drive Analytics Tools with Letta via HTTP API

This script reads the drive_analytics_tools.py module and creates Letta tools
that import from it. Since the functions are complex and share helpers, we'll
include the module path and let Letta import from it.
"""

import os
import json
import urllib.request

LETTA_BASE = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_ID = os.getenv("LETTA_AGENT_ID", "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8")

# Path to the tools module
TOOLS_MODULE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "drive_analytics_tools.py"))


def http_post(url, data):
    """Make HTTP POST request."""
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"HTTP Error {e.code}: {error_body}")
        return None


def http_get(url):
    """Make HTTP GET request."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f"GET Error: {e}")
        return None


def http_patch(url, data):
    """Make HTTP PATCH request."""
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method='PATCH')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"PATCH Error {e.code}: {error_body}")
        return None


def create_tool(source_code, tags=None):
    """Create a tool in Letta."""
    payload = {
        "source_code": source_code,
        "tags": tags or []
    }
    return http_post(f"{LETTA_BASE}/v1/tools/", payload)


def get_all_tools():
    """Get all tools."""
    tools = http_get(f"{LETTA_BASE}/v1/tools/")
    return tools if isinstance(tools, list) else []


def find_tool_by_name(name):
    """Find a tool by name."""
    tools = get_all_tools()
    for tool in tools:
        if tool.get("name") == name:
            return tool
    return None


def attach_tools_to_agent(agent_id, tool_ids):
    """Attach tools to agent."""
    # Get current agent
    agent = http_get(f"{LETTA_BASE}/v1/agents/{agent_id}")
    if not agent:
        return False
    
    current_tool_refs = agent.get("tools", [])
    
    # Extract current tool IDs (handle both string and dict formats)
    current_tool_ids = set()
    for ref in current_tool_refs:
        if isinstance(ref, dict):
            current_tool_ids.add(ref.get("id"))
        elif isinstance(ref, str):
            current_tool_ids.add(ref)
    
    # Ensure new tool IDs are strings
    new_tool_ids = [t if isinstance(t, str) else t.get("id", t) for t in tool_ids]
    
    # Merge tool lists (convert to list of strings, dedupe, preserve order)
    all_tool_ids = list(dict.fromkeys(list(current_tool_ids) + new_tool_ids))
    
    # Update agent - use 'tool_ids' field (not 'tools')
    result = http_patch(f"{LETTA_BASE}/v1/agents/{agent_id}", {"tool_ids": all_tool_ids})
    return result is not None


def create_tool_source(function_name, docstring, params):
    """Create tool source code that imports from the module."""
    # Read the actual function from the module to get its signature
    with open(TOOLS_MODULE_PATH, 'r') as f:
        module_content = f.read()
    
    # Extract the function definition
    import re
    pattern = rf'def {function_name}\([^)]*\)[^:]*:.*?(?=\n\ndef |\n\nclass |\Z)'
    match = re.search(pattern, module_content, re.DOTALL)
    
    if match:
        func_code = match.group(0)
        # Create a standalone version that includes necessary imports
        return f'''import os
import sys
import json
import time
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Add module path and import
sys.path.insert(0, "{os.path.dirname(TOOLS_MODULE_PATH)}")
from drive_analytics_tools import {function_name}
'''
    else:
        # Fallback: just import
        return f'''import os
import sys
sys.path.insert(0, "{os.path.dirname(TOOLS_MODULE_PATH)}")
from drive_analytics_tools import {function_name}
'''


# Tool definitions
TOOLS = [
    {"name": "collect_daily_workspace_activity", "tags": ["drive", "analytics", "workspace"]},
    {"name": "collect_daily_personal_activity", "tags": ["drive", "analytics", "personal"]},
    {"name": "collect_daily_mentions", "tags": ["drive", "analytics", "mentions"]},
    {"name": "calculate_running_averages", "tags": ["drive", "analytics", "averages"]},
    {"name": "initialize_drive_analytics_memory", "tags": ["drive", "analytics", "setup"]},
    {"name": "get_drive_analytics_summary", "tags": ["drive", "analytics", "query"]},
    {"name": "get_drive_trends", "tags": ["drive", "analytics", "query"]},
    {"name": "get_my_drive_activity", "tags": ["drive", "analytics", "query"]},
    {"name": "get_drive_mentions", "tags": ["drive", "analytics", "query"]},
    {"name": "get_document_activity", "tags": ["drive", "analytics", "query"]},
    {"name": "get_top_documents", "tags": ["drive", "analytics", "query"]},
    {"name": "get_recent_my_activity", "tags": ["drive", "analytics", "query"]},
    {"name": "get_drive_file_info", "tags": ["drive", "query", "metadata"]},
]


def main():
    print("="*60)
    print("Drive Analytics Tools Registration")
    print("="*60)
    print()
    print(f"Letta Base: {LETTA_BASE}")
    print(f"Agent ID: {AGENT_ID}")
    print()
    
    registered_tool_ids = []
    
    for tool_def in TOOLS:
        tool_name = tool_def["name"]
        print(f"→ Registering {tool_name}...")
        
        # Check if tool already exists
        existing = find_tool_by_name(tool_name)
        if existing:
            print(f"  → Tool already exists (ID: {existing['id']}), updating...")
            # Delete old tool to recreate with updated signature
            delete_url = f"{LETTA_BASE}/v1/tools/{existing['id']}"
            try:
                req = urllib.request.Request(delete_url, method='DELETE')
                with urllib.request.urlopen(req, timeout=30) as r:
                    print(f"  ✓ Deleted old tool")
            except Exception as e:
                print(f"  ⚠ Could not delete old tool: {e}")
        
        # Always create/update the tool with current signature
        if True:  # Changed from 'else:' to always update
            # Create tool source that imports from module
            # Use the container path where the module will be mounted
            container_module_path = "/app/tools/letta"
            
            # Get the actual function signature from the module
            import inspect
            import importlib.util
            module_path = TOOLS_MODULE_PATH
            spec = importlib.util.spec_from_file_location("drive_analytics_tools", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            func = getattr(module, tool_name)
            sig = inspect.signature(func)
            
            # Build parameter string from signature
            from typing import get_origin, get_args
            params = []
            for param_name, param in sig.parameters.items():
                param_str = param_name
                if param.annotation != inspect.Parameter.empty:
                    ann = param.annotation
                    # Handle typing.Optional properly using get_origin/get_args (Python 3.8+)
                    try:
                        origin = get_origin(ann)
                        args = get_args(ann)
                        if origin is not None:
                            # It's a generic type like Optional[str]
                            if hasattr(origin, '__name__') and origin.__name__ == 'Union':
                                # It's Optional (which is Union[T, None])
                                if len(args) == 2 and type(None) in args:
                                    # Optional[Something]
                                    non_none = [a for a in args if a is not type(None)][0]
                                    if hasattr(non_none, '__name__'):
                                        param_str += f": Optional[{non_none.__name__}]"
                                    else:
                                        param_str += f": Optional[{str(non_none)}]"
                                else:
                                    param_str += f": {str(ann).replace('typing.', '')}"
                            else:
                                param_str += f": {str(ann).replace('typing.', '')}"
                        elif hasattr(ann, '__name__'):
                            param_str += f": {ann.__name__}"
                        else:
                            param_str += f": {str(ann).replace('typing.', '')}"
                    except (AttributeError, TypeError):
                        # Fallback for older Python or simple types
                        if hasattr(ann, '__name__'):
                            param_str += f": {ann.__name__}"
                        else:
                            param_str += f": {str(ann).replace('typing.', '')}"
                if param.default != inspect.Parameter.empty:
                    if param.default is None:
                        param_str += " = None"
                    elif isinstance(param.default, str):
                        param_str += f" = '{param.default}'"
                    else:
                        param_str += f" = {param.default}"
                params.append(param_str)
            
            param_string = ", ".join(params)
            # Simplify return type - just use 'str' if it's a string annotation
            return_type = sig.return_annotation
            if return_type != inspect.Parameter.empty:
                if hasattr(return_type, '__name__'):
                    return_annotation = f" -> {return_type.__name__}"
                else:
                    return_annotation = f" -> str"  # Default to str
            else:
                return_annotation = ""
            
            # Get the actual docstring from the function - it should have proper parameter descriptions
            docstring = func.__doc__ or f"Wrapper for {tool_name} from drive_analytics_tools module."
            # Clean up the docstring - remove leading/trailing whitespace but preserve structure
            docstring = docstring.strip()
            
            # Extract just parameter names for the function call
            param_names = [p.split(':')[0].split('=')[0].strip() for p in params]
            func_call_params = ', '.join(param_names)
            
            tool_source = f'''import os
import sys
import json
import time
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Import the function from our module (container path)
sys.path.insert(0, "{container_module_path}")
import drive_analytics_tools

# Re-export the function with proper signature so Letta can see the parameters
def {tool_name}({param_string}){return_annotation}:
    r"""{docstring}"""
    func = getattr(drive_analytics_tools, "{tool_name}")
    return func({func_call_params})
'''
            
            result = create_tool(tool_source, tags=tool_def["tags"])
            if result:
                tool_id = result.get('id')
                print(f"  ✓ Created tool (ID: {tool_id})")
                registered_tool_ids.append(tool_id)
            else:
                print("  ✗ Failed to create tool")
    
    # Attach to agent
    print()
    print(f"→ Attaching tools to agent {AGENT_ID}...")
    
    if not registered_tool_ids:
        print("  ✗ No tools to attach")
        return 1
    
    if attach_tools_to_agent(AGENT_ID, registered_tool_ids):
        print(f"  ✓ Attached {len(registered_tool_ids)} tools to agent")
    else:
        print("  ✗ Failed to attach tools")
        return 1
    
    print()
    print("="*60)
    print("✓ Registration Complete")
    print("="*60)
    print()
    print("Your agent now has these Drive analytics tools:")
    print("  Setup:")
    print("    • initialize_drive_analytics_memory - Initialize memory blocks")
    print("  Data Collection:")
    print("    • collect_daily_workspace_activity")
    print("    • collect_daily_personal_activity")
    print("    • collect_daily_mentions")
    print("    • calculate_running_averages")
    print("  Query Tools:")
    print("    • get_drive_analytics_summary")
    print("    • get_drive_trends")
    print("    • get_my_drive_activity")
    print("    • get_drive_mentions")
    print("    • get_document_activity")
    print("    • get_top_documents")
    print("    • get_recent_my_activity")
    print("    • get_drive_file_info - Get document metadata from Drive URL")
    print()
    print("Try asking your agent:")
    print('  "Collect yesterday\'s Drive activity"')
    print('  "Show me the top edited documents"')
    print('  "Get documents I\'ve been viewing recently"')
    print('  "Get info about this document: https://docs.google.com/document/d/..."')
    print()
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
