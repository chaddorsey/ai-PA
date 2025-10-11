# PBI-19: Dedicated Scheduling & Reminder Service

## Overview
The personal assistant ecosystem needs a durable, queryable scheduling capability that survives container restarts, integrates tightly with Letta, and supports both conversational reminders and automation workflows. PBI-19 delivers a dedicated Python-based scheduling service running in its own Docker container. The service persists job definitions, execution history, metadata, and embeddings in the shared PostgreSQL instance (with pgvector) so Letta agents can search and reason over reminders and automation logs. It exposes a REST API and an MCP tool for Letta to create, manage, and query schedules while supporting external actions such as web downloads or script execution. Observability, catch-up handling, and documentation ensure long-term reliability.

[View in Backlog](../backlog.md#user-content-19)

## Problem Statement
Cron jobs tied to individual containers are fragile in a Dockerized environment. When containers restart, scheduled tasks can be lost, duplicated, or desynchronized. Letta requires authoritative access to upcoming and past reminders, along with automation hooks for external data ingestion. Without a centralized scheduler that persists its state and exposes proper interfaces, the assistant cannot reliably orchestrate time-based tasks or review history for RAG use cases.

## User Stories
- As a platform architect, I need a dedicated scheduling service that persists across container lifecycles so that time-based automations remain reliable.
- As a Letta agent, I must create, update, and cancel reminders programmatically so that I can manage user prompts and workflows.
- As an automation engineer, I need to trigger external actions (webhooks, scripts) on schedules and log outcomes so that downstream systems receive timely data.
- As a knowledge analyst, I want searchable historical records of reminders and automations so that I can surface patterns and context during conversations.

## Technical Approach
- **Stack**: Python 3.12, FastAPI for REST API, APScheduler for job execution, SQLAlchemy ORM with pgvector extension, sentence-transformers for embeddings, Docker containerized deployment.
- **Persistence**: Jobs, triggers, executions, actions, payload metadata, and embeddings stored in shared PostgreSQL; migrations managed via Alembic.
- **Scheduling**: APScheduler with database-backed job store to rehydrate state on restart, catch-up logic for missed runs, idempotency guards.
- **Interfaces**:
  - REST API for CRUD operations, immediate triggers, search, and archive export.
  - MCP tool exposing commands (e.g., `schedule_reminder`, `list_jobs`, `search_archive`, `update_job`, `cancel_job`, `trigger_now`, `register_external_action`).
- **Embeddings**: Local embedding service integrated; textual content, metadata snapshots, and execution summaries vectorized for semantic search.
- **External Actions**: Allow-listed HTTP/webhook and script execution; results captured and stored for Letta ingestion.
- **Security**: Internal network exposure within Docker Compose; optional API key for REST endpoints; logging includes contextual metadata without sensitive payloads.
- **Documentation**: API spec, MCP usage guide, Compose integration instructions, schema diagrams, operational runbook.

## UX/UI Considerations
- No human-facing UI in scope; focus on clear API schemas, OpenAPI documentation, and MCP command descriptions.
- Provide CLI or `curl` examples in documentation for manual operations.
- Error messages crafted for Letta agents with actionable suggestions and validation feedback.

## Acceptance Criteria
- Service runs as a dedicated Docker container with healthcheck and Compose integration, connecting to shared PostgreSQL.
- REST API and MCP tool enable Letta to create, manage, and search schedules/reminders.
- Job definitions, executions, metadata, and embeddings persist in PostgreSQL/pgvector with migration scripts.
- External action execution framework supports HTTP/webhook calls and allow-listed scripts with result logging.
- Observability includes structured logging, retry/catch-up behavior, and optional metrics endpoint.
- Documentation covers setup, API, MCP integration, embeddings, and security posture.
- E2E test plan validates creation → execution → archive search workflows for Letta and external actions.

## Dependencies
- Shared PostgreSQL instance with pgvector extension enabled.
- Docker Compose networking (`pa-internal`) for service communication.
- Access to Letta container for MCP integration and callback endpoints.
- Sentence-transformer model available locally or via existing embedding service.

## Open Questions
- Which sentence-transformer model is preferred for embeddings (size vs. accuracy trade-off)?
- Should initial authentication be API key–based or deferred to network-level controls?
- What allow-list policy governs script execution locations and environment variables?
- Are there existing observability stacks (Prometheus/Fluent Bit) to integrate with immediately?

## Related Tasks
- [Back to task list](./tasks.md)
- Tasks tracked in `docs/delivery/19/tasks.md` with detailed files:
  - 19-1 Architecture & Schema Design
  - 19-2 Core Service MVP
  - 19-3 MCP Tool Integration & Documentation
  - 19-4 External Action Pipelines
  - 19-5 Observability & Resilience
  - 19-6 E2E CoS Test


