# PBI-1: Complete Core CRUD and Enhanced Queries

## Overview

Complete the foundational task management capabilities by implementing the missing `deleteTask` operation and adding enhanced query capabilities that enable sophisticated task filtering and search through AI conversations.

**Current Status**: 🔄 **EXTENDED** - Core CRUD operations and basic enhanced queries are complete. Now extending with comprehensive query capabilities including exclusion filters, hierarchical operations, boolean tag logic, and universal query builder for maximum conversational AI efficiency.

## Problem Statement

While users can already create, update, and complete tasks through Claude conversations, two critical gaps remain:

1. **Missing Delete Operation**: Users cannot delete tasks through AI conversations - the only CRUD operation not implemented
2. **Limited Query Capabilities**: Only basic listing operations exist (by project, all remaining tasks) - no advanced filtering by tags, dates, duration, or complex criteria
3. **No Advanced Search**: Cannot search task content or perform sophisticated filtering operations

These limitations prevent users from having complete task management control and sophisticated task discovery through conversational AI.

## User Stories

### Primary User Stories
- **As a task manager**, I want to delete tasks through AI conversations so that I can manage the complete task lifecycle without switching to OmniFocus
- **As a task organizer**, I want to filter tasks by tags through AI conversations so that I can find context-specific tasks quickly
- **As a productivity optimizer**, I want to query tasks by date ranges and duration through AI conversations so that I can plan and analyze my work effectively
- **As a knowledge worker**, I want to search task content through AI conversations so that I can find specific tasks without remembering exact names
- **As a time manager**, I want to edit task estimated duration through AI conversations so that I can manage my time allocation without switching applications

### Supporting User Stories
- **As a careful user**, I want task deletion to be safe with confirmation so that I don't accidentally lose important tasks
- **As a project manager**, I want to combine filtering criteria (tags + projects + dates) so that I can find specific task subsets
- **As a busy professional**, I want search to be forgiving with typos so that I can find tasks even with approximate queries
- **As a planning user**, I want duration updates to be validated so that I can maintain accurate time estimates

## Technical Approach

### Architecture Overview
- **OmniFocus Plugin Extension**: Add `deleteTask` method and enhanced query methods to existing plugin
- **Server Tool Registration**: Register new MCP tools with proper Zod schemas for type safety
- **Bridge Layer**: No changes needed - existing `callOmniFocus` interface handles all operations

### Implementation Strategy

**Phase 1: Core Delete Operation**
1. Implement `deleteTask` method in OmniFocus plugin with safety checks
2. Register `deleteTask` MCP tool in server with proper validation
3. Add confirmation prompts for safety

**Phase 2: Enhanced Query Operations**
1. Implement tag-based filtering methods in plugin
2. Implement multi-dimensional query methods with date/duration filtering
3. Register all query tools in server with comprehensive schemas

**Phase 3: Advanced Search**
1. Implement full-text search capabilities in plugin
2. Add fuzzy matching and scoped search options
3. Optimize search performance for large task sets

### Key Technical Decisions
- **Safety First**: Delete operations include confirmation and optional force flags
- **Performance Optimization**: Query operations designed for < 500ms response times
- **Comprehensive Filtering**: Support for combining multiple filter criteria
- **Search Flexibility**: Both exact and fuzzy matching options

## UX/UI Considerations

### Conversational Patterns
- **Delete Confirmation**: "Are you sure you want to delete task 'Review proposal'? This cannot be undone."
- **Query Precision**: "Found 12 tasks tagged 'urgent' due this week in project 'Website Launch'"
- **Search Results**: "Found 3 tasks matching 'budget review': [list with relevance scores]"

### Error Handling
- **Safe Failures**: Delete operations fail safely with clear error messages
- **Query Feedback**: Clear indication when queries return no results vs. system errors
- **Search Guidance**: Helpful suggestions when searches return no results

### Performance Expectations
- **Immediate Response**: All operations feel instantaneous to users
- **Progress Indication**: Long-running searches show progress
- **Graceful Degradation**: Fallback to simpler queries if complex ones fail

## Acceptance Criteria

### Core Delete Operation
1. **Delete Task Implementation**: `deleteTask` method successfully removes tasks from OmniFocus
2. **Safety Confirmation**: Deletion requires confirmation to prevent accidents
3. **Error Handling**: Attempts to delete non-existent tasks fail gracefully
4. **Force Delete Option**: Optional force flag for programmatic deletion

### Enhanced Task Updates
1. **Duration Editing**: `updateTask` includes estimated duration field for time management
2. **Duration Validation**: Duration values are validated (positive numbers, reasonable ranges)
3. **Duration Preservation**: Existing durations are preserved when not explicitly updated
4. **Duration Integration**: Duration updates work seamlessly with other task field updates

### Enhanced Query Operations  
1. **Tag-Based Filtering**: `listTasksByTag` filters tasks by specified tags
2. **Multi-Dimensional Queries**: `queryTasks` combines date, duration, and status filters
3. **Project Scoping**: Tag queries can be scoped to specific projects
4. **Completed Task Control**: All queries support including/excluding completed tasks

### Advanced Search Capabilities
1. **Full-Text Search**: `searchTasks` searches task names and note content
2. **Fuzzy Matching**: Search tolerates typos and partial matches
3. **Scoped Search**: Search can be limited to specific projects or tags
4. **Performance**: All search operations complete within 2 seconds

### Data Integrity
1. **Atomic Operations**: All operations are atomic (complete or fail entirely)
2. **No Data Loss**: Failed operations never result in partial data corruption
3. **Consistent State**: OmniFocus database remains consistent after all operations
4. **Rollback Capability**: Failed multi-step operations can be rolled back

### Conversational Integration
1. **Natural Language Queries**: AI can interpret complex natural language requests
2. **Contextual Responses**: Results include relevant context and metadata
3. **Error Communication**: Errors are communicated clearly to both AI and users
4. **Query Optimization**: Common query patterns are optimized for performance

## Dependencies

### Technical Dependencies
- **Existing MCP Tools**: All current 8 MCP tools must continue working
- **OmniFocus Plugin**: Current plugin methods must remain functional
- **Bridge Architecture**: Generic bridge interface must be preserved

### Functional Dependencies
- **OmniFocus Access**: Plugin must have full read/write access to OmniFocus database
- **AppleScript Bridge**: Bridge must handle complex query operations efficiently
- **Claude Integration**: MCP tools must be compatible with Claude Desktop

### Performance Dependencies
- **Response Times**: Query operations must complete within performance requirements
- **Memory Usage**: Enhanced queries cannot significantly increase memory usage
- **OmniFocus Performance**: Operations cannot degrade OmniFocus UI performance

## Open Questions

### Technical Questions
1. **Delete Safety**: What level of confirmation is appropriate for different delete scenarios?
2. **Query Optimization**: How should we handle queries that could return thousands of results?
3. **Search Indexing**: Should we implement search indexing for performance, or rely on OmniFocus's built-in search?
4. **Error Recovery**: How should we handle partial failures in complex multi-step operations?

### User Experience Questions
1. **Confirmation UX**: How should delete confirmations work in conversational flow?
2. **Query Feedback**: What information should be included in query results to help users?
3. **Search Results**: How should search results be ranked and presented?
4. **Performance Expectations**: What response times do users expect for different operation types?

### Business Questions
1. **Feature Prioritization**: Which enhanced query features provide the most user value?
2. **Safety vs. Convenience**: How do we balance delete safety with user convenience?
3. **Search Scope**: Should search be limited to active tasks or include completed/archived tasks?

## Related Tasks

**Task Management**: [View task list for this PBI](./tasks.md)

**Key Implementation Tasks**:
- [1-1: Implement and register listTasksByTag end-to-end](./1-1.md) ✅ **Done**
- [1-2: Add duration editing to updateTask](./1-2.md) ✅ **Done**
- [1-3: Implement queryTasks multi-dimensional filtering](./1-3.md) ✅ **Done**
- [1-4: Register queryTasks MCP tool](./1-4.md) ✅ **Done**
- [1-5-1-8: Complete MCP tool registration suite](./1-6.md) ✅ **Done**
- [1-9: Implement and register deleteTask](./1-9.md) ✅ **Done**
- [1-10: Add query performance optimization](./1-10.md) ✅ **Done**
- [1-11: Implement comprehensive error handling](./1-11.md) ✅ **Done**
- [1-12: E2E foundation operations testing](./1-12.md) ✅ **Done**
- [1-13: Implement and register searchTasks](./1-13.md) ✅ **Done**

## Completion Summary

**PBI-1 Status**: ✅ **COMPLETE** (January 10, 2025)

**All Acceptance Criteria Met**:
- ✅ Core Delete Operation: `deleteTask` safely removes tasks with confirmation
- ✅ Enhanced Task Updates: Duration editing integrated into `updateTask`
- ✅ Enhanced Query Operations: Tag filtering and multi-dimensional queries working
- ✅ Advanced Search Capabilities: Full-text search with fuzzy matching implemented
- ✅ Data Integrity: All operations atomic with proper error handling
- ✅ Conversational Integration: Natural language queries work seamlessly through Claude

**Implemented Capabilities**:
- **Complete CRUD Operations**: Create, Read, Update, Delete all functional
- **Advanced Query Tools**: `listTasksByTag`, `queryTasks`, `searchTasks` with comprehensive filtering
- **Search & Discovery**: Full-text search with fuzzy matching and scoped searching
- **Performance Optimization**: Multi-level caching with smart TTL configuration
- **Robust Error Handling**: Comprehensive validation and graceful failure modes

**Technical Achievements**:
- 13 MCP tools registered for complete task management
- Sophisticated search algorithm with relevance scoring  
- Performance caching system with selective invalidation
- Comprehensive parameter validation and error messaging
- End-to-end testing validated through real Claude Desktop usage

The OmniFocus MCP Bridge now provides complete conversational task management capabilities, enabling users to perform all task management operations through natural language conversations with AI.

## Enhanced Query Capabilities Extension

**Extension Goal**: Transform the solid foundation into a comprehensive query system that eliminates multi-step operations and client-side filtering, enabling complex queries to be accomplished in single API calls.

### Real-World Problem
Current query limitations require inefficient multi-step operations:
```
// Current: "Show me active tasks with 'DSE' but not in Priorities project"
1. searchTasks({ query: "DSE", active: true })
2. Client-side filtering to exclude project
```

### Enhanced Capabilities

#### 1. Exclusion Filters
**Objective**: Enable negative filtering to exclude specific entities from results

**New Parameters (queryTasks & searchTasks)**:
- `excludeProjectIds: string[]` - Exclude tasks from specific projects
- `excludeTagIds: string[]` - Exclude tasks with specific tags  
- `excludeFolderIds: string[]` - Exclude tasks from project folders

**Enhanced Query Example**:
```javascript
searchTasks({ 
  query: "DSE", 
  active: true,
  excludeProjectIds: ["priorities-project-id"]
});
```

#### 2. Enhanced Search + Query Integration
**Objective**: Merge the best capabilities of both methods - add all queryTasks filters to searchTasks

**Additional Parameters for searchTasks**:
- Date filters: `dueBefore`, `dueAfter`, `deferBefore`, `deferAfter`
- Duration filters: `minDuration`, `maxDuration`
- Status filters: `flagged`, `blocked`

**Use Case**: "Find tasks containing 'budget' that are flagged and due this week"
```javascript
searchTasks({
  query: "budget",
  flagged: true,
  dueAfter: "2024-01-01",
  dueBefore: "2024-01-07"
});
```

#### 3. Hierarchical Project Operations
**Objective**: Handle project tree operations elegantly

**New Parameters**:
- `excludeProjectHierarchy: string` - Exclude project and all its subprojects
- `includeProjectHierarchy: string` - Include project and all its subprojects
- `excludeProjectPath: string` - Exclude by project path (e.g., "Work/Archive/*")

**Use Case**: "Find tasks not in any archived projects"
```javascript
queryTasks({
  active: true,
  excludeProjectPath: "*/Archive/*"
});
```

#### 4. Boolean Tag Logic
**Objective**: Support complex tag combinations for sophisticated filtering

**Enhanced Parameters**:
- `requireAllTags: string[]` - Must have ALL these tags (AND logic)
- `requireAnyTags: string[]` - Must have AT LEAST ONE of these tags (OR logic)
- `excludeAllTags: string[]` - Must NOT have any of these tags (NOT logic)

**Use Case**: "Find work tasks that are either urgent or high-priority, but not in meetings"
```javascript
queryTasks({
  requireAnyTags: ["work"],
  requireAnyTags: ["urgent", "high-priority"],
  excludeAllTags: ["meetings"]
});
```

#### 5. Universal Query Builder
**Objective**: Create a unified method combining search and filtering

**New Method**: `universalQuery`
```javascript
universalQuery({
  search: "DSE",                    // Text search
  active: true,                     // Status filter
  excludeProjects: ["priorities"],  // Project exclusion
  requireAnyTags: ["work"],         // Tag requirements
  dueBefore: "2024-01-31",         // Date filtering
  flagged: true,                   // Additional filters
  maxResults: 50                   // Result limiting
});
```

#### 6. Advanced Status Combinations
**Objective**: Enable complex status-based filtering

**New Parameters**:
- `hasEstimate: boolean` - Filter tasks with/without time estimates
- `hasNotes: boolean` - Filter tasks with/without notes
- `hasAttachments: boolean` - Filter tasks with/without attachments
- `isOverdue: boolean` - Filter overdue tasks specifically
- `isDueToday: boolean` - Filter tasks due today
- `isDueSoon: boolean` - Filter tasks due within configurable timeframe

#### 7. Performance and Workflow Enhancements
**Objective**: Optimize for common conversational AI workflows

**Features**:
- **Smart Defaults**: Common parameter combinations pre-optimized
- **Query Hints**: Suggest alternative queries when no results found
- **Result Summarization**: Automatic categorization of large result sets
- **Query History**: Cache frequent query patterns for instant response

### Universal Workflow Patterns Enabled

#### Time-Based Exclusions
- "Due this week but not today" → `{ dueAfter: "today", dueBefore: "end-of-week" }`
- "Deferred but not to next month" → `{ deferDate: exists, deferBefore: "end-of-month" }`

#### Status Combinations
- "Flagged but not completed" → `{ flagged: true, completed: false }`
- "Has due date but not flagged" → `{ hasEstimate: true, flagged: false }`

#### Context-Aware Filtering
- "In work projects but not in archive folder" → `{ requireAnyTags: ["work"], excludeFolderIds: ["archive"] }`
- "Has energy tag but not blocked" → `{ requireAnyTags: ["energy"], blocked: false }`

#### Duration-Based Workflows
- "Quick tasks (under 15 min) but not in someday project" → `{ maxDuration: 15, excludeProjects: ["someday"] }`
- "Long tasks (over 1 hour) that are flagged" → `{ minDuration: 60, flagged: true }`

### Enhanced Acceptance Criteria

#### Exclusion Filtering
1. **Project Exclusion**: Can exclude single or multiple projects from any query
2. **Tag Exclusion**: Can exclude tasks with specific tags from results
3. **Folder Exclusion**: Can exclude entire folder hierarchies from queries
4. **Performance**: Exclusion filtering adds < 100ms to query time

#### Boolean Tag Logic
1. **AND Logic**: `requireAllTags` filters tasks having all specified tags
2. **OR Logic**: `requireAnyTags` filters tasks having any specified tags
3. **NOT Logic**: `excludeAllTags` removes tasks with any specified tags
4. **Combination**: All three logical operations can be used together

#### Hierarchical Operations
1. **Project Trees**: Can include/exclude entire project hierarchies
2. **Path Matching**: Can use wildcard patterns for project paths
3. **Nested Logic**: Hierarchical operations work with other filters
4. **Performance**: Tree operations complete within 1 second

#### Universal Query Builder
1. **Single Method**: `universalQuery` can replace multiple method calls
2. **Full Feature Set**: Supports all filtering and search capabilities
3. **Optimized**: Single method is faster than equivalent multi-method queries
4. **Backward Compatibility**: Existing methods continue to work unchanged

#### Advanced Status Filtering
1. **Metadata Filtering**: Can filter by presence/absence of estimates, notes, attachments
2. **Time Intelligence**: Smart date filtering with relative dates (today, this week, etc.)
3. **Status Combinations**: Complex status logic works reliably
4. **Error Handling**: Invalid status combinations provide helpful error messages

## Implementation Roadmap

### Phase 1: Exclusion Filters (High Impact)
- **Tasks**: 1-14, 1-15
- **Timeline**: 2-3 days
- **Value**: Eliminates most multi-step query operations

### Phase 2: Boolean Tag Logic (Medium Impact)
- **Tasks**: 1-16
- **Timeline**: 2-3 days  
- **Value**: Enables sophisticated tag-based filtering

### Phase 3: Enhanced Search Integration (Medium Impact)
- **Tasks**: 1-17
- **Timeline**: 1-2 days
- **Value**: Unifies search and filtering capabilities

### Phase 4: Universal Query Builder (High Impact)
- **Tasks**: 1-18
- **Timeline**: 3-4 days
- **Value**: Single method for all query operations

### Phase 5: Advanced Status & Performance (Low-Medium Impact)
- **Tasks**: 1-19, 1-20
- **Timeline**: 2-3 days
- **Value**: Completes the comprehensive query system

[View in Backlog](../backlog.md#user-content-1) 