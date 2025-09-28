# Product Backlog

This document contains all Product Backlog Items (PBIs) for the OmniFocus MCP Bridge project, ordered by priority.

## Current Status Overview

**✅ Already Working Through Claude Desktop:**
- **Complete Task CRUD** (except delete): Create, read, update, and complete tasks via 8 MCP tools
- **Rich Task Creation**: Projects, tags, dates, notes, flagged status fully supported  
- **Comprehensive Updates**: Change any task field including project reassignment
- **Project & Tag Management**: Full visibility into organizational structure
- **Proven Architecture**: Bridge successfully handles complex operations with OmniFocus

**📋 Missing Core Capabilities:** ~~Task deletion, advanced filtering, search, inbox operations, perspective management~~ ✅ **ALL CORE CAPABILITIES COMPLETE**

**🚀 Next Phase:** Template automation and external integrations (PBIs 5-6)

## Product Backlog Items

| ID | Actor | User Story | Status | Conditions of Satisfaction (CoS) |
|----|-------|------------|--------|-----------------------------------|
| 1 | Task Manager | As a task manager, I want to delete tasks, edit estimated duration, and perform advanced queries through AI conversations so that I can complete all basic task management operations with sophisticated filtering capabilities. | Done | 1. AI can delete tasks safely with confirmation, 2. AI can edit task estimated duration with validation, 3. AI can filter tasks by tags with optional project scoping, 4. AI can perform multi-dimensional queries (dates, duration, status), 5. AI can search task names and notes with fuzzy matching, 6. All operations maintain data integrity |
| 2 | Project Organizer | As a project organizer, I want to manage my inbox and access all my perspectives through AI conversations so that I can process tasks efficiently and leverage my custom organizational systems. | Done | 1. AI can list and process inbox items individually and in bulk, 2. AI can access and manage all user perspectives with full CRUD operations, 3. AI can navigate complex project hierarchies with performance optimization, 4. Inbox processing workflows are fully conversational |
| 3 | Power User | As a power user, I want to restructure my project hierarchy, manage task relationships, and control project group types through AI conversations so that I can organize complex projects and completion workflows without manual interface navigation. | Done | 1. AI can create and manage folder structures with nesting, 2. AI can move projects between folders and apply templates, 3. AI can move tasks between projects while maintaining relationships, 4. AI can convert tasks to projects and create subtasks programmatically, 5. AI can set project group types (parallel vs sequential) and completion behaviors, 6. Complex hierarchy changes preserve data integrity |
| 4 | Project Organizer | As a project organizer, I want to manage folders, projects, and task relationships through AI conversations so that I can restructure my work organization conversationally with complete hierarchy management capabilities. | Done | 1. AI can create nested folder structures and move projects between folders, 2. AI can create projects with folder assignment and convert tasks to projects, 3. AI can move tasks between projects and create subtask hierarchies, 4. AI can prevent circular dependencies and maintain hierarchy integrity, 5. Complex restructuring operations complete with transaction support and rollback capabilities |
| 5 | Workflow Automator | As a workflow automator, I want to create templates and automate task management workflows through AI conversations so that I can reduce repetitive work and get proactive optimization suggestions. | Proposed | 1. AI can create and apply project templates with parameters, 2. AI can set up automated workflows with triggers and actions, 3. AI can provide smart suggestions for task optimization, 4. Templates significantly reduce setup time, 5. Automation suggestions improve productivity |  
| 6 | Integration User | As an integration user, I want to use the bridge with multiple MCP clients and connect external services so that I can access OmniFocus from different AI interfaces and sync with other productivity tools. | Proposed | 1. Bridge works seamlessly with multiple MCP clients, 2. External service integrations maintain data consistency, 3. Calendar sync works bidirectionally, 4. Performance scales with multiple connections, 5. Protocol compliance enables broad compatibility |
| 10 | OmniFocus Integrator | As an OmniFocus integrator, I want MCP responses to include creation and modification timestamps so that agents can reason about item freshness and history. | Proposed | Plugin exposes added/modified timestamps for tasks, projects, folders, tags, and perspectives; MCP responses return ISO timestamps; Documentation updated with usage guidance |

## PBI History

| Timestamp | PBI_ID | Event_Type | Details | User |
|-----------|--------|------------|---------|------|
| 2025-01-15 14:30:00 | 1 | Created | Initial PBI created after analyzing actual current state - focus on missing delete and advanced queries | AI Agent |
| 2025-01-15 14:30:00 | 1 | Status_Change | Moved to Agreed - reflects current priority for completing core CRUD operations | AI Agent |
| 2025-01-15 14:30:00 | 2-6 | Created | Created remaining PBIs focusing on missing capabilities rather than exposing existing ones | AI Agent |
| 2025-01-16 20:40:00 | 2 | Status_Change | Moved to Done - completed all organizational management capabilities with optimizations | AI Agent |
| 2025-01-16 16:40:00 | 1 | Status_Change | Moved to Done - completed all core CRUD operations, advanced queries, search, and universalQuery with 21 total tasks | AI Agent |
| 2025-01-16 17:00:00 | 3 | Status_Change | Moved to Agreed - comprehensive 12-task breakdown created for organizational structure access capabilities | AI Agent |
| 2025-01-31 17:45:00 | 4 | Status_Change | Moved to Done - completed all hierarchy and relationship management with 11 tasks. Tasks 4-12, 4-13, 4-14 set aside as redundant/overengineered for use case | AI Agent |
| 2025-01-16 20:15:00 | 3 | Status_Change | Moved to Done - completed organizational structure access with comprehensive perspective reading, project hierarchy, group type management. Tasks 3-2, 3-8 deferred as overkill | AI Agent |
| 2025-09-28 22:20:00 | 10 | Created | Added PBI 10 for exposing OmniFocus timestamps through MCP integration | AI Agent |

**Links to PBI Details:**
- [PBI-1: Complete Core CRUD and Enhanced Queries](./1/prd.md)
- [PBI-2: Inbox and Organizational Management](./2/prd.md)
- [PBI-3: Hierarchy and Advanced Organization](./3/prd.md)
- [PBI-4: Hierarchy and Relationship Management](./4/prd.md)
- [PBI-5: Workflow Automation and Intelligence](./5/prd.md)
- [PBI-6: External Integration and Multi-Client Support](./6/prd.md) 