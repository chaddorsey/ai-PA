# Slack Tools: Letta Compliance Guide

This document ensures all Slack custom tools follow Letta's tool registration requirements as documented in `context/coding_custom_letta_tools.md`.

## Return Type: Dict[str, Any]

**CRITICAL**: All tools must return `Dict[str, Any]`, NOT JSON strings.

### Standard Return Structure

```python
{
    "status": "ok" | "error",
    "data": {
        # Actual result data
    },
    "metadata": {
        # Optional metadata
    },
    "error_message": "..."  # Only if status == "error"
}
```

### Error Response Structure

```python
{
    "status": "error",
    "error_message": "Human-readable error message",
    "traceback": "Full traceback (optional, for debugging)"
}
```

## Function Structure Template

```python
from typing import Dict, Any, Optional

def tool_name(
    param1: Optional[str] = None,
    param2: Optional[int] = None
) -> Dict[str, Any]:
    """
    Tool description.
    
    Args:
        param1: Description of param1
        param2: Description of param2 (optional)
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - data: Result data (structure depends on tool)
        - error_message: Error message if status is "error"
    """
    # 1. IMPORTS FIRST (inside function, at very beginning)
    import os
    import traceback
    import json
    import urllib.request
    import urllib.parse
    from datetime import datetime
    
    # 2. TRY-EXCEPT WRAPPER
    try:
        # 3. DEFAULTS (inline)
        if param1 is None:
            param1 = "default"
        
        # 4. MAIN LOGIC (inline everything, NO nested def statements)
        # All helper logic must be inlined here
        
        return {
            "status": "ok",
            "data": {
                # Result data
            }
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "traceback": traceback.format_exc()
        }
```

## Critical Rules

### ✅ DO

1. **Return Dict[str, Any]**: All tools return dictionaries, not JSON strings
2. **Imports inside function**: All imports at the very beginning of the function
3. **Wrap in try-except**: All logic wrapped in try-except
4. **Inline all logic**: No nested `def` statements
5. **Comprehensive docstrings**: Include Args: and Returns: sections
6. **Type hints**: Use `Optional[...]` for optional parameters, `Dict[str, Any]` for return type
7. **Consistent error format**: Always return `{"status": "error", "error_message": "..."}`

### ❌ DON'T

1. **NO nested def statements**: Letta extracts these as separate tools
2. **NO module-level imports** (except `from typing import ...`)
3. **NO JSON string returns**: Always return Dict[str, Any]
4. **NO helper functions**: Inline all logic
5. **NO complex types in signatures**: Use basic JSON types (str, int, bool, Optional[...])

## Updating Tool Specifications

All tool specifications in `SLACK_TOOLS_SPECIFICATION.md` must be updated to:

1. Return `Dict[str, Any]` instead of JSON strings
2. Include proper error response structure
3. Document the standard return format with `status` and `data` keys
4. Follow the function structure template above

## Code Review Checklist

Before implementing each tool, verify:

- [ ] Function signature uses `Dict[str, Any]` return type
- [ ] Module-level imports only: `from typing import Dict, Any, Optional`
- [ ] All other imports inside function at the very beginning
- [ ] Entire function wrapped in try-except
- [ ] No nested `def` statements
- [ ] Docstring includes Args: and Returns: sections
- [ ] Return format follows standard structure (status, data, error_message)
- [ ] Error handling returns proper error structure
- [ ] All helper logic is inlined

## Example: Converting Existing Tool

### Before (String Return - Wrong for Letta)

```python
def get_slack_messages(channel: str) -> str:
    """Get messages from channel."""
    import json
    # ... logic ...
    return json.dumps({"messages": [...]})
```

### After (Dict Return - Correct for Letta)

```python
from typing import Dict, Any

def get_slack_messages(channel: str) -> Dict[str, Any]:
    """
    Get messages from a Slack channel.
    
    Args:
        channel: Channel ID or name
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - data: Dictionary with "messages" array
        - error_message: Error message if status is "error"
    """
    import os
    import traceback
    import json
    import urllib.request
    import urllib.parse
    
    try:
        # ... inline logic ...
        return {
            "status": "ok",
            "data": {
                "messages": [...]
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
            "traceback": traceback.format_exc()
        }
```
