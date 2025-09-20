# PBI-5: Containerize and Integrate Slackbot into PA Ecosystem

[View in Backlog](../backlog.md#user-content-5)

## Overview

This PBI focuses on containerizing the existing Slackbot application and integrating it into the unified PA ecosystem as a Docker service. The Slackbot provides interactive chatbot functionality within Slack, communicating with Letta for AI responses. This PBI does not address the separate Slack MCP server (which is covered by PBI 4).

## Problem Statement

Currently, the Slackbot application runs as a standalone Python application outside of the containerized ecosystem. This creates several issues:

1. **Deployment inconsistency**: Slackbot not managed with other services via Docker Compose
2. **Configuration management**: Slackbot configuration not integrated with unified environment management
3. **Monitoring gaps**: Slackbot not included in centralized logging and health monitoring
4. **Operational complexity**: Requires separate deployment and management procedures
5. **Service isolation**: Slackbot not part of the unified Docker network architecture

## User Stories

### Primary User Story
**As an application developer**, I want the Slackbot containerized and integrated into the ecosystem so that it can be managed and deployed alongside other services.

### Supporting User Stories
- **As a system administrator**, I want the Slackbot to run as a Docker service so that I can manage it consistently with other services
- **As a DevOps engineer**, I want the Slackbot to connect to Letta via internal network so that communication is secure and efficient
- **As a user**, I want all current Slack functionality preserved so that my workflow remains uninterrupted
- **As an operations engineer**, I want Slackbot logs integrated with centralized logging so that I can monitor and troubleshoot effectively

## Technical Approach

### Current State Analysis
- **Existing Slackbot**: Python-based application using Slack Bolt framework
- **Current MCP Integration**: External Slack MCP server at `slack-mcp-server:3001`
- **Letta Configuration**: Already configured to connect to `http://slack-mcp-server:8081`

### Implementation Strategy

#### 1. Containerization
- Create Dockerfile for Slackbot application
- Ensure all dependencies are properly managed
- Configure proper logging and health checks

#### 2. Docker Compose Integration
- Add Slackbot service to main docker-compose.yml
- Configure proper networking and service dependencies
- Set up environment variable management

#### 3. Service Configuration
- Environment variable management for Slack tokens and Letta connection
- Health check implementation
- Logging integration with centralized logging

#### 4. Letta Integration
- Maintain existing Letta API communication
- Ensure proper network connectivity between containers
- Preserve all existing Slackbot functionality

### Architecture Changes

```
Before:
Slackbot (standalone Python app) → Letta (HTTP API)
External Slack MCP Server (separate container) → Letta (MCP tools)

After:
Slackbot (containerized) → Letta (HTTP API)
External Slack MCP Server (unchanged) → Letta (MCP tools)
```

## UX/UI Considerations

- **No user-facing changes**: All Slack functionality remains the same
- **Transparent integration**: Users should not notice any difference in Slack behavior
- **Improved reliability**: Better control over Slack integration service
- **Enhanced monitoring**: Better visibility into Slack service health and logs

## Acceptance Criteria

1. **Docker Service**: Slackbot runs as a Docker service in docker-compose.yml
2. **Internal Network**: Connects to Letta via internal network (pa-network)
3. **Functionality Preservation**: All current Slack functionality preserved
4. **Letta Integration**: Maintains existing Letta API communication
5. **Logging Integration**: Logs integrated with centralized logging system
6. **Service Management**: Can be started/stopped with docker-compose commands
7. **Health Checks**: Proper health check implementation
8. **Environment Configuration**: Proper environment variable management
9. **Streaming Responses**: Human-like progressive message updates using Letta streaming API

## Dependencies

- **PBI 2**: Docker Compose unification (must be completed first)
- **PBI 3**: Network unification (must be completed first)
- **PBI 4**: MCP server standardization (provides patterns to follow)

## Streaming Enhancement

### Human-Like Interaction
The Slackbot will implement streaming responses to provide a more natural, human-like interaction experience:

- **Progressive Updates**: Messages update in real-time as content streams from Letta
- **Rate Limiting**: Throttled updates (0.5s intervals, 5-chunk batches) to avoid API limits
- **Message Length Management**: Proper handling of long responses with truncation
- **Error Handling**: Graceful fallback to non-streaming on errors
- **Loading Behavior**: Replace static "Thinking..." with dynamic content updates

### Technical Implementation
- Switch from `LettaAPI` to `LettaAPIStreaming` class
- Use `chat_update()` for progressive message updates
- Implement proper error handling and fallback mechanisms
- Configure rate limiting to respect Slack API limits

## Open Questions

1. **MCP Interface Implementation**: What specific MCP tools should the Slackbot expose?
2. **Authentication**: How should Slack tokens be managed in the containerized environment?
3. **State Management**: How should user state be persisted in the containerized environment?
4. **Streaming Configuration**: Should streaming be configurable per user or globally?
5. **Error Handling**: What error handling patterns should be implemented for MCP interface?

## Related Tasks

- [Task 5-1: Analyze current Slackbot implementation](./5-1.md)
- [Task 5-2: Create Dockerfile for Slackbot](./5-2.md)
- [Task 5-3: Update Docker Compose to integrate containerized Slackbot](./5-3.md)
- [Task 5-4: Test Slackbot integration and validate functionality](./5-4.md)
- [Task 5-5: Implement streaming responses for human-like interaction](./5-5.md)
