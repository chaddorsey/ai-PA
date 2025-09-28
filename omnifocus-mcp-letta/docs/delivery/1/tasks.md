# Tasks for PBI 1: Complete Core CRUD and Enhanced Queries

This document lists all tasks associated with PBI 1.

**Parent PBI**: [PBI 1: Complete Core CRUD and Enhanced Queries](./prd.md)

## Task Summary

| Task ID | Name                                     | Status   | Description                        |
| :------ | :--------------------------------------- | :------- | :--------------------------------- |
| 1-1     | [Implement and register listTasksByTag end-to-end](./1-1.md) | Done | Complete tag-based filtering from plugin through MCP server |
| 1-2     | [Add duration editing to updateTask](./1-2.md) | Done | Add estimated duration field to updateTask operations |
| 1-3     | [Implement queryTasks multi-dimensional filtering](./1-3.md) | Done | Add queryTasks with date, duration, and status filtering |
| 1-4     | [Register queryTasks MCP tool](./1-4.md) | Done | Register queryTasks tool in server with comprehensive schema |
| 1-5     | [Implement listTasksByContext alias](./1-5.md) | Rejected | Add context alias for tag filtering (OmniFocus 4 compatibility) |
| 1-6     | [Register createTask MCP tool](./1-6.md) | Done | Register existing createTask plugin method as MCP tool |
| 1-7     | [Register updateTask MCP tool](./1-7.md) | Done | Register existing updateTask plugin method as MCP tool |
| 1-8     | [Register completeTask MCP tool](./1-8.md) | Done | Register existing completeTask plugin method as MCP tool |
| 1-9     | [Implement and register deleteTask](./1-9.md) | Done | Implement deleteTask in plugin and register as MCP tool |
| 1-10    | [Add query performance optimization](./1-10.md) | Done | Implement performance optimization for query operations |
| 1-11    | [Implement comprehensive error handling](./1-11.md) | Done | Add robust error handling throughout query operations |
| 1-12    | [E2E foundation operations testing](./1-12.md) | Done | Comprehensive testing of all new operations through Claude |
| 1-13    | [Implement and register searchTasks](./1-13.md) | Done | Full-text search with fuzzy matching for task discovery |
| 1-14    | [Add exclusion filters to queryTasks and searchTasks](./1-14.md) | Done | Implement excludeProjectIds, excludeTagIds, excludeFolderIds parameters |
| 1-15    | [Register enhanced exclusion filters in MCP server](./1-15.md) | Done | Update server schemas with exclusion filter parameters and validation |
| 1-16    | [Implement boolean tag logic for advanced filtering](./1-16.md) | Done | Add requireAllTags, requireAnyTags, excludeAllTags for complex tag operations |
| 1-17    | [Enhance searchTasks with queryTasks filter integration](./1-17.md) | Done | Add date, duration, and status filters to searchTasks for unified querying |
| 1-18    | [Implement universalQuery unified method](./1-18.md) | Done | Create single method combining search and filtering with optimized performance |
| 1-19    | [Fix task projectID null issue using containingProject](./1-19.md) | Done | Replace t.project with t.containingProject in task serialization to fix null projectID issues |
| 1-20    | [Add advanced status and metadata filtering](./1-20.md) | Done | Implement hasEstimate, hasNotes, isOverdue, isDueToday filtering capabilities |
| 1-21    | [Fix searchTasks projectId filter bug](./1-21.md) | Done | Fix conditional logic in searchTasks to properly filter by projectId parameter |

## Enhancement Phases

### Phase 1: Exclusion Filters (Tasks 1-14, 1-15)
**Objective**: Enable negative filtering to eliminate multi-step query operations
**Impact**: High - Converts 2-step queries into single API calls
**Example**: Find "DSE" tasks not in "Priorities" project becomes a single `searchTasks` call

### Phase 2: Boolean Tag Logic (Task 1-16)  
**Objective**: Support complex tag combinations with AND/OR/NOT logic
**Impact**: Medium - Enables sophisticated tag-based workflow filtering
**Example**: Find work tasks that are urgent OR high-priority, but NOT meetings

### Phase 3: Enhanced Search Integration (Task 1-17)
**Objective**: Merge search and filtering capabilities into unified tools  
**Impact**: Medium - Eliminates need to choose between search vs. filtering
**Example**: Search "budget" + flagged + due this week in single call

### Phase 4: Universal Query Builder (Task 1-18)
**Objective**: Single method for all query operations with optimization
**Impact**: High - Replaces multiple methods, optimized for conversational AI
**Example**: One method handles search + filters + exclusions + logic

### Phase 5: Advanced Status & Performance (Tasks 1-19, 1-20)  
**Objective**: Complete comprehensive query system with intelligence
**Impact**: Medium - Adds metadata filtering and conversational optimizations
**Example**: Find tasks with estimates that are overdue, with smart suggestions 