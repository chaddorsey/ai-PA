# Tasks for PBI 18: Calendly Availability Checking via MCP Server

This document lists all tasks associated with PBI 18.

**Parent PBI**: [PBI 18: Calendly Availability Checking via MCP Server](./prd.md)

## Task Summary

| Task ID | Name | Status | Description |
| :------ | :--------------------------------------- | :------- | :--------------------------------- |
| 18-1 | [Create calendly-mcp-server project structure](./18-1.md) | Proposed | Set up directory structure, requirements.txt, and basic project files |
| 18-2 | [Implement MCP HTTP wrapper with FastAPI](./18-2.md) | Proposed | Create FastAPI server that exposes calendly_slots tool via MCP protocol |
| 18-3 | [Create Dockerfile with Playwright support](./18-3.md) | Proposed | Build Docker image with Python, Playwright, and Chromium |
| 18-4 | [Update docker-compose.yml for calendly service](./18-4.md) | Proposed | Add calendly-mcp-server service configuration to main compose file |
| 18-5 | [Register Calendly MCP server with Letta](./18-5.md) | Proposed | Update letta_mcp_config.json to include calendly-tools |
| 18-6 | [Create end-to-end integration test](./18-6.md) | Proposed | Test Letta agent can discover and invoke Calendly tool successfully |
| 18-7 | [Create usage documentation and examples](./18-7.md) | Proposed | Document tool usage, API reference, and common patterns |

## Task Dependencies

```
18-1 (Project Structure)
  │
  ├─> 18-2 (MCP Wrapper)
  │     │
  │     └─> 18-3 (Dockerfile)
  │           │
  │           └─> 18-4 (docker-compose)
  │                 │
  │                 └─> 18-5 (Letta config)
  │                       │
  │                       └─> 18-6 (E2E Test)
  │
  └─> 18-7 (Documentation) [can be done in parallel with 18-2 to 18-5]
```

## Implementation Notes

### Critical Path
Tasks 18-1 through 18-6 must be completed sequentially as each depends on the previous.

### Parallel Work
Task 18-7 (documentation) can be started early and updated as implementation progresses.

### Testing Strategy
- Task 18-2: Unit tests for MCP wrapper
- Task 18-3: Container build verification
- Task 18-4: Service startup and health checks
- Task 18-5: Letta can discover service
- Task 18-6: Full end-to-end workflow test

### Technical Risks
- **Playwright installation**: Chromium download is large (~200MB), may slow builds
  - Mitigation: Use multi-stage Docker build, cache layers
- **Memory usage**: Chromium instances can consume significant memory
  - Mitigation: Implement request queuing, limit concurrent instances
- **API stability**: Calendly's undocumented API could change
  - Mitigation: Comprehensive error handling and logging

## Estimated Effort

| Task | Complexity | Estimated Time |
|------|-----------|----------------|
| 18-1 | Low | 30 minutes |
| 18-2 | Medium | 2-3 hours |
| 18-3 | Medium | 1-2 hours |
| 18-4 | Low | 30 minutes |
| 18-5 | Low | 15 minutes |
| 18-6 | Medium | 1-2 hours |
| 18-7 | Low | 1 hour |
| **Total** | | **6-9 hours** |

## Success Criteria

All tasks must be completed and verified before PBI 18 can be marked as Done:

1. ✅ calendly-mcp-server directory exists with all required files
2. ✅ Server starts successfully via docker-compose
3. ✅ Health check endpoint returns 200 OK
4. ✅ Letta discovers calendly_slots tool
5. ✅ End-to-end test passes: Letta → MCP → Calendly → response
6. ✅ Documentation includes working examples
7. ✅ All acceptance criteria from PRD are met

