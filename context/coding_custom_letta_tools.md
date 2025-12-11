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

### 2. Helper Functions Must Be Nested Inside the Main Function

**Problem**: Module-level helper functions are not included when Letta extracts the function, causing `NameError` at runtime.

**Solution**: Define all helper functions inside the main function, before they are used.

```python
def my_custom_tool(param1: str, param2: Optional[int] = None) -> Dict[str, Any]:
    """
    Tool description here.
    """
    # Imports here...
    
    # Define helper functions inside main function so they're included when Letta extracts the function
    
    def helper_function_1(arg1: str, arg2: str) -> str:
        """Helper function description.
        
        Args:
            arg1: Description of arg1
            arg2: Description of arg2
        """
        # Implementation...
        return result
    
    def helper_function_2(data: str) -> int:
        """Helper function description.
        
        Args:
            data: Description of data
        """
        # Implementation...
        return result
    
    # Main function logic that uses helpers...
    result = helper_function_1(param1, "value")
    return {"status": "ok", "result": result}
```

### 3. Type Annotations Are Required for Nested Functions

**Problem**: Letta's schema generator requires type annotations for all function parameters, including nested helper functions.

**Solution**: Add type annotations to all nested function parameters and return types.

```python
def my_custom_tool(param1: str) -> Dict[str, Any]:
    """Tool description."""
    # Imports...
    
    def helper(data: str, count: int) -> str:  # ✅ Type annotations required
        """Helper description.
        
        Args:
            data: Description
            count: Description
        """
        return f"{data} {count}"
    
    # ❌ This will fail:
    # def helper(data, count):  # Missing type annotations
    #     return f"{data} {count}"
```

### 4. Only Basic JSON Types Supported for Nested Functions

**Problem**: Letta's schema generator only supports basic JSON-serializable types: `str`, `int`, `bool`, `float`, `None`, and simple `List`/`Dict` with these types. Complex types like `datetime`, `pytz.BaseTzInfo`, or custom classes cause schema generation errors.

**Solution**: Use basic JSON types for nested function type annotations, even if they're not semantically correct. Python doesn't enforce types at runtime, so the code will work correctly.

```python
def my_custom_tool(param1: str) -> Dict[str, Any]:
    """Tool description."""
    # Imports...
    from datetime import datetime
    import pytz
    
    # ✅ Use basic JSON types for nested functions
    def parse_datetime(dt_str: str, tz_obj: str) -> str:
        """Parse datetime string.
        
        Args:
            dt_str: Datetime string
            tz_obj: Timezone object (annotated as str for Letta)
        """
        # Implementation can still use actual datetime/pytz objects
        tz = pytz.timezone(tz_obj)  # Works at runtime
        dt = datetime.fromisoformat(dt_str)
        return dt.astimezone(tz)
    
    # ❌ This will fail schema generation:
    # def parse_datetime(dt_str: str, tz_obj: pytz.BaseTzInfo) -> datetime:
    #     # pytz.BaseTzInfo and datetime are not JSON-serializable types
```

**Supported Types for Nested Functions**:
- `str`
- `int`
- `bool`
- `float`
- `None` (or `Optional[...]`)
- `List[str]`, `List[int]`, etc. (with basic types)
- `Dict[str, str]`, `Dict[str, int]`, etc. (with basic types)

**Not Supported**:
- `datetime`
- `pytz.BaseTzInfo`
- Custom classes
- `Any` (causes schema generation errors)
- `object` (causes schema generation errors)
- Complex generic types like `Dict[str, Any]` in nested functions

### 5. Docstrings with Args Sections Required for Nested Functions

**Problem**: Letta's schema generator requires docstrings with `Args:` sections for all nested functions, describing each parameter.

**Solution**: Add docstrings with `Args:` sections to all nested functions.

```python
def my_custom_tool(param1: str) -> Dict[str, Any]:
    """Tool description."""
    # Imports...
    
    def helper_function(data: str, count: int) -> str:
        """Helper function description.
        
        Args:
            data: Description of what data represents
            count: Description of what count represents
        """
        return f"{data} {count}"
    
    # ❌ This will fail:
    # def helper_function(data: str, count: int) -> str:
    #     """Helper function description."""  # Missing Args section
    #     return f"{data} {count}"
```

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

Here's a complete example following all conventions:

```python
"""
Custom Tool Example

This module demonstrates a custom Letta tool following all required conventions.
"""

def generate_report(
    report_type: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a formatted report.
    
    This tool generates reports based on the specified type and date range.
    
    Args:
        report_type: Type of report to generate (e.g., "daily", "weekly")
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
    import os
    import sys
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
    
    # Define helper functions inside main function so they're included when Letta extracts the function
    
    def parse_date(date_str: str) -> str:
        """Parse date string.
        
        Args:
            date_str: Date string in ISO format
        """
        # Implementation uses actual datetime but type annotation is str
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.isoformat()
        except ValueError:
            return date_str
    
    def format_report_content(data: str, report_type: str) -> str:
        """Format report content.
        
        Args:
            data: Report data as string
            report_type: Type of report
        """
        if report_type == "daily":
            return f"# Daily Report\n\n{data}"
        elif report_type == "weekly":
            return f"# Weekly Report\n\n{data}"
        else:
            return f"# Report\n\n{data}"
    
    def calculate_date_range(start: str, end: str) -> str:
        """Calculate date range.
        
        Args:
            start: Start date string
            end: End date string
        """
        # Implementation can use actual datetime objects
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        days = (end_dt - start_dt).days
        return f"{days} days"
    
    # Main function logic
    try:
        # Set defaults
        if start_date is None:
            tz = pytz.timezone("America/New_York")
            start_date = datetime.now(tz).isoformat()
        
        if end_date is None:
            tz = pytz.timezone("America/New_York")
            end_date = datetime.now(tz).isoformat()
        
        # Use helper functions
        parsed_start = parse_date(start_date)
        parsed_end = parse_date(end_date)
        date_range = calculate_date_range(parsed_start, parsed_end)
        
        # Generate report
        report_data = f"Report for {date_range}"
        formatted_report = format_report_content(report_data, report_type)
        
        return {
            "status": "ok",
            "report": formatted_report,
            "timestamp": datetime.now(pytz.timezone("America/New_York")).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        return {
            "status": "error",
            "report": "",
            "timestamp": datetime.now(pytz.timezone("America/New_York")).isoformat(),
            "error_message": str(e)
        }
```

## Common Pitfalls

1. **Module-level imports**: Will cause `NameError` at runtime
2. **Module-level helper functions**: Will cause `NameError` at runtime
3. **Missing type annotations on nested functions**: Will fail schema generation
4. **Complex types in nested functions**: Will fail schema generation (use `str` instead)
5. **Missing docstrings on nested functions**: Will fail schema generation
6. **Missing Args sections in docstrings**: Will fail schema generation

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
2. **Logger initialization**
3. **Path setup** (if needed)
4. **Module imports** (from other packages)
5. **Helper function definitions** (all nested functions)
6. **Default value assignments**
7. **Main logic** (try/except blocks, business logic)

```python
def my_tool(param: str) -> Dict[str, Any]:
    """Tool description."""
    # 1. IMPORTS FIRST
    import os
    import sys
    # ... all imports
    
    # 2. LOGGER
    logger = logging.getLogger(__name__)
    
    # 3. PATH SETUP
    sys.path.insert(0, ...)
    
    # 4. MODULE IMPORTS
    try:
        from module import Class
    except ImportError:
        Class = None
    
    # 5. HELPER FUNCTIONS
    def helper(...):
        """Helper."""
        ...
    
    # 6. DEFAULTS
    if param is None:
        param = "default"
    
    # 7. MAIN LOGIC
    try:
        result = helper(param)
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "error", "error_message": str(e)}
```

## Summary Checklist

When creating a custom Letta tool, ensure:

- [ ] All imports are inside the main function **at the very beginning** (before any other code)
- [ ] All helper functions are nested inside the main function
- [ ] All nested functions have type annotations
- [ ] Nested function types use only basic JSON types (`str`, `int`, `bool`, `float`, `None`, simple `List`/`Dict`)
- [ ] All nested functions have docstrings with `Args:` sections
- [ ] Main function has comprehensive docstring with `Args:` and `Returns:` sections
- [ ] Error handling is in place with proper logging
- [ ] Return value is a `Dict[str, Any]` with consistent structure
- [ ] Code follows the correct order: imports → helpers → defaults → logic

Following these conventions will ensure your tool registers successfully on the first attempt.

