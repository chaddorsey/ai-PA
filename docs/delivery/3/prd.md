# PBI-3: Organizational Structure Access

[View in Backlog](../backlog.md#user-content-3)

## ✅ **COMPLETED**

**Status**: Done (7 of 12 tasks completed, 3 set aside, 2 deferred)

**Key Achievements**:
- ✅ **Comprehensive Perspective Reading**: Deep binary plist parsing with filter rule interpretation
- ✅ **Enhanced Inbox Processing**: Bulk operations with workflow management
- ✅ **Complete Project Hierarchy**: Full tree navigation and path analysis  
- ✅ **Group Type Management**: Parallel/sequential control for projects and tasks
- ✅ **Completion Behavior Control**: "Complete with last action" configuration
- ✅ **MCP Server Integration**: All tools properly registered with validation

**Strategic Decisions**:
- **Deferred 3-2, 3-8**: Advanced perspective analytics deemed overkill for core use cases
- **Set Aside 3-10, 3-11, 3-12**: Intelligence features and testing deferred to future iterations
- **Focus on Fundamentals**: Prioritized solid organizational access over advanced features

## Overview

This PBI provides complete visibility into OmniFocus organizational systems, enabling AI assistants to understand and navigate user perspectives, inbox workflows, and complex project hierarchies. Building on the query and mutation capabilities from PBI-1 and PBI-2, this adds organizational intelligence that makes AI interactions context-aware and workflow-optimized.

## Problem Statement

OmniFocus users organize their work through perspectives, inbox processing, and project hierarchies, but AI assistants cannot see or understand these organizational structures. This leads to context-unaware task management where AI cannot suggest relevant actions based on user's current perspective or workflow state. The existing bridge provides basic project listing but lacks the sophisticated organizational awareness needed for intelligent task management assistance.

## User Stories

### Primary User Story
As an organization user, I want to access OmniFocus perspectives, inbox, and project hierarchies through AI so that I can understand and navigate my complete organizational system.

### Supporting User Stories
- As a GTD practitioner, I want AI to understand my inbox and help me process items conversationally
- As a project manager, I want AI to navigate complex project hierarchies and suggest relevant actions
- As a perspective user, I want AI to understand my custom views and provide context-aware suggestions
- As a perspective creator, I want to create and modify custom perspectives through AI conversation
- As a workflow optimizer, I want AI to analyze my organizational patterns and suggest improvements
- As a busy professional, I want AI to help me focus on the right work based on my current perspective
- As a perspective manager, I want to duplicate and modify existing perspectives to create new views
- As a focus optimizer, I want AI to suggest optimal perspectives based on my current work context
- **As a project organizer**, I want to set and modify project group types (parallel vs sequential) through AI conversations so that I can control task completion workflows
- **As a completion-focused user**, I want to configure "complete with last action" behavior through AI conversations so that I can automate project completion patterns

## Technical Approach

### Architecture
Extend the bridge with advanced organizational intelligence:
1. **Advanced Perspective Management** - Full CRUD operations for custom perspectives (moved from PBI-2)
2. **Project Hierarchy Navigation** - Complete project tree traversal with nested task support
3. **Folder Management** - Complete folder operations and project organization
4. **Group Type Management** - Control parallel vs sequential task completion workflows
5. **Context-Aware Recommendations** - Organizational pattern analysis and suggestions

**Note**: Basic perspective operations (list, switch, view tasks) were completed in PBI-2. This PBI focuses on advanced perspective creation/modification and comprehensive project/folder management.

### Implementation Strategy
1. **Expand OmniFocus Plugin**: Add perspective and hierarchy methods to `omnifocus-mcp.omnijs`
2. **Enhance Bridge Intelligence**: Add organizational context processing in `bridge.ts`
3. **Update MCP Server**: Register organizational tools with rich metadata
4. **Add Workflow Intelligence**: Implement pattern recognition and suggestion algorithms

### API Design
```typescript
// Perspective management - Full CRUD
listPerspectives(): Perspective[]
getPerspective({ perspectiveId: string }): PerspectiveDetails
getActivePerspective(): PerspectiveDetails
createPerspective({
  name: string,
  taskFilter?: TaskFilter,
  grouping?: GroupingRule,
  sorting?: SortingRule,
  isBuiltIn?: boolean
}): Perspective
updatePerspective({
  perspectiveId: string,
  fields: {
    name?: string,
    taskFilter?: TaskFilter,
    grouping?: GroupingRule,
    sorting?: SortingRule
  }
}): Perspective
deletePerspective({ perspectiveId: string }): boolean
duplicatePerspective({ perspectiveId: string, newName: string }): Perspective
setActivePerspective({ perspectiveId: string }): boolean

// Inbox operations
listInbox(): InboxItem[]
processInboxItem({ 
  taskId: string, 
  action: 'organize' | 'defer' | 'delete',
  targetProjectId?: string,
  targetDate?: string
})
bulkProcessInbox({ 
  items: Array<{taskId: string, action: ProcessAction}> 
})

// Project hierarchy
getProjectHierarchy({ projectId?: string }): ProjectTree
getProjectTree(): CompleteProjectTree  
getProjectPath({ projectId: string }): ProjectPath[]

// Project group type management
getProjectGroupType({ projectId: string }): GroupType // 'parallel' | 'sequential'
setProjectGroupType({ 
  projectId: string, 
  groupType: 'parallel' | 'sequential' 
}): boolean
getProjectCompletionBehavior({ projectId: string }): CompletionBehavior
setProjectCompletionBehavior({ 
  projectId: string, 
  completeWithLastAction: boolean 
}): boolean

// Task group type management (for parent tasks with subtasks)
getTaskGroupType({ taskId: string }): GroupType // 'parallel' | 'sequential'  
setTaskGroupType({ 
  taskId: string, 
  groupType: 'parallel' | 'sequential' 
}): boolean
```

## UX/UI Considerations

### Conversational Intelligence
- **Context Awareness**: AI understands current perspective and suggests relevant actions
- **Workflow Integration**: AI can guide users through inbox processing workflows
- **Hierarchy Navigation**: AI can navigate complex project structures conversationally
- **Pattern Recognition**: AI identifies organizational patterns and suggests optimizations

### Organizational UX
- **Perspective Switching**: AI can switch between perspectives based on user intent
- **Inbox Guidance**: AI provides structured inbox processing guidance
- **Project Navigation**: AI helps users find and navigate to relevant projects
- **Organizational Insights**: AI provides insights into organizational patterns and health

## Acceptance Criteria

### Functional Requirements
1. **Perspective Management Works**:
   - List all user perspectives including custom ones
   - Access perspective details and task filters
   - Create new perspectives with custom filtering and grouping rules
   - Update existing perspective properties and filters
   - Delete custom perspectives (with protection for built-in ones)
   - Duplicate perspectives to create variations
   - Switch active perspective programmatically

2. **Inbox Processing Works**:
   - List all inbox items with full metadata
   - Process inbox items with organize/defer/delete actions
   - Support bulk inbox processing operations

3. **Project Hierarchy Works**:
   - Navigate complete project tree structures
   - Access nested project relationships
   - Understand project context and dependencies

4. **Project Group Type Management Works**:
   - Read and modify project group types (parallel vs sequential)
   - Configure "complete with last action" behavior for projects
   - Handle task group types for parent tasks with subtasks
   - Validate group type changes preserve existing task relationships

5. **Performance Standards**:
   - Organizational queries complete within 1s
   - Inbox processing scales with item count
   - Project hierarchy navigation remains responsive

### Non-Functional Requirements
1. **Organizational Intelligence**: AI understands user's organizational patterns
2. **Context Preservation**: Organizational context is maintained across conversations
3. **Workflow Integration**: Operations integrate smoothly with existing OmniFocus workflows
4. **Pattern Recognition**: System identifies and suggests organizational improvements

## Dependencies

### Internal Dependencies
- PBI-1 (Enhanced Query Operations) - required for organizational data access
- PBI-2 (Task Mutation Operations) - required for inbox processing
- Existing MCP bridge infrastructure

### External Dependencies
- OmniFocus perspective API access
- OmniFocus inbox system integration
- OmniFocus project hierarchy APIs

### Data Dependencies
- OmniFocus perspective definitions
- OmniFocus inbox task collection
- OmniFocus project tree structure

## Open Questions

1. **Perspective Customization**: Should AI be able to create or modify user perspectives?
2. **Inbox Intelligence**: How sophisticated should AI inbox processing suggestions be?
3. **Hierarchy Limits**: What's the maximum depth of project hierarchy we should support?
4. **Context Memory**: How long should AI remember organizational context between conversations?
5. **Permission Boundaries**: What organizational changes should require explicit user confirmation?

## Related Tasks

Task implementation will be defined in `tasks.md` once this PBI is approved. The task breakdown will include:

- Perspective access implementation
- Inbox processing workflow development
- Project hierarchy navigation system
- Context-aware recommendation engine
- Organizational pattern analysis
- Integration testing with PBI-1 and PBI-2
- User workflow validation
- Performance optimization 