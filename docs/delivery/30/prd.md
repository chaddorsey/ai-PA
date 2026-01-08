# PBI-30: PA Web Interface and Routing Handler

[View in Backlog](../backlog.md#user-content-30)

## Overview

This PBI creates a web-based Personal Assistant interface with an intelligent routing handler that directs messages to the appropriate Letta agents. The system provides a specialized PA experience that complements the existing Open WebUI, with features for dashboard visualization, file uploads, and extensibility for future multi-source message routing.

## Problem Statement

Currently, interaction with the Letta agent ecosystem is limited to:
1. **Slack** - Requires Slack workspace access, limited UI customization
2. **Open WebUI** - Generic chat interface, not optimized for PA-specific features
3. **Direct API** - Technical barrier for casual use

Users need a dedicated web interface that:
- Is accessible from any device via web browser
- Provides PA-specific features (agent selection, memory visualization, dashboard)
- Supports rich inputs (files, screenshots)
- Can be extended to support additional input sources (Telegram, SMS)

## User Stories

### Primary User Story
**As a user**, I want a web-based chat interface with intelligent routing so that I can interact with my personal assistant from any device and have my messages automatically routed to the most appropriate Letta agent.

### Supporting User Stories
- **As a user**, I want to see available agents and their capabilities so that I can choose the right agent for my request
- **As a user**, I want to view agent memory blocks so that I can understand what context the agent has about me
- **As a user**, I want to upload files and screenshots so that I can share visual information with the agent
- **As a user**, I want streaming responses so that I can see the agent's reply as it's generated
- **As a user**, I want conversation history so that I can reference previous interactions
- **As a power user**, I want the routing handler to be extensible so that future input sources (Telegram) use the same routing logic

## Technical Approach

### Architecture

```
User Browser (Web UI)
    ↓ HTTPS (Cloudflare Tunnel)
PA Web Service (Port 5200)
  - Flask backend with SSE
  - Static frontend (Vanilla JS)
  - Session management
  - File upload handling
    ↓ HTTP (pa-internal network)
PA Routing Handler (Port 5201)
  - FastAPI service
  - Phase 1: Simple pattern matching
  - Phase 2: DSPy-based routing
    ↓ HTTP (pa-internal network)
Letta Service (Port 8283)
  - Multiple agents (task/calendar/pulse/default)
  - SSE streaming responses
```

### Technology Stack

- **Frontend**: Vanilla JS + SSE (matches auto-madden pattern)
- **Web Service**: Flask + Flask-SOCK (proven pattern)
- **Routing Handler**: FastAPI (async support, OpenAPI docs)
- **Database**: Supabase PostgreSQL (conversation history, routing analytics)
- **Communication**: Server-Sent Events (matches Letta's protocol)

### Key Design Decisions

1. **Two-service architecture** - Separates UI serving from routing logic, enabling multi-source routing
2. **SSE over WebSocket** - Matches Letta's existing streaming pattern
3. **Vanilla JS** - Simple, no build step, fast iteration
4. **Phase 1 simplicity** - Pattern matching first, DSPy intelligence later
5. **Complement Open WebUI** - Specialized PA interface vs generic chat

### Service Specifications

**PA Web Service (pa-web-ui)**
- Port: 5200 (exposed via `pa.cd-ai-pa.work`)
- Endpoints: `/`, `/health`, `/api/config`, `/api/agents`, `/api/agents/{id}/memory`, `/api/upload`, `/stream`

**PA Routing Handler (pa-routing-handler)**
- Port: 5201 (internal only)
- Endpoints: `/v1/route`, `/v1/agents`, `/v1/agents/select`, `/health`

### Database Schema

- `pa_web_conversations` - Message history with session tracking
- `pa_routing_decisions` - Analytics for routing logic
- `pa_web_sessions` - Session management (Phase 2 with Redis)

## UX/UI Considerations

- **Dark theme** following auto-madden design language
- **Chat interface** with message bubbles, timestamps, agent attribution
- **Agent selector** dropdown with descriptions
- **Dashboard panel** for memory blocks and agent status
- **File upload** with drag-and-drop and preview
- **Loading states** and streaming text animation
- **Mobile responsive** design

## Acceptance Criteria

1. Web chat interface accessible via Cloudflare tunnel at `pa.cd-ai-pa.work`
2. Messages routed to appropriate Letta agent (manual selection Phase 1, automatic in Phase 2)
3. Streaming responses displayed in real-time with proper formatting
4. Dashboard displays agent memory blocks and refreshes automatically
5. File upload support for images and documents (up to 10MB)
6. Conversation history stored in PostgreSQL and viewable in UI
7. Coexists with Open WebUI without conflicts (different port/URL)
8. Health checks for both services pass
9. Services integrate cleanly with existing Docker Compose setup

## Dependencies

- **Letta Service** (port 8283) - Agent execution and streaming
- **Supabase PostgreSQL** - Conversation and routing data storage
- **Cloudflare Tunnel** - External access routing

## Open Questions

1. ~~Should we replace or complement Open WebUI?~~ **Decided: Complement**
2. ~~DSPy integration priority?~~ **Decided: Phase 2**
3. ~~Ollama integration?~~ **Decided: Defer to cloud LLMs**
4. ~~Authentication level?~~ **Decided: Open access initially**

## Related Tasks

See [tasks.md](./tasks.md) for the complete task breakdown.

### Phase 1 Tasks (MVP)
- 30-1: Project Setup and Docker Configuration
- 30-2: Database Schema and Migrations
- 30-3: PA Web Service - Backend Foundation
- 30-4: PA Web Service - Frontend UI
- 30-5: PA Routing Handler - Core Service
- 30-6: PA Routing Handler - Phase 1 Routing Logic
- 30-7: Letta Integration - Client Library
- 30-8: PA Web Service - SSE Streaming
- 30-9: Dashboard Features - Agent Info
- 30-10: File Upload Support
- 30-11: Cloudflare Tunnel Configuration
- 30-12: Documentation and Deployment Guide
- 30-13: E2E Testing and Bug Fixes

### Phase 2 Tasks (Future)
- DSPy Intent Classification
- Multi-Source Support (Telegram)
- Advanced Dashboard Analytics
- Authentication and User Management
