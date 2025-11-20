# Registering MCP Tools as Strict in Letta

## Overview

"Strict" mode in Letta enforces strict schema validation for tool inputs, ensuring that:
- All required fields are present
- No additional properties are allowed (unless explicitly permitted)
- Field types match exactly
- Values conform to constraints

This improves reliability by catching errors early and preventing malformed tool calls.

## Method 1: Strict Schema in MCP Tool Definition (Recommended)

The most reliable way to enable strict mode is to define strict JSON schemas in your MCP server's tool definitions. Letta will automatically enforce these schemas.

### In Your MCP Server Tool Definition

When defining your tool in the MCP server, ensure your `inputSchema` has strict validation:

```typescript
// Example: Calendar tool with strict schema
{
  name: "Get_Events",
  description: "Get calendar events for a user",
  inputSchema: {
    type: "object",
    properties: {
      timeMin: {
        type: "string",
        format: "date-time",
        description: "Start time for event query (ISO 8601)"
      },
      timeMax: {
        type: "string",
        format: "date-time",
        description: "End time for event query (ISO 8601)"
      },
      userId: {
        type: "string",
        description: "User ID or email"
      }
    },
    required: ["timeMin", "timeMax", "userId"],
    additionalProperties: false  // ← This enforces strict mode
  }
}
```

**Key points:**
- Set `additionalProperties: false` to prevent extra fields
- Define all `required` fields explicitly
- Use specific `type` constraints (not `any`)
- Add `format` constraints where applicable (e.g., `date-time`)

### Example: Minimal Calendar Event Tool

```typescript
{
  name: "Get_Events_Minimal",
  description: "Get minimal calendar events (optimized format)",
  inputSchema: {
    type: "object",
    properties: {
      participantId: {
        type: "string",
        minLength: 1,
        description: "Participant ID"
      },
      timeMin: {
        type: "string",
        pattern: "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$",
        description: "Start time (ISO 8601 UTC)"
      },
      timeMax: {
        type: "string",
        pattern: "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$",
        description: "End time (ISO 8601 UTC)"
      },
      excludeAllDay: {
        type: "boolean",
        default: true,
        description: "Exclude all-day events"
      }
    },
    required: ["participantId", "timeMin", "timeMax"],
    additionalProperties: false
  }
}
```

## Method 2: Letta Tool Registration with Strict Validation

If you're registering tools programmatically via Letta's API, you can specify validation options:

### Using Letta Python Client

```python
from letta_client import Letta

client = Letta(base_url="http://localhost:8283")

# Register tool with strict validation
tool = client.tools.create_from_function(
    func=your_function,
    name="your_tool_name",
    tags=["calendar", "strict"],
    # Strict validation is enforced via function signature and Pydantic models
)
```

**Note:** For Python functions, strict validation comes from:
- Pydantic models with `additionalProperties: false` in JSON schema
- Type hints in function signatures
- Required vs optional parameters

### Using Letta API Directly

```bash
# Register MCP tool with strict validation
curl -X POST http://localhost:8283/v1/tools \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Get_Events",
    "type": "mcp",
    "mcp_server": "calendar-tools",
    "validation": {
      "strict": true,
      "reject_additional_properties": true,
      "require_all_fields": true
    }
  }'
```

## Method 3: MCP Server Configuration

You can also configure strict mode at the MCP server level in `letta_mcp_config.json`:

```json
{
  "mcpServers": {
    "calendar-tools": {
      "command": "http",
      "args": ["http://n8n:5678/mcp/80b10600-d5be-4552-b00c-5c9790bded31"],
      "env": {
        "MCP_SERVER_NAME": "calendar-tools",
        "MCP_TRANSPORT": "streamable-http",
        "STRICT_VALIDATION": "true"
      },
      "validation": {
        "strict": true,
        "reject_additional_properties": true
      },
      "disabled": false
    }
  }
}
```

**Note:** This format may vary depending on Letta version. Check Letta's documentation for the exact schema.

## Method 4: Tool-Level Configuration via Letta ADE

If using Letta's Agent Development Environment (ADE):

1. Navigate to **Tool Manager** → **MCP Tools**
2. Select your MCP server
3. Find the tool you want to configure
4. Click **Edit** or **Configure**
5. Enable **Strict Validation** option
6. Set **Reject Additional Properties** to `true`
7. Save configuration

## Verification

### Test Strict Validation

```bash
# Test with valid input (should succeed)
curl -X POST http://localhost:8283/v1/tools/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "server": "calendar-tools",
    "tool": "Get_Events",
    "arguments": {
      "participantId": "user123",
      "timeMin": "2025-01-01T00:00:00Z",
      "timeMax": "2025-01-15T00:00:00Z"
    }
  }'

# Test with invalid input (should fail with strict mode)
curl -X POST http://localhost:8283/v1/tools/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "server": "calendar-tools",
    "tool": "Get_Events",
    "arguments": {
      "participantId": "user123",
      "timeMin": "2025-01-01T00:00:00Z",
      "timeMax": "2025-01-15T00:00:00Z",
      "extraField": "should be rejected"  # ← Should fail in strict mode
    }
  }'
```

## Best Practices

1. **Always use `additionalProperties: false`** in your tool schemas
2. **Define all required fields explicitly** in the `required` array
3. **Use specific types** (avoid `any` or `object` without constraints)
4. **Add format constraints** where applicable (e.g., `date-time`, `email`)
5. **Test strict validation** before deploying to production

## Troubleshooting

### Tool calls failing with "additional properties not allowed"

- **Cause**: Strict mode is enabled and tool call includes extra fields
- **Solution**: Remove extra fields from tool calls, or update schema to allow them

### Required fields missing errors

- **Cause**: Strict mode requires all fields in `required` array
- **Solution**: Ensure all required fields are provided in tool calls

### Type validation errors

- **Cause**: Field types don't match schema (e.g., string vs number)
- **Solution**: Ensure tool calls match exact types defined in schema

## References

- [Letta Tool Documentation](https://docs.letta.com/guides/tools/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [JSON Schema Validation](https://json-schema.org/understanding-json-schema/)

