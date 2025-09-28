# PBI-4: Hierarchy and Relationship Management

[View in Backlog](../backlog.md#user-content-4)

## Overview

This PBI enables sophisticated project and task organization through AI interaction, providing complete control over folder structures, project hierarchies, and task relationships. Building on the foundation of query, mutation, and organizational access capabilities, this transforms the bridge into a powerful organizational restructuring tool that can handle complex hierarchy modifications through natural language conversations.

## Problem Statement

OmniFocus users frequently need to reorganize their work structures - moving projects between folders, creating subtasks, converting tasks to projects, and restructuring hierarchies. Currently, these operations require manual manipulation in the OmniFocus interface and cannot be performed through AI conversation. This creates friction when users want to reorganize their work based on AI-assisted analysis or when discussing project restructuring with an AI assistant.

## User Stories

### Primary User Story
As a project organizer, I want to manage folders, projects, and task relationships through AI so that I can restructure my work organization conversationally.

### Supporting User Stories
- As a project manager, I want to create new folders and move projects between them based on AI analysis
- As a task organizer, I want to convert tasks into projects and create subtask hierarchies conversationally
- As a workflow optimizer, I want to restructure entire project hierarchies based on AI recommendations
- As a busy professional, I want to delegate organizational tasks to AI that understand my work patterns
- As a strategic thinker, I want to experiment with different organizational structures through AI conversation

## Technical Approach

### Architecture
Extend the bridge with comprehensive hierarchy management:
1. **Folder Operations** - Create, move, and organize folder structures
2. **Project Management** - Create projects, move between folders, apply templates
3. **Task Relationship Management** - Create subtasks, move tasks, convert tasks to projects
4. **Hierarchy Integrity** - Maintain relationships and dependencies during restructuring

### Implementation Strategy
1. **Enhance OmniFocus Plugin**: Add hierarchy manipulation methods to `omnifocus-mcp.omnijs`
2. **Extend Bridge Layer**: Add transaction support for complex hierarchy operations
3. **Update MCP Server**: Register hierarchy management tools with validation
4. **Add Integrity Checking**: Implement relationship validation and dependency tracking

### API Design
```typescript
// Folder operations
createFolder({ 
  name: string, 
  parentFolderId?: string,
  position?: number 
})
moveProject({ 
  projectId: string, 
  folderId: string,
  position?: number 
})
deleteFolder({ 
  folderId: string, 
  moveProjectsTo?: string 
})

// Project management
createProject({ 
  name: string, 
  folderId?: string,
  templateId?: string,
  position?: number 
})
convertTaskToProject({ 
  taskId: string, 
  folderId?: string,
  preserveSubtasks?: boolean 
})

// Task relationship management
moveTask({ 
  taskId: string, 
  targetProjectId?: string,
  parentTaskId?: string,
  position?: number 
})
createSubtask({ 
  parentTaskId: string,
  name: string,
  // ... other task properties
})
restructureHierarchy({
  operations: Array<HierarchyOperation>
})
```

## UX/UI Considerations

### Conversational Hierarchy Management
- **Natural Language Restructuring**: Support commands like "Move all marketing projects to the new Q1 folder"
- **Relationship Preservation**: Maintain task relationships during hierarchy changes
- **Undo Support**: Provide rollback for complex hierarchy operations
- **Confirmation Patterns**: Confirm major restructuring operations before execution

### Organizational Intelligence
- **Dependency Awareness**: Understand and preserve task/project dependencies
- **Pattern Recognition**: Suggest organizational improvements based on usage patterns
- **Template Application**: Apply project templates conversationally
- **Integrity Validation**: Prevent operations that would break organizational integrity

## Acceptance Criteria

### Functional Requirements
1. **Folder Operations Work**:
   - Create nested folder structures
   - Move projects between folders
   - Delete folders with proper project handling

2. **Project Management Works**:
   - Create projects with folder assignment
   - Convert tasks to projects with subtask preservation
   - Apply project templates correctly

3. **Task Relationships Work**:
   - Move tasks between projects
   - Create and manage subtask hierarchies
   - Maintain parent/child relationships during moves

4. **Hierarchy Integrity**:
   - Prevent circular dependencies
   - Maintain referential integrity
   - Validate all hierarchy operations

### Non-Functional Requirements
1. **Data Integrity**: All hierarchy operations maintain database consistency
2. **Performance**: Complex restructuring operations complete within 5s
3. **Rollback Capability**: Major hierarchy changes can be undone
4. **Validation**: All operations validated before execution

## Dependencies

### Internal Dependencies
- PBI-1 (Enhanced Query Operations) - required for hierarchy validation
- PBI-2 (Task Mutation Operations) - required for task manipulation
- PBI-3 (Organizational Structure Access) - required for organizational context
- Existing MCP bridge infrastructure

### External Dependencies
- OmniFocus folder management APIs
- OmniFocus project hierarchy APIs
- OmniFocus task relationship APIs

### Data Dependencies
- OmniFocus folder tree structure
- OmniFocus project containment relationships
- OmniFocus task parent/child relationships

## Open Questions

1. **Operation Atomicity**: Should complex hierarchy operations be atomic transactions?
2. **Template System**: How sophisticated should project templates be?
3. **Circular Dependency Prevention**: What safeguards prevent circular hierarchies?
4. **Performance Limits**: What's the maximum complexity of hierarchy operations we should support?
5. **Collaboration Impact**: How do hierarchy changes affect shared or collaborative projects?

## Related Tasks

Task implementation will be defined in `tasks.md` once this PBI is approved. The task breakdown will include:

- Folder creation and management implementation
- Project movement and conversion system
- Task relationship management
- Hierarchy integrity validation
- Transaction support for complex operations
- Template system development
- Performance optimization
- Integration testing with previous PBIs
- User acceptance testing for complex workflows 