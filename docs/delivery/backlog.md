# AI Personal Assistant Ecosystem - Product Backlog

This backlog contains all Product Backlog Items (PBIs) for the AI Personal Assistant Ecosystem Unification project, ordered by priority (highest at the top).

## Backlog Items

| ID | Actor | User Story | Status | Conditions of Satisfaction (CoS) |
|:---|:------|:-----------|:-------|:---------------------------------|
| 1 | System Administrator | As a system administrator, I want to consolidate all PostgreSQL databases into a unified Supabase instance so that I can manage data more efficiently and reduce resource overhead. | Proposed | All databases (n8n, Letta, RAG) use single PostgreSQL instance with proper schema isolation; Migration scripts preserve all data; Performance equivalent to current setup; Backup procedures unified - [View Details](./1/prd.md) |
| 2 | DevOps Engineer | As a DevOps engineer, I want all services unified in a single Docker Compose configuration so that I can deploy and manage the entire PA ecosystem with one command. | Proposed | Single docker-compose.yml contains all services; One-command deployment from clean environment; Service dependencies properly configured; Health checks validate all services startup correctly - [View Details](./2/prd.md) |
| 3 | Network Administrator | As a network administrator, I want all inter-service communication on a unified Docker network so that services can communicate securely and efficiently without external dependencies. | Done | All services on pa-internal network; No hardcoded IPs in configurations; Service discovery via DNS names; External access only via designated endpoints; Network isolation validates correctly - [View Details](./3/prd.md) |
| 4 | Integration Engineer | As an integration engineer, I want all MCP servers standardized and integrated into the main Docker Compose so that Letta can access all capabilities through a consistent interface. | Proposed | Gmail MCP migrated from separate compose; All MCP servers use consistent configuration patterns; Letta connects to all MCP servers successfully; Health checks validate MCP server availability - [View Details](./4/prd.md) |
| 20 | Integration Engineer | As an integration engineer, I want Slack analytics exports provided by a dedicated MCP service so that Letta tools can trigger exports reliably without depending on unrelated services. | Done | Slack analytics export FastAPI service available on pa-internal network; Service runs in its own Docker container with health checks; Letta tool configured to call new service; Operational runbook documents deployment and troubleshooting - [View Details](./20/prd.md) |
| 5 | Application Developer | As an application developer, I want the Slackbot containerized and integrated into the ecosystem so that it can be managed and deployed alongside other services. | Agreed | Slackbot runs as Docker service; Connects to Letta via internal network; All current Slack functionality preserved; Logs integrated with centralized logging; Can be started/stopped with docker-compose - [View Details](./5/prd.md) |
| 6 | Operations Engineer | As an operations engineer, I want external access via Cloudflare tunnels integrated into the Docker setup so that remote access is secure and properly managed. | InProgress | Cloudflare tunnel runs as container service; Remote access to necessary services works; Tunnel configuration managed via environment variables; Failover and reconnection handling implemented - [View Details](./6/prd.md) |
| 7 | Home Server Owner | As a home server owner, I want a complete deployment kit with documentation so that I can easily deploy and maintain the PA ecosystem on my home infrastructure. | InProgress | Complete deployment documentation; Single-command deployment script; Environment configuration templates; Backup and restore procedures documented; Troubleshooting guide provided - [View Details](./7/prd.md) |
| 8 | QA Engineer | As a QA engineer, I want comprehensive end-to-end testing procedures so that I can validate all PA workflows function correctly after system unification. | Proposed | Test procedures for all major workflows; Automated tests for critical paths; Performance benchmarks established; Test data and scenarios documented; Validation scripts executable - [View Details](./8/prd.md) |
| 9 | Security Engineer | As a security engineer, I want proper secrets management and network security policies so that the unified system maintains security best practices for home server deployment. | Proposed | All secrets managed via environment variables; No hardcoded credentials in code; Network segmentation implemented; TLS/SSL for external communications; Security scanning procedures documented - [View Details](./9/prd.md) |
| 10 | Product Owner | As a product owner, I want performance validation and optimization so that the unified system meets or exceeds current performance benchmarks. | Proposed | Performance benchmarks documented; System startup time ≤ 5 minutes; Memory usage optimized; Database query performance maintained; Monitoring dashboards operational - [View Details](./10/prd.md) |
| 11 | System Administrator | As a system administrator, I want framework version management with controlled upgrade paths so that I can safely update n8n, Letta, and Graphiti while maintaining cutting-edge features and system reliability. | Done | Version lock file maintains current working versions; Upgrade procedures documented for each framework; Version compatibility matrix maintained; Rollback procedures tested and documented - [View Details](./11/prd.md) |
| 12 | DevOps Engineer | As a DevOps engineer, I want lean upgrade infrastructure with automated testing so that framework upgrades are validated in staging before production deployment with quick rollback capability. | Proposed | Staging environment for testing upgrades; Automated workflow validation; Database migration testing; Rollback capability within 5 minutes; Critical workflow tests automated - [View Details](./12/prd.md) |
| 13 | AI Engineer | As an AI engineer, I want extensible RAG infrastructure integrated through Letta so that the personal assistant can access and search through technical documentation, personal notes, and domain-specific knowledge bases. | Proposed | HayHooks service deployed and operational; RAG MCP server integrated with Letta; Document ingestion workflow functional; Semantic search queries return relevant results; Tool-based access from Letta working - [View Details](./13/prd.md) |
| 14 | System Administrator | As a system administrator, I want RAG document processing and storage using the existing PostgreSQL infrastructure so that document knowledge is integrated seamlessly with the unified database approach. | Proposed | RAG documents stored in PostgreSQL with pgvector; Document embedding pipeline operational; Incremental document updates supported; Domain-specific document organization; Backup procedures include RAG data - [View Details](./14/prd.md) |
| 15 | Productivity Specialist | As a productivity specialist, I want project-oriented MCP tooling to expose accurate OmniFocus project metadata so that downstream automations can trust quick-access summaries. | Proposed | projectOperations list returns created/modified timestamps and status data; projectOperations detailLevel outputs differ across minimal/standard/full; listProjects surfaces folder metadata and honours listByFolder flag; Regression tests and docs capture the updated tool behaviour - [View Details](./15/prd.md) |
| 16 | Conversational AI Designer | As a conversational AI designer, I want rich OmniFocus MCP tool metadata and onboarding guidance so that LLMs invoke the tools correctly without repeated failures. | Proposed | Tool descriptions explain required fields and defaults; Quick-start help tool provides usage examples; Welcome notification advertises help reference; Smoke tests confirm help tool availability - [View Details](./16/prd.md) |
| 17 | Productivity Specialist | As a productivity specialist, I want task durations surfaced in simplified OmniFocus tools so that automations and LLMs can reason about effort. | Proposed | Quick task listings and project summaries include durationMinutes; schemas updated; docs and smoke tests refreshed with duration examples - [View Details](./17/prd.md) |
| 18 | AI Engineer | As an AI engineer, I want Calendly availability checking integrated into Letta as an MCP server so that my personal assistant can intelligently query scheduling availability and suggest meeting times. | Proposed | Calendly MCP server deployed as Docker service; Server exposes slot-checking tools via MCP protocol; Letta can query Calendly URLs for available dates and times; Health checks validate server availability; Documentation includes usage examples - [View Details](./18/prd.md) |
| 19 | Platform Architect | As a platform architect, I want a dedicated scheduling and reminder service integrated with Letta so that time-indexed actions remain reliable, persistent, and searchable across the ecosystem. | Proposed | Scheduler runs as Docker service with shared Postgres/pgvector access; REST and MCP surfaces available to Letta; Job definitions, executions, and metadata persisted with embeddings; Supports Letta reminders and external actions with archival search; Security posture documented; Usage and integration documentation published - [View Details](./19/prd.md) |
| 21 | Executive / EA | As a user, I want a single Letta tool that turns my chat request and my team's calendars into reliable meeting proposals that follow my rules and minimize disruption, so that Letta can schedule directly. | Agreed | (1) Single orchestration tool (Pattern B) with typed schema; (2) Accepts events from Letta's Get_Events; (3) 15-min grid-time ASP with lexicographic optimization; (4) Returns ready-to-schedule proposals + explanation; (5) Provides relaxations on UNSAT; (6) Performs within set time budget for typical horizons - [View Details](./21/prd.md) |
| 22 | Executive / EA | As a user, I want to reschedule existing meetings by asking for new time options, so that Letta can automatically identify the meeting and propose alternatives while preserving all meeting details. | Agreed | (1) Tool accepts event_id parameter or identifies event from natural language; (2) Extracts meeting details (participants, duration, title) from existing event; (3) Finds alternative time slots treating original event as movable; (4) Preserves original event metadata in proposals; (5) Maintains backward compatibility with new meeting scheduling - [View Details](./22/prd.md) |
| 23 | System Administrator | As a system administrator, I want to migrate Letta from v0.12.1 to v0.14.0 with SDK v1.0 compatibility so that I can take advantage of performance improvements and new features while maintaining system stability. | Proposed | (1) All breaking SDK changes updated (modify→update, list pagination, snake_case properties); (2) Server upgraded to 0.14.0; (3) All tools and scripts tested and working; (4) Version lock files updated; (5) Migration documented with rollback procedures - [View Details](./23/prd.md) |
| 24 | Executive / EA | As a user, I want a daily briefing tool that generates a formatted schedule report with available time calculations, so that Letta can provide me with an up-to-date view of my day at any time. | Agreed | (1) Tool retrieves calendar events from cdorsey@concord.org via MCP Core_Event_Data; (2) Filters and formats events according to gold-standard rules; (3) Calculates available time from current time to 5:00 PM Eastern; (4) Generates Markdown-formatted briefing with proper time formatting; (5) Updates memory block with briefing content; (6) Handles Eastern time with daylight savings correctly - [View Details](./24/prd.md) |
| 25 | Executive / EA | As a user, I want comprehensive Google Calendar CRUD tools for Letta agents so that I can create, read, update, and delete calendar events through natural language, supporting all standard event properties including times with timezone, attendees, location, description, and file attachments. | Proposed | (1) Tools use user OAuth authentication following Drive API pattern; (2) Full CRUD operations (create, read, update, delete events); (3) Support for all event properties (summary, times with timezone, description, location, attendees, attachments); (4) Support for both own calendar and shared calendars; (5) Comprehensive error handling and validation; (6) All tools registered with Letta with proper schemas - [View Details](./25/prd.md) |

|| 26 | Executive / EA | As a user, I want consolidated Drive analytics tools with user, owner, and date range filtering so that I can answer questions like "What did Cynthia edit last week?" without multiple tool calls. | Agreed | (1) Unified search_drive_activity tool with user/owner/date/activity filters; (2) get_drive_documents for document discovery; (3) Preserved analytics capabilities; (4) All example questions answerable; (5) Old tools deprecated but functional; (6) New tools registered with Letta - [View Details](./26/prd.md) |
| 27 | Home User | As a home user, I want a Letta agent with sports and media control tools so that I can ask "Watch the Patriots game" and have the TV automatically tune to the correct channel or streaming service. | Done | (1) ESPN API polling service deployed; (2) Flipper Zero IR control API deployed; (3) Roku TV control via ECP; (4) Letta tools for sports queries, channel lookup, TV control, and game watching; (5) End-to-end orchestration works for cable and streaming games - [View Details](./27/prd.md) |
| 28 | Home User | As a home user, I want intentional series tracking with manual progress, status management, and new season monitoring so that Letta can tell me what I haven't watched and notify me of new seasons. | Done | (1) tracked_series table with status/progress fields; (2) Add/remove series by title with JustWatch lookup; (3) Status management (watching/finished/dropped/on_hold); (4) Manual progress override with flexible spec parsing; (5) New season detection for finished series; (6) Watchlist auto-tracking integration; (7) Multi-user and multi-service support - [View Details](./28/prd.md) |
|| 29 | Home User | As a home user watching an NFL game, I want a real-time AI companion that provides contextual insights, explains plays, and answers questions tuned to my knowledge level so that I can better understand and enjoy the game. | InProgress | (1) Real-time ESPN API polling for game state; (2) Template and LLM-based insight generation; (3) Adaptive delivery timing (max 4/min, respects game flow); (4) Web chat interface for interaction; (5) Letta agent integration for memory-enriched responses; (6) User knowledge level tracking - [View Details](./29/prd.md) |
| 30 | User | As a user, I want a web-based chat interface with intelligent routing so that I can interact with my personal assistant from any device and have my messages automatically routed to the most appropriate Letta agent. | Done | (1) Web chat interface accessible via Cloudflare tunnel; (2) Messages routed to appropriate Letta agent; (3) Streaming responses displayed in real-time; (4) Dashboard displays agent memory blocks; (5) File upload support; (6) Conversation history stored; (7) Coexists with Open WebUI - [View Details](./30/prd.md) |
| 31 | User | As a user, I want contextual routing and threaded conversations so that follow-up messages route to the correct agent and concurrent requests are visually organized. | Done | (1) Brief follow-ups route to previous agent 80%+ of time; (2) Concurrent requests supported without blocking; (3) Responses visually threaded under originating requests; (4) Reply button continues conversation with specific agent; (5) No regression in keyword routing accuracy - [View Details](./31/prd.md) |

## PBI History Log

| Timestamp | PBI_ID | Event_Type | Details | User |
|:----------|:-------|:-----------|:--------|:-----|
| 2025-09-20 01:30:00 | ALL | create_pbi | Initial backlog created based on ecosystem unification analysis | AI_Agent |
| 2025-09-20 02:15:00 | 11,12 | create_pbi | Added framework upgrade management PBIs based on practical n8n upgrade analysis | AI_Agent |
| 2025-10-09 07:19:48 | 17 | create_pbi | Added PBI 17 to expose task duration in simplified OmniFocus tools | AI_Agent |
| 2025-10-09 07:32:07 | 17 | approve | PBI 17 completed - duration exposed in quick tools and documentation | AI_Agent |
| 2025-09-20 02:45:00 | 13,14 | create_pbi | Added RAG infrastructure PBIs based on lean HayHooks integration approach | AI_Agent |
| 2025-01-20 16:30:00 | 3 | approve | PBI 3 moved from Proposed to Agreed - ready for implementation | User |
| 2025-01-20 18:40:00 | 3 | approve | PBI 3 completed successfully - all conditions of satisfaction met | AI_Agent |
| 2025-01-20 19:15:00 | 5 | propose_for_backlog | PBI 5 moved from Proposed to Agreed - ready for implementation | AI_Agent |
| 2025-09-21 03:30:00 | 6 | start_implementation | PBI 6 moved from Proposed to InProgress - Cloudflare tunnel integration started | AI_Agent |
| 2025-01-20 20:15:00 | 7 | propose_for_backlog | PBI 7 moved from Proposed to Agreed - deployment kit ready for implementation | AI_Agent |
| 2025-01-21 01:50:00 | 7 | start_implementation | PBI 7 implementation completed - comprehensive deployment kit with 61 files created | AI_Agent |
| 2025-01-21 04:30:00 | 11 | propose_for_backlog | PBI 11 moved from Proposed to Agreed - framework version management ready for implementation | AI_Agent |
| 2025-01-21 09:35:00 | 11 | approve | PBI 11 completed - all acceptance criteria met, comprehensive version management framework implemented | User |
| 2025-10-08 14:20:00 | 15 | create_pbi | Added PBI 15 to repair OmniFocus project metadata exposure in MCP quick tools | AI_Agent |
| 2025-10-10 12:00:00 | 18 | create_pbi | Added PBI 18 to integrate Calendly availability checking via MCP server for Letta | AI_Agent |
| 2025-11-11 15:30:00 | 20 | create_pbi | Added PBI 20 to provide dedicated Slack analytics export MCP service and decouple from Calendly server | AI_Agent |
| 2025-11-16 02:12:30 | 20 | approve | PBI 20 completed; service deployed, tools updated, and operations doc added | User |
| 2025-11-18 10:00:00 | 21 | create_pbi | Added PBI 21 to build scheduling orchestration tool with DSPy and clingo ASP for intelligent meeting proposal generation | AI_Agent |
| 2025-01-21 12:00:00 | 22 | create_pbi | Added PBI 22 to extend scheduling orchestrator with rescheduling support for existing meetings | AI_Agent |
| 2025-01-21 13:00:00 | 22 | propose_for_backlog | PBI 22 moved from Proposed to Agreed - ready for implementation | AI_Agent |
| 2025-01-21 14:00:00 | 23 | create_pbi | Added PBI 23 to migrate Letta from v0.12.1 to v0.14.0 with SDK v1.0 compatibility and performance improvements | AI_Agent |
| 2025-01-21 15:00:00 | 24 | create_pbi | Added PBI 24 to create daily briefing tool that generates formatted schedule reports with available time calculations | AI_Agent |
| 2025-01-21 15:30:00 | 24 | propose_for_backlog | PBI 24 moved from Proposed to Agreed - ready for implementation | AI_Agent |
| 2025-01-21 20:00:00 | 25 | create_pbi | Added PBI 25 to create comprehensive Google Calendar CRUD tools for Letta agents with full event property support | AI_Agent |
| 2024-12-24 10:00:00 | 26 | create_pbi | Added PBI 26 to consolidate Drive analytics tools with user/owner/date filtering | AI_Agent |
| 2024-12-24 10:05:00 | 26 | propose_for_backlog | PBI 26 moved from Proposed to Agreed - ready for implementation | AI_Agent |
| 2026-01-01 10:00:00 | 27 | create_pbi | Added PBI 27 for Sports & Media Control Agent with Letta tools for ESPN, Roku, and FIOS IR control | AI_Agent |
| 2026-01-01 12:00:00 | 27 | approve | PBI 27 completed - all services and tools implemented | AI_Agent |
| 2026-01-03 06:30:00 | 28 | create_pbi | Added PBI 28 for Series Tracking Management System with status, progress overrides, and new season monitoring | AI_Agent |
| 2026-01-03 06:30:00 | 28 | start_implementation | PBI 28 moved to InProgress - beginning implementation | AI_Agent |
| 2026-01-03 08:00:00 | 28 | approve | PBI 28 completed - all 7 tasks done, 11 new tools registered | AI_Agent |
|| 2026-01-03 10:00:00 | 29 | create_pbi | Added PBI 29 for Auto-Madden Real-Time Game Companion with ESPN polling, insight generation, and adaptive delivery | AI_Agent |
|| 2026-01-03 10:00:00 | 29 | start_implementation | PBI 29 moved to InProgress - beginning implementation | AI_Agent |
| 2026-01-07 21:00:00 | 30 | create_pbi | Added PBI 30 for PA Web Interface and Routing Handler with intelligent agent routing | AI_Agent |
| 2026-01-08 02:30:00 | 30 | approve | PBI 30 completed - web interface deployed at pa.cd-ai-pa.work with routing and streaming | AI_Agent |
| 2026-01-08 02:30:00 | 31 | create_pbi | Added PBI 31 for Contextual Routing and Threaded Conversations follow-up | AI_Agent |
| 2026-01-08 09:05:00 | 31 | approve | PBI 31 completed - all 6 tasks done, threaded UI with concurrent requests and reply mode | AI_Agent |

## Backlog Notes

### Priority Rationale
The backlog is ordered to address foundational infrastructure changes first, followed by service integrations, and finally operational improvements. This sequence minimizes risk and ensures each phase builds upon stable foundations.

### Dependencies
- PBIs 1-2 are foundational and should be completed before other PBIs
- PBI 3 depends on completion of PBI 2 (network unification)
- PBI 4 depends on completion of PBIs 2-3 (network and MCP standardization)
- PBI 11 (version management) should be implemented early in Phase 2 for safety
- PBI 12 (upgrade infrastructure) depends on PBI 11 and builds upon unified infrastructure
- PBI 13 (RAG infrastructure) depends on PBIs 1-2 (database consolidation and networking)
- PBI 14 (RAG database integration) depends on PBI 13 and must be implemented together
- PBIs 5-6 can be worked on in parallel after core infrastructure (PBIs 1-4)
- PBIs 7-10 represent final validation and productionization phases

### Scope Boundaries
This backlog covers the unification and production-readiness of the existing PA ecosystem. It does not include:
- New AI agent capabilities beyond current functionality
- Additional MCP servers beyond those currently deployed  
- Advanced orchestration features (Kubernetes migration)
- Multi-node deployment capabilities
- Advanced RAG features (multi-modal search, real-time document updates, advanced analytics)
- Integration with external document management systems beyond basic ingestion

### Success Criteria
The backlog is considered complete when:
- All services operate within a single Docker Compose configuration
- System can be deployed with a single command on target home server
- All current PA functionality is preserved and validated
- RAG infrastructure is operational with document search capabilities
- Framework upgrade procedures are tested and documented
- Comprehensive backup, monitoring, and documentation are in place
- Performance meets or exceeds current system benchmarks

