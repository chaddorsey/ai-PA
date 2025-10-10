# PBI 18: Calendly Availability Checking via MCP Server

**Status**: Proposed  
**Actor**: AI Engineer  
**Created**: 2025-10-10  

[Back to Backlog](../backlog.md)

## Overview

Integrate Calendly availability checking into the Letta agent ecosystem by deploying a dedicated MCP server that wraps the existing calendly-scraper Python tools. This will enable the personal assistant to intelligently query Calendly scheduling links and provide availability information for meeting coordination.

## Problem Statement

Currently, the personal assistant cannot help with scheduling coordination because it lacks visibility into Calendly availability. Users must manually check Calendly links to find available meeting times, which is time-consuming and doesn't leverage the AI's ability to assist with scheduling workflows.

The existing `calendly-scraper` tools in the repository provide robust functionality for:
- Discovering event types from Calendly profiles
- Sniffing event UUIDs via browser automation
- Fetching available dates and time slots
- Handling timezone conversions

However, these tools are standalone Python scripts and not integrated into the Letta agent ecosystem.

## User Stories

### Primary User Story
**As an AI engineer**, I want Calendly availability checking integrated into Letta as an MCP server so that my personal assistant can intelligently query scheduling availability and suggest meeting times.

### Supporting User Stories
1. **As a user**, I want to ask my assistant "What times is X available?" and get accurate Calendly slot information
2. **As a user**, I want the assistant to handle both profile URLs and specific event URLs seamlessly
3. **As a developer**, I want the Calendly MCP server to follow the same patterns as other MCP servers for consistency
4. **As an operations engineer**, I want the Calendly service to be monitored and health-checked like other services

## Technical Approach

### Architecture
Deploy the Calendly scraper as a containerized MCP server following the established pattern used by gmail-mcp, graphiti-mcp, and rag-mcp servers:

```
┌─────────────────┐
│  Letta Agent    │
│  (Container)    │
└────────┬────────┘
         │ MCP Protocol
         │ (HTTP)
         ▼
┌─────────────────────┐
│ Calendly MCP Server │
│  - HTTP wrapper     │
│  - Tool registry    │
│  - Playwright       │
│  - Python runtime   │
└─────────────────────┘
```

### Implementation Strategy

1. **Create MCP Server Wrapper**
   - Build FastAPI or similar HTTP server
   - Expose calendly_slots tool via MCP protocol
   - Handle async operations properly
   - Implement health check endpoint

2. **Docker Integration**
   - Create Dockerfile with Python + Playwright + Chromium
   - Add service to docker-compose.yml
   - Configure on pa-internal network
   - Set up volume mounts if needed for cache

3. **Letta Integration**
   - Add calendly-tools to letta_mcp_config.json
   - Configure HTTP endpoint
   - Test tool discovery and invocation

4. **Resource Management**
   - Playwright/Chromium can be memory-intensive
   - Implement request queuing if needed
   - Consider timeout and rate limiting

### Technology Stack
- **Runtime**: Python 3.11+
- **Web Framework**: FastAPI (for MCP HTTP wrapper)
- **Browser Automation**: Playwright + Chromium
- **HTTP Client**: requests + aiohttp
- **HTML Parsing**: BeautifulSoup4
- **Base Tool**: calendly_letta_tool.py (already implements BaseTool)

### Dependencies
- Requires docker-compose.yml updates
- Requires letta_mcp_config.json updates
- Depends on existing pa-internal network (PBI 3 - Done)
- Follows MCP server patterns established in PBIs 4, 13

## UX/UI Considerations

### Agent Interaction Patterns
Users should be able to interact naturally:
- "Check Zarek's availability next week"
- "What times does the calendly.com/john/30min event have open?"
- "Find me a slot on Alice's calendar between 2-4pm EST"

### Response Format
The tool should return structured data that the agent can interpret:
```json
{
  "events": [
    {
      "title": "30 Minute Meeting",
      "url": "https://calendly.com/user/30min",
      "days": ["2025-10-15", "2025-10-16"],
      "times": {
        "2025-10-15": ["09:00", "10:00", "14:30"],
        "2025-10-16": ["11:00", "15:00"]
      }
    }
  ]
}
```

### Error Handling
Graceful degradation for:
- Invalid Calendly URLs
- Private/inaccessible calendars
- Network timeouts
- Rate limiting

## Acceptance Criteria

### Functional Requirements
1. ✅ Calendly MCP server deployed as Docker service
2. ✅ Server exposes `calendly_slots` tool via MCP protocol
3. ✅ Letta can discover and invoke the Calendly tool
4. ✅ Tool successfully queries Calendly profile URLs for available dates
5. ✅ Tool successfully queries specific event URLs for time slots
6. ✅ Timezone handling works correctly (default: America/New_York)
7. ✅ Date range parameters work (start, end dates)

### Non-Functional Requirements
8. ✅ Health checks validate server availability
9. ✅ Server starts automatically with docker-compose up
10. ✅ Proper error messages returned for invalid inputs
11. ✅ Response times < 30 seconds for typical queries
12. ✅ Documentation includes usage examples

### Integration Requirements
13. ✅ Service appears in Letta's MCP server list
14. ✅ Service accessible from Letta container via pa-internal network
15. ✅ Logs integrated with centralized logging pattern
16. ✅ Service follows naming conventions (calendly-mcp-server)

## Dependencies

### External Dependencies
- **Upstream**: Calendly's undocumented `/api/booking/event_types/<UUID>/calendar/range` endpoint
- **Note**: This is a frontend API that could change without notice

### Internal Dependencies
- Docker Compose infrastructure (PBI 2 - Proposed)
- pa-internal network (PBI 3 - Done)
- Letta container with MCP support (current)

### Technical Dependencies
- Playwright requires Chromium browser (~200MB)
- Python dependencies: requests, beautifulsoup4, lxml, pydantic, fastapi

## Open Questions

1. **Caching Strategy**: Should we cache availability data? For how long?
   - Recommendation: Start without caching, add if needed

2. **Rate Limiting**: What rate limits should we impose?
   - Recommendation: One request per 2 seconds to be respectful

3. **Concurrent Requests**: Should we limit concurrent Playwright instances?
   - Recommendation: Limit to 2-3 concurrent to manage memory

4. **Error Recovery**: How should we handle Calendly API changes?
   - Recommendation: Fail gracefully with informative errors

5. **Authentication**: Do we need to support authenticated Calendly access?
   - Recommendation: Phase 1 is public URLs only

## Related Tasks

See [tasks.md](./tasks.md) for the complete task breakdown.

## Technical Design Notes

### MCP Server Structure
```
calendly-mcp-server/
├── Dockerfile
├── requirements.txt
├── src/
│   ├── main.py              # FastAPI MCP wrapper
│   ├── calendly_tool.py     # Copied from ../calendly-scraper/
│   └── mcp_server.py        # MCP protocol implementation
└── README.md
```

### Environment Variables
```bash
MCP_SERVER_NAME=calendly-tools
MCP_SERVER_VERSION=1.0.0
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8086
CALENDLY_DEFAULT_TIMEZONE=America/New_York
CALENDLY_REQUEST_TIMEOUT=30
```

### Docker Compose Entry
```yaml
calendly-mcp-server:
  build:
    context: ./calendly-mcp-server
  container_name: calendly-mcp-server
  restart: unless-stopped
  networks: [pa-internal]
  ports:
    - "8086:8086"
  environment:
    - MCP_SERVER_NAME=calendly-tools
    - MCP_SERVER_VERSION=1.0.0
    - MCP_SERVER_PORT=8086
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8086/health"]
    interval: 30s
    timeout: 5s
    retries: 3
```

## Success Metrics

1. **Integration Success**: Letta successfully calls Calendly tool
2. **Response Accuracy**: Returns correct availability data
3. **Performance**: Average response time < 20 seconds
4. **Reliability**: Server uptime > 99% during testing
5. **Usability**: Clear error messages for common failure cases

## Risk Assessment

### Medium Risks
- **Calendly API Changes**: The undocumented API could change
  - *Mitigation*: Implement robust error handling and logging
  
- **Resource Consumption**: Playwright + Chromium is heavy
  - *Mitigation*: Limit concurrent instances, monitor memory

### Low Risks
- **Network Timeout**: Calendly service unavailable
  - *Mitigation*: Appropriate timeouts and retry logic

- **Invalid URLs**: Users provide malformed URLs
  - *Mitigation*: Input validation and clear error messages

## Future Enhancements (Out of Scope)

- Authenticated Calendly API access for private calendars
- Booking capability (not just availability checking)
- Calendar comparison across multiple people
- Integration with personal calendar (Google Calendar)
- Intelligent meeting time suggestions based on preferences
- Webhook integration for real-time availability updates

