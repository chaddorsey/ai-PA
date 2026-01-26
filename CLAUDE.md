# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **AI Personal Assistant (PA) ecosystem** running on a home server infrastructure. The system integrates multiple services including:
- **Letta** - AI agent framework with memory and tool execution
- **n8n** - Workflow automation platform
- **Supabase** - PostgreSQL database with REST API, Auth, and Studio
- **MCP Servers** - Model Context Protocol servers for various integrations (Gmail, Slack, calendar, OmniFocus, etc.)
- **Slackbot** - Slack integration for AI assistant access
- **Scheduler Service** - Dedicated scheduling and reminder service with semantic search
- **Sports & Media Tools** - ESPN API integration, Roku TV control, Flipper Zero IR control
- **Auto-Madden** - Real-time NFL game companion with insights engine

All services run containerized via Docker Compose on a unified `pa-internal` network.

## Development Commands

### Docker Services

```bash
# Start all services
docker-compose up -d

# Start specific service(s)
docker-compose up -d letta scheduler-service slackbot

# View service logs
docker-compose logs -f <service-name>

# Rebuild specific service after code changes
docker-compose up -d --build <service-name>

# Stop all services
docker-compose down

# Stop and remove volumes (destructive)
docker-compose down -v
```

### Python Services (Poetry-based)

Most Python services use Poetry for dependency management. Common services: `scheduler-service`, `scheduler-mcp`, `slackbot`.

```bash
# Install dependencies
poetry install

# Run development server (scheduler-service example)
poetry run uvicorn scheduler_service.main:app --reload

# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov

# Add dependency
poetry add <package-name>

# Format/lint code
poetry run ruff check .
poetry run ruff format .
```

### Node.js Services (npm-based)

MCP servers often use Node.js. Common services: `gmail-mcp`, `rag-mcp`, `omnifocus-mcp-letta`.

```bash
# Install dependencies
npm install

# Build TypeScript services
npm run build

# Run in development mode (if available)
npm run dev
```

### Letta Integration

Letta scripts are in the `/letta` directory and handle agent configuration, tool attachment, and MCP server setup.

```bash
# Configure MCP servers for Letta
python letta/configure_mcp_servers.py

# Attach tools to agents
python letta/attach_scheduling_tool_to_agent.py
python letta/attach_slack_analytics_to_agent.py
```

### Health Checks

```bash
# Check all MCP servers
./scripts/health-check-all.sh

# Validate MCP protocol compliance
./scripts/validate-mcp-protocol.sh

# Validate Letta-MCP connection
./scripts/validate-letta-mcp-connection.sh
```

### Backup and Recovery

```bash
# Comprehensive system backup (preferred - more complete)
./deployment/scripts/backup.sh --verbose

# Backup to specific location
./deployment/scripts/backup.sh --output /Volumes/main-filestore/ai-PA-backups

# Dry run to see what would be backed up
./deployment/scripts/backup.sh --dry-run

# Legacy backup script
./scripts/comprehensive_backup.sh

# Emergency recovery
./scripts/system-recovery.sh
```

**Automated Backups:** Daily at 2am via cron (`deployment/scripts/backup-wrapper.sh`)

**Backup Location:** `/Volumes/main-filestore/ai-PA-backups/`

**What's Backed Up:**
- All PostgreSQL databases (pg_dumpall + individual dumps)
- Docker volumes (n8n, neo4j, open-webui, etc.)
- Host data (Auto-Madden DBs, credentials, Letta filesystem)
- Letta agent exports and memory blocks (via API)
- n8n workflow exports
- Configuration files (.env, docker-compose.yml)
- Git reference (commit hash for recovery)

## Architecture

### Service Communication

- **Internal Network**: All services communicate via `pa-internal` Docker network using service names (DNS-based discovery)
- **External Access**: Cloudflare tunnels provide secure remote access
- **No Hardcoded IPs**: Always use service names in configurations (e.g., `http://scheduler-service:8000`)

### Database Architecture

- **Primary DB**: Supabase PostgreSQL (`supabase-db`) on port 5432 (internal)
- **Supabase REST**: PostgREST API on port 8000
- **Supabase Studio**: Web UI on port 3000
- **Supabase Auth**: GoTrue authentication service on port 9999
- **Schema Isolation**: Different services use separate schemas/databases within the same PostgreSQL instance

### MCP Server Pattern

MCP servers expose tools to Letta agents via the Model Context Protocol. They typically:
1. Run as FastAPI services with stdio transport for MCP
2. Are configured in Letta via `configure_mcp_servers.py`
3. Expose health check endpoints
4. Follow naming pattern: `<purpose>-mcp-server`

Key MCP servers:
- `gmail-mcp-server` - Gmail API integration
- `scheduler-mcp` - Scheduling service tools
- `slack-analytics-mcp-server` - Slack analytics exports
- `graphiti-mcp-server` - Knowledge graph integration
- `omnifocus-mcp-server` - OmniFocus task management

### Sports & Media Architecture

The sports-and-media-tools subsystem provides end-to-end control:
- `sports-service` (port 5123) - ESPN API with caching
- `flipper-api` (port 5124) - IR commands via Flipper Zero over USB
- Roku TV control via ECP protocol (192.168.7.187)
- Integration with Letta for voice-controlled sports watching

### Auto-Madden Architecture

Real-time NFL game companion with three microservices:
- `auto-madden-game-state` (port 5132) - ESPN API polling every 3 seconds, change detection
- `auto-madden-insight-engine` (port 5131) - LLM-based insights (Claude/GPT-4), WebSocket delivery, Q&A
- `auto-madden-companion-ui` (port 5130) - Flask web interface with live/replay modes

### Service Entry Points

Key entry point files for each service:

| Service | Entry Point | Framework |
|---------|-------------|-----------|
| scheduler-service | `src/scheduler_service/main.py` | FastAPI |
| slackbot | `app.py` | Slack Bolt |
| auto-madden-game-state | `game_state_service.py` | Flask |
| auto-madden-insight-engine | `insight_engine.py` | Flask + WebSocket |
| auto-madden-companion-ui | `app.py` | Flask |
| sports-service | `sports_api.py` | Flask |
| flipper-api | `flipper_api.py` | Flask |
| gmail-mcp | `src/index.ts` | Node.js MCP |
| omnifocus-mcp-letta | `server-mcp-simplified.ts` | Node.js MCP |
| scheduler-mcp | `src/scheduler_mcp/server.py` | FastAPI MCP |
| pa-routing-handler | `src/pa_routing/main.py` | FastAPI |

### Letta MCP Configuration

MCP servers are registered in `/letta/letta_mcp_config.json`. All use HTTP transport:

| MCP Server | Endpoint | Purpose |
|------------|----------|---------|
| gmail-tools | `http://gmail-mcp-server:8080/mcp` | Gmail API (OAuth) |
| slack-tools | `http://localhost:3001/sse` | Slack integration |
| graphiti-tools | `http://graphiti-mcp-server:8000/mcp` | Knowledge graph (Neo4j) |
| rag-tools | `http://rag-mcp-server:8082/mcp` | Vector database |
| calendly-tools | `http://calendly-mcp-server:8086/mcp` | Availability checking |
| scheduler-tools | `http://scheduler-mcp:8088/mcp` | Job scheduling |
| omnifocus-tools | `http://host.docker.internal:8888/mcp` | Task management (AppleScript bridge) |

### Database Schemas

PostgreSQL databases/schemas in Supabase:
- `scheduler_service` - Jobs and executions for scheduler
- `letta` - Agent memory and vector embeddings
- `n8n` / `n8n_restore` - Workflow automation data
- `postgres` (public) - Shared data

Neo4j (port 7474/7687):
- Graphiti knowledge graph for semantic memory

## Project Management (Critical)

This project follows **strict task-based development** defined in `.cursorrules`. Key principles:

### Fundamental Rules

1. **NO CODE CHANGES WITHOUT A TASK**: All changes must be associated with an agreed-upon task
2. **Tasks Link to PBIs**: All tasks must be associated with a Product Backlog Item (PBI)
3. **User Authority**: User is the sole decider for scope and design
4. **No Scope Creep**: Changes outside explicit task scope are prohibited
5. **DRY Principle**: Information defined once, referenced elsewhere

### Workflow

1. **Check backlog**: `docs/delivery/backlog.md` contains all PBIs
2. **Review PBI details**: `docs/delivery/<PBI-ID>/prd.md`
3. **Check tasks**: `docs/delivery/<PBI-ID>/tasks.md`
4. **Task details**: `docs/delivery/<PBI-ID>/<PBI-ID>-<TASK-ID>.md`

### Task Status Synchronization

When updating task status, **ALWAYS update both**:
1. The individual task file (`docs/delivery/<PBI-ID>/<PBI-ID>-<TASK-ID>.md`)
2. The tasks index (`docs/delivery/<PBI-ID>/tasks.md`)

### Commit Message Format

```bash
<task_id> <task_description>

# Example:
6-3 Add health check endpoint to scheduler service
```

### Before Making Changes

1. Identify the associated PBI and task
2. If no task exists, discuss with user whether to create one
3. Never make "improvements" outside the task scope
4. Document all changes in the task file

### Plan and Task File Tracking

When using superpowers skills (brainstorming, writing-plans, executing-plans) to create implementation plans:

1. **Write task files to Git-tracked locations**: Save plans to `docs/plans/YYYY-MM-DD-<feature-name>-tasks.md`
2. **Never leave plans only in `~/.claude/plans/`**: This directory is outside the repo and not tracked in Git
3. **Commit plan files immediately**: After creating or modifying a plan file, add and commit it:
   ```bash
   git add docs/plans/<plan-file>.md
   git commit -m "docs: add/update <feature> implementation plan"
   ```
4. **Design documents go alongside task files**: Save design docs to `docs/plans/YYYY-MM-DD-<feature-name>-design.md`
5. **Keep both synchronized**: If the plan changes during execution, update the tracked file

**Plan File Naming Convention:**
- Design documents: `docs/plans/YYYY-MM-DD-<feature>-design.md`
- Implementation tasks: `docs/plans/YYYY-MM-DD-<feature>-tasks.md`
- Implementation plans: `docs/plans/YYYY-MM-DD-<feature>-impl.md`

## Testing Strategy

### Test Distribution

- **Unit Tests**: Focus on individual functions/classes in isolation (`src/test/`)
- **Integration Tests**: Verify multi-component interactions (`test/integration/`)
- **E2E Tests**: Critical user paths via Playwright (`playwright/`)

### Test Plans

- Test plans must be proportional to task complexity
- Simple tasks (constants, interfaces): Basic compilation checks
- Complex tasks: Detailed scenarios with edge cases
- Dedicated "E2E CoS Test" task for PBI-level validation

### Running Tests

```bash
# Python services
poetry run pytest                    # Run all tests
poetry run pytest tests/test_foo.py  # Run specific test
poetry run pytest -v                 # Verbose output
poetry run pytest --cov             # With coverage

# Slackbot
pytest .

# Scheduler service
cd scheduler-service && poetry run pytest
```

### Test Requirements

- Tasks cannot be marked "Done" unless tests pass
- Integration tests should use real instances of internal infrastructure (DB, queues)
- Mock only external third-party services at application boundary

## Configuration Management

### Environment Variables

Environment variables are defined in `.env` (gitignored). Key categories:

**Database:**
- `POSTGRES_PASSWORD` - Supabase DB password
- `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY` - API keys
- `SCHEDULER_DB_URL` - Scheduler service connection

**AI/LLM APIs:**
- `OPENAI_API_KEY` - OpenAI API
- `ANTHROPIC_API_KEY` - Claude API
- `GEMINI_API_KEY` - Google Gemini

**Slack Integration:**
- `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` - Slack credentials
- `SLACK_MCP_XOXP_TOKEN` - MCP server token
- `LETTA_AGENT_ID` - Default agent for Slack

**Scheduler:**
- `SCHEDULER_API_KEY` - API authentication
- `LETTA_CALLBACK_URL` - Agent callback URL

**Sports & Media:**
- `SD_USERNAME`, `SD_PASSWORD` - Schedules Direct

**Auto-Madden:**
- `LLM_PROVIDER`, `LLM_MODEL` - Insight generation config

**n8n:**
- `N8N_ENCRYPTION_KEY` - Workflow encryption
- `WEBHOOK_URL` - External webhook base

### Secrets Management

- **Never commit secrets** to git
- All secrets via environment variables
- No hardcoded credentials in code
- Credentials stored in `.env` or service-specific credential files (gitignored)

## Service Ports Reference

### Core Services
| Service | Internal Port | External Port | Purpose |
|---------|---------------|---------------|---------|
| supabase-db | 5432 | - | PostgreSQL database |
| supabase-rest | 3000 | 8000 | PostgREST API |
| supabase-auth | 9999 | 9999 | Authentication |
| supabase-studio | 3000 | 3000 | Web UI |
| n8n | 5678 | 5678 | Workflow automation |
| letta | 8283 | 8283 | Agent server |
| neo4j | 7474/7687 | 7474/7687 | Graph database |

### MCP Servers
| Service | Port | Purpose |
|---------|------|---------|
| gmail-mcp-server | 8084 | Gmail API integration |
| omnifocus-mcp-server | 8888 | OmniFocus (AppleScript bridge) |
| scheduler-mcp | 8088 | Scheduling tools |
| slack-mcp-server | 3001 | Slack integration |
| graphiti-mcp-server | 8082 | Knowledge graph tools |
| rag-mcp-server | 8085 | RAG vector tools |
| calendly-mcp-server | 8086 | Calendly availability |
| slack-analytics-mcp-server | 8097 | Slack analytics export |

### Application Services
| Service | Port | Purpose |
|---------|------|---------|
| scheduler-service | 8001 | Scheduling API |
| slackbot | 8081/8083 | Slack bot (health/main) |
| pa-routing-handler | 5201 | Agent conversation routing |
| pa-web-ui | 5200 | Web interface |
| open-webui | 8080 | Chat UI for Letta |

### Sports & Media
| Service | Port | Purpose |
|---------|------|---------|
| sports-service | 5123 | ESPN API |
| flipper-api | 5124 | IR control |
| schedules-direct-service | 5125 | TV listings |
| content-database | 5126 | JustWatch content |
| watch-history-service | 5127 | Roku history |

### Auto-Madden
| Service | Port | Purpose |
|---------|------|---------|
| auto-madden-companion-ui | 5130 | Web interface |
| auto-madden-insight-engine | 5131 | LLM insights |
| auto-madden-game-state | 5132 | ESPN polling |

## Key Implementation Patterns

### Adding a New MCP Server

1. Create service directory with FastAPI app
2. Implement MCP protocol with stdio transport
3. Add health check endpoint
4. Add service to `docker-compose.yml` on `pa-internal` network
5. Register in `letta/configure_mcp_servers.py`
6. Create corresponding task in appropriate PBI

### Database Migrations

For scheduler-service (uses Alembic):
```bash
cd scheduler-service
poetry run alembic revision --autogenerate -m "description"
poetry run alembic upgrade head
```

### Logging

Services use structured logging (structlog for Python). Include:
- Service name
- Request ID
- User context
- Clear error messages

### Constants for Repeated Values

Per `.cursorrules` principle #12, any value used more than once must be defined as a named constant:
```python
# BAD
for i in range(10):
    ...

# GOOD
NUM_WEBSITES = 10
for i in range(NUM_WEBSITES):
    ...
```

## Troubleshooting

### Service Won't Start

1. Check logs: `docker-compose logs <service-name>`
2. Verify dependencies are healthy: `docker-compose ps`
3. Check environment variables in `.env`
4. Verify network connectivity: `docker network inspect pa-internal`

### Database Connection Issues

1. Ensure `supabase-db` is healthy: `docker-compose ps supabase-db`
2. Check connection string uses service name, not localhost
3. Verify schema/database exists
4. Check credentials in `.env`

### MCP Server Not Responding

1. Check health endpoint: `curl http://localhost:<port>/health`
2. Verify Letta configuration: check `letta/configure_mcp_servers.py`
3. Check logs for both Letta and MCP server
4. Validate MCP protocol: `./scripts/validate-mcp-protocol.sh`

## Version Management

The project maintains a version lock file (`config/versions/version-lock.yml`) for framework stability:
- n8n, Letta, Graphiti versions are locked
- Upgrade procedures documented in `docs/upgrades/`
- Rollback scripts available in `scripts/rollback/`
- See PBI-11 for version management strategy

## External Package Research

Per `.cursorrules` principle #9: When proposing tasks involving external packages:
1. Research documentation via web to avoid hallucinations
2. Create `<task-id>-<package>-guide.md` with fresh API cache
3. Include date stamp and link to original docs
4. Store in task directory: `docs/delivery/<PBI-ID>/<task-id>-<package>-guide.md`

## Network and Security

- All internal communication over `pa-internal` network (172.20.0.0/16)
- External access via Cloudflare tunnels (managed by `cloudflare-tunnel` service)
- TLS/SSL for external communications
- Network segmentation between services
- No services directly exposed to internet except via tunnel

## Key Files Reference

Understanding these files helps navigate the codebase:

**Configuration:**
- `docker-compose.yml` - Complete service orchestration (25+ services)
- `.env` - Environment variables (gitignored)
- `letta/letta_mcp_config.json` - MCP server registration

**Scheduler Service:**
- `scheduler-service/src/scheduler_service/main.py` - App factory
- `scheduler-service/src/scheduler_service/services/scheduler.py` - Job execution
- `scheduler-service/src/scheduler_service/services/schedule_parser.py` - NLP parsing

**Slackbot:**
- `slackbot/app.py` - Main entry, Slack Bolt setup
- `slackbot/listeners/listeners.py` - Event handler registration
- `slackbot/listeners/messages/message_im_hybrid.py` - DM handling
- `slackbot/manifest.json` - Slack app configuration

**Auto-Madden:**
- `auto-madden/game-state-service/game_state_service.py` - ESPN polling
- `auto-madden/insight-engine/insight_engine.py` - LLM insight generation (~190KB)
- `auto-madden/companion-ui/app.py` - Flask web UI

**Letta Integration:**
- `letta/configure_mcp_servers.py` - Register MCP servers with Letta
- `letta/attach_*.py` - Tool attachment scripts
- `letta/register_*.py` - Tool registration

**Sports & Media:**
- `sports-and-media-tools/sports-service/sports_api.py` - ESPN API client
- `sports-and-media-tools/flipper-api/flipper_api.py` - IR commands

## Letta Agents

The system has ~20 Letta agents. Key agent management:

```bash
# List all agents
curl http://localhost:8283/v1/agents

# Export agent for backup
curl http://localhost:8283/v1/agents/{agent_id}/export

# Get agent memory blocks
curl http://localhost:8283/v1/blocks
```

Agents are configured via the Letta API and have MCP tools attached for:
- Gmail operations
- OmniFocus task management
- Scheduling (create/manage reminders)
- Slack messaging
- Knowledge graph queries (Graphiti)
- RAG document retrieval

## macOS Considerations

When running on macOS, metadata files (`.DS_Store`, `._*` files) can cause issues:

```bash
# Clean macOS metadata from a directory (e.g., before Letta restart)
find ./letta -name "._*" -type f -delete
find ./letta -name ".DS_Store" -type f -delete
```

The `letta/env` directory is a sandbox venv that Letta creates. If Letta gets stuck in a restart loop, try removing it:

```bash
docker-compose stop letta
rm -rf ./letta/env
docker-compose up -d letta
```
