# Calendly MCP Server

MCP (Model Context Protocol) server that provides Calendly availability checking and booking tools for Letta agents.

## Overview

This service wraps the verified `calendly_slots.py` implementation in an MCP-compliant HTTP server, allowing Letta agents to query Calendly availability data through a standardized interface.

## Architecture

```
┌─────────────────┐
│  Letta Agent    │
│  (Container)    │
└────────┬────────┘
         │ MCP Protocol (HTTP)
         ▼
┌─────────────────────┐
│ Calendly MCP Server │
│  - FastAPI wrapper  │
│  - MCP protocol     │
│  - Playwright       │
│  - Python runtime   │
└─────────────────────┘
         │
         ▼
   Calendly.com APIs
```

## Features

- **Availability Checking**: Query available time slots for Calendly events
  - Profile URL Support: Query all events for a Calendly user profile
  - Event URL Support: Query specific event availability
  - Date Range Queries: Flexible date range specification
  - Timezone Handling: Proper timezone conversion (default: America/New_York)
  - Time Slot Details: Returns available dates and specific time slots
  
- **Pre-filled Booking Links**: Generate booking URLs with auto-filled form data
  - Avoids CAPTCHA issues (user completes booking in their browser)
  - Pre-fills name, email, custom fields, and time slot
  - Returns clickable link + instructions for completion
  - No browser automation required
  
- **Health Checks**: Built-in health monitoring endpoint

## Core Function

The server exposes the `slots_for_profile_or_event()` function which:
- Accepts either profile URLs (`https://calendly.com/username`) or event URLs (`https://calendly.com/username/event-slug`)
- Returns structured JSON with available days and time slots
- Handles event discovery, UUID sniffing, and API querying automatically

**Exposed Tool Parameters:**
- `url` (required): Calendly URL (profile or event)
- `timezone` (optional): IANA timezone (default: "America/New_York")
- `start` (optional): Start date YYYY-MM-DD (default: today)
- `end` (optional): End date YYYY-MM-DD (default: start+21 days)

**Internal optimizations handled automatically:**
- XHR sniffing wait time: 6 seconds (with auto-retry up to 12s if needed)
- Rate limiting delay: 0.35s between requests
- Retry logic: Up to 3 attempts with increasing wait times

**Returns:**
```json
{
  "events": [
    {
      "title": "30 Minute Meeting",
      "url": "https://calendly.com/user/30min",
      "uuid": "abc123...",
      "scheduling_link_uuid": "xyz789...",
      "date_range": {"start": "2025-10-15", "end": "2025-11-15"},
      "days": ["2025-10-15", "2025-10-16", ...],
      "times": {
        "2025-10-15": ["09:00", "10:00", "14:30"],
        "2025-10-16": ["11:00", "15:00"]
      },
      "range_errors": []
    }
  ]
}
```

## Installation

### Prerequisites
- Python 3.11+
- Docker (for containerized deployment)

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run development server
uvicorn src.main:app --reload --port 8086
```

### Docker Deployment

```bash
# Build image
docker build -t calendly-mcp-server .

# Run container
docker run -p 8086:8086 calendly-mcp-server
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_SERVER_NAME` | Server identifier | `calendly-tools` |
| `MCP_SERVER_VERSION` | Server version | `1.0.0` |
| `MCP_SERVER_HOST` | Bind address | `0.0.0.0` |
| `MCP_SERVER_PORT` | Port number | `8086` |
| `CALENDLY_DEFAULT_TIMEZONE` | Default timezone for queries | `America/New_York` |
| `CALENDLY_REQUEST_TIMEOUT` | API request timeout (seconds) | `30` |

## API Endpoints

### Health Check
```
GET /health
```

Returns server health status.

**Response:**
```json
{
  "status": "healthy",
  "service": "calendly-tools",
  "version": "1.0.0"
}
```

### MCP Protocol Endpoint
```
POST /mcp
```

MCP protocol endpoint for tool discovery and invocation.

## Available Tools

### Tool 1: `calendly_slots` - Check Availability

Query Calendly availability for a profile or specific event.

**Parameters:**
- `url` (string, required): Calendly profile or event URL
- `timezone` (string, optional): IANA timezone (default: "America/New_York")
- `start` (string, optional): Start date YYYY-MM-DD (default: today)
- `end` (string, optional): End date YYYY-MM-DD (default: start + 21 days)

**Example Usage:**
```json
{
  "tool": "calendly_slots",
  "arguments": {
    "url": "https://calendly.com/zarek-drozda",
    "timezone": "America/New_York",
    "start": "2025-10-15",
    "end": "2025-11-15"
  }
}
```

### Tool 2: `calendly_create_booking_link` - Generate Pre-filled Booking Link

Generate a Calendly booking URL with all form data pre-filled (name, email, custom fields, time slot).

**Why Use This?**
- ✅ Avoids CAPTCHA/bot detection (user completes booking in their browser)
- ✅ Saves user time (form is pre-filled)
- ✅ Works reliably across all Calendly accounts
- ✅ User can review before confirming

**Parameters:**
- `url` (string, required): Calendly event URL
- `date` (string, required): Date in YYYY-MM-DD format
- `time` (string, required): Time in HH:MM (24h) or h:mma format (e.g., "14:30" or "2:30pm")
- `name` (string, required): Invitee full name
- `email` (string, required): Invitee email address
- `timezone` (string, optional): IANA timezone (default: "America/New_York")
- `custom_fields` (object, optional): Custom field responses (e.g., {"title the meeting": "Q4 Planning"})
- `guests` (array, optional): Guest email addresses (must be added manually by user)

**Example Usage:**
```json
{
  "tool": "calendly_create_booking_link",
  "arguments": {
    "url": "https://calendly.com/zarek-drozda/30min",
    "date": "2025-10-29",
    "time": "12:30pm",
    "name": "Chad Dorsey",
    "email": "cdorsey@concord.org",
    "timezone": "America/New_York",
    "custom_fields": {
      "title the meeting": "Chad - Kate - Zarek check-in"
    },
    "guests": ["kmiller@concord.org"]
  }
}
```

**Example Response:**
```json
{
  "success": true,
  "booking_url": "https://calendly.com/zarek-drozda/30min/2025-10-29T12:30:00-04:00?name=Chad+Dorsey&email=cdorsey@concord.org&question_0=Chad+-+Kate+-+Zarek+check-in",
  "instructions": [
    "1. Click the booking_url link",
    "2. Verify the pre-filled information is correct",
    "3. Add guests manually: kmiller@concord.org",
    "4. Click 'Schedule Event' button",
    "5. Complete CAPTCHA if prompted"
  ]
}
```

**Recommended Workflow:**
1. Use `calendly_slots` to find available times
2. Use `calendly_create_booking_link` to generate a pre-filled link
3. Present the link to the user
4. User clicks link and completes booking

## Integration with Letta

Add to `letta_mcp_config.json`:
```json
{
  "mcpServers": {
    "calendly-tools": {
      "command": "http",
      "args": ["http://calendly-mcp-server:8086/mcp"],
      "env": {
        "MCP_SERVER_NAME": "calendly-tools",
        "MCP_SERVER_VERSION": "1.0.0",
        "MCP_TRANSPORT": "streamable-http"
      },
      "disabled": false
    }
  }
}
```

## Technical Notes

### Playwright/Chromium
- The server uses Playwright to sniff event UUIDs from XHR network traffic
- Chromium browser runs in headless mode
- Each request spawns a browser instance (cleaned up after completion)
- Memory usage: ~150-200MB per concurrent request

### Rate Limiting & Retry Logic
- Built-in delay between per-day API calls (0.35s)
- Respects Calendly's undocumented API usage patterns
- Automatic retry on UUID discovery failure (up to 3 attempts)
- Sniff wait time increases from 6s → 9s → 12s on retries
- Recommended: no more than 2-3 concurrent requests

### Error Handling

The tool provides expressive error messages to help diagnose issues:

**Parameter Validation Errors:**
- Missing URL: Explains required format and examples
- Invalid URL type: Shows received type vs expected string
- Non-HTTP URL: Reminds about https:// requirement
- Non-Calendly URL: Validates calendly.com domain
- Invalid timezone: Shows received value and examples
- Invalid date format: Shows received format vs expected YYYY-MM-DD
- Invalid date range: Explains end must be after start

**Runtime Errors:**
- Timeout errors: Suggests Calendly may be slow/unavailable
- Connection errors: Recommends checking network
- 404 errors: Suggests verifying URL accessibility
- UUID not found: Provides detailed troubleshooting (see below)

**UUID Discovery Failures:**

When the tool cannot discover an event UUID (after 3 attempts with 6s, 9s, 12s wait times), it returns:
```
Could not discover event UUID after 3 attempts (wait times: 6.0s → 12.0s). 
This typically means:
  1) The event has no availability in the near future
  2) The event URL may be private, expired, or invalid
  3) The page may require authentication

Suggestion: Try a different date range or verify the URL is publicly accessible.
```

**Partial Failures:**
- If querying multiple events (from profile), some may succeed while others fail
- Each event in response includes its own error/success status
- Range errors are reported in the `range_errors` array

## Development

### Project Structure
```
calendly-mcp-server/
├── Dockerfile
├── README.md
├── requirements.txt
├── .dockerignore
└── src/
    ├── __init__.py
    ├── main.py           # FastAPI application
    ├── mcp_server.py     # MCP protocol implementation
    └── calendly_slots.py # Core Calendly scraping logic
```

### Testing

```bash
# Test the core function directly
python -c "
import asyncio
from src.calendly_slots import slots_for_profile_or_event

async def test():
    result = await slots_for_profile_or_event(
        url='https://calendly.com/zarek-drozda',
        tz='America/New_York',
        start='2025-10-15',
        end='2025-11-15',
        sniff_wait=6.0,
        sleep=0.35
    )
    print(result)

asyncio.run(test())
"
```

## License

Part of the AI-PA ecosystem.

## References

- [Letta Documentation](https://docs.letta.com/)
- [Model Context Protocol](https://modelcontextprotocol.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Playwright Documentation](https://playwright.dev/python/)

