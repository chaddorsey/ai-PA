# Coding Custom Letta Tools

This guide documents the conventions and requirements for creating custom tools that work with Letta's tool registration system. These requirements were discovered through implementation and are critical for successful tool registration.

## Overview

When Letta registers a custom tool using `create_from_function`, it extracts the function body and analyzes it for schema generation. This process has specific requirements that must be followed for the tool to register successfully.

## Critical Requirements

### 1. All Imports Must Be Inside the Main Function - AT THE VERY BEGINNING

**Problem**: When Letta extracts the function, module-level imports are not included, causing `NameError` at runtime. Additionally, if imports come after other code (like default value assignments), they won't be executed before that code runs.

**Solution**: Move all imports inside the main function body, at the **very beginning**, immediately after the docstring and before ANY other code (including default value assignments).

```python
def my_custom_tool(param1: str, param2: Optional[int] = None) -> Dict[str, Any]:
    """
    Tool description here.
    """
    # ⚠️ CRITICAL: Imports MUST be first, before any other code
    # Import required modules inside function for Letta tool extraction
    import os
    import sys
    import asyncio
    from typing import Dict, Any, Optional, List
    from datetime import datetime, timedelta
    import pytz
    import logging
    
    # Initialize logger
    logger = logging.getLogger(__name__)
    
    # Add parent directory to path for imports if needed
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Import from other modules
    try:
        from some_module import SomeClass, SomeError
    except ImportError:
        SomeClass = None
        SomeError = None
    
    # NOW you can set defaults and do other work
    if param2 is None:
        param2 = 0
    
    # Rest of function implementation...
```

**Common Mistake**: Putting imports after default value assignments or other code. This will cause `NameError` because the imports haven't executed yet when that code runs.

### 2. AVOID Nested Function Definitions (def statements)

**Problem**: When Letta extracts the function, it may also extract nested `def` statements as separate tools, leading to unexpected behavior. Nested functions with missing docstrings or type annotations cause schema generation errors.

**Solution**: **DO NOT use `def` statements inside the main function.** Instead:
1. Inline all helper logic directly
2. Use lambdas only for simple sorting/filtering callbacks
3. Store computed values in dictionaries/lists for reuse

```python
def my_custom_tool(param1: str, param2: Optional[int] = None) -> Dict[str, Any]:
    """
    Tool description here.
    """
    # Imports here...
    import pytz
    from datetime import datetime
    
    # ❌ DO NOT DO THIS - Letta may extract nested functions as separate tools:
    # def helper_function(data):
    #     return data.upper()
    
    # ✅ INSTEAD - Inline the logic or use lambdas for simple operations:
    
    # For complex reused logic, compute once and store in a dict/list
    processed_items = {}
    for item in items:
        # Inline the processing logic
        processed = item.get("value", "").upper()
        processed_items[item["id"]] = processed
    
    # For simple sorting, lambdas are OK (but no def statements)
    items.sort(key=lambda x: x.get("date", ""))
    
    return {"status": "ok", "result": processed_items}
```

**Exception**: `async def` for asyncio operations may be needed but should be kept minimal:

```python
    # This pattern is acceptable for async operations
    async def _async_fetch():
        await client.initialize()
        return await client.get_data()
    result = asyncio.run(_async_fetch())
```

### 3. If You MUST Use Nested Functions (Not Recommended)

If you absolutely must use nested `def` statements (e.g., for complex async operations), they require:
- Type annotations on all parameters
- Docstrings with `Args:` sections
- Only basic JSON types (`str`, `int`, `bool`, `float`, `None`)

**However, it's strongly recommended to avoid nested functions entirely** - see section 2.

### 6. Main Function Requirements

The main function itself has more flexible requirements:

- **Type Annotations**: Can use complex types like `Dict[str, Any]`, `Optional[...]`, etc.
- **Docstring**: Should have comprehensive docstring with `Args:` and `Returns:` sections
- **Return Type**: Should be `Dict[str, Any]` or similar structured return type

```python
def my_custom_tool(
    param1: str,
    param2: Optional[int] = None,
    param3: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Comprehensive tool description.
    
    This tool does X, Y, and Z.
    
    Args:
        param1: Description of param1
        param2: Description of param2 (optional)
        param3: Description of param3 (optional, JSON string)
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - result: The result data
        - error_message: Error message if status is "error"
    """
    # Imports and implementation...
```

## Complete Example

Here's a complete example following all conventions (NO nested `def` statements):

```python
"""
Custom Tool Example

This module demonstrates a custom Letta tool following all required conventions.
"""

from typing import Dict, Any, Optional


def generate_report(
    report_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a formatted report.
    
    This tool generates reports based on the specified type and date range.
    
    Args:
        report_type: Type of report to generate (e.g., "daily", "weekly"). Defaults to "daily".
        start_date: Start date in ISO format (optional, defaults to today)
        end_date: End date in ISO format (optional, defaults to today)
    
    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - report: Formatted report content
        - timestamp: ISO timestamp of when report was generated
        - error_message: Error message if status is "error"
    """
    # Import required modules inside function for Letta tool extraction
    import traceback
    import os
    import sys
    from datetime import datetime, timedelta
    import pytz
    
    # Wrap entire function in try-except
    try:
        # Set defaults
        if report_type is None:
            report_type = "daily"
        
        tz = pytz.timezone("America/New_York")
        now = datetime.now(tz)
        
        if start_date is None:
            start_date = now.isoformat()
        if end_date is None:
            end_date = now.isoformat()
        
        # Parse dates (inline, no helper function)
        try:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if start_dt.tzinfo is None:
                start_dt = pytz.UTC.localize(start_dt)
            start_dt = start_dt.astimezone(tz)
        except:
            start_dt = now
        
        try:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                end_dt = pytz.UTC.localize(end_dt)
            end_dt = end_dt.astimezone(tz)
        except:
            end_dt = now
        
        # Calculate date range (inline)
        days = (end_dt - start_dt).days
        date_range = f"{days} days"
        
        # Format report (inline)
        report_data = f"Report for {date_range}"
        if report_type == "daily":
            formatted_report = f"# Daily Report\n\n{report_data}"
        elif report_type == "weekly":
            formatted_report = f"# Weekly Report\n\n{report_data}"
        else:
            formatted_report = f"# Report\n\n{report_data}"
        
        return {
            "status": "ok",
            "report": formatted_report,
            "timestamp": now.isoformat()
        }
    
    except Exception as e:
        # Safe error handling
        try:
            error_timestamp = datetime.now(pytz.timezone("America/New_York")).isoformat()
        except:
            from datetime import datetime as dt
            error_timestamp = dt.now().isoformat()
        return {
            "status": "error",
            "report": "",
            "timestamp": error_timestamp,
            "error_message": f"Error: {str(e)}\n{traceback.format_exc()}"
        }
```

## Common Pitfalls

1. **Module-level imports**: Will cause `NameError` at runtime
2. **Nested `def` statements**: Letta extracts these as separate tools - **AVOID**
3. **Module-level helper functions**: Will cause `NameError` at runtime
4. **Missing try-except wrapper**: Errors may not be handled gracefully
5. **Using complex types (datetime, custom classes)**: Stick to basic JSON types in signatures

## Registration

Once your tool follows these conventions, register it with Letta:

```python
from letta_client import Letta
from my_module import generate_report

client = Letta(base_url="http://localhost:8283")
created_tool = client.tools.create_from_function(
    func=generate_report,
    tags=["reporting", "custom"]
)
```

## Code Order Within Main Function

The order of code inside the main function is critical:

1. **Imports** (first, immediately after docstring)
2. **try-except wrapper** (wrap all logic)
3. **Default value assignments** (inside try block)
4. **Path setup** (if needed)
5. **Module imports** (from other packages, with fallbacks)
6. **Main logic** (inline all helper logic, no nested `def` statements)
7. **Error handling** (safe fallbacks in except block)

```python
from typing import Dict, Any, Optional


def my_tool(param: Optional[str] = None) -> Dict[str, Any]:
    """Tool description."""
    # 1. IMPORTS FIRST
    import traceback
    import os
    import sys
    from datetime import datetime
    import pytz
    
    # 2. TRY-EXCEPT WRAPPER
    try:
        # 3. DEFAULTS
        if param is None:
            param = "default"
        
        # 4. PATH SETUP
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # 5. MODULE IMPORTS
        try:
            from some_module import SomeClass
        except ImportError:
            SomeClass = None
        
        # 6. MAIN LOGIC (inline everything, NO nested def statements)
        result = param.upper()  # Inline helper logic
        
        return {"status": "ok", "result": result}
    
    except Exception as e:
        # 7. SAFE ERROR HANDLING
        try:
            error_timestamp = datetime.now(pytz.timezone("America/New_York")).isoformat()
        except:
            error_timestamp = datetime.now().isoformat()
        return {
            "status": "error",
            "error_message": f"Error: {str(e)}\n{traceback.format_exc()}"
        }
```

## Summary Checklist

When creating a custom Letta tool, ensure:

- [ ] All imports are inside the main function **at the very beginning** (before any other code)
- [ ] **NO nested `def` statements** - inline all helper logic
- [ ] Module-level imports only for type hints (`from typing import Dict, Any, Optional`)
- [ ] Entire function body wrapped in try-except
- [ ] Main function has comprehensive docstring with `Args:` and `Returns:` sections
- [ ] Safe error handling with fallbacks if imports fail
- [ ] Return value is a `Dict[str, Any]` with consistent structure
- [ ] Code follows the correct order: imports → try-except → defaults → logic → error handling

Following these conventions will ensure your tool registers successfully on the first attempt.

## Key Discovery

**Letta extracts ALL `def` statements** from within your function and attempts to register them as separate tools. This means:
- Nested helper functions become separate tools
- Each extracted function needs its own docstring and type annotations
- This is usually NOT what you want

**The solution is to avoid `def` statements entirely** and inline all logic directly in the main function body.

