"""Static schema registry mapping group.action keys to OmniFocus plugin method metadata."""

from __future__ import annotations

SCHEMAS: dict[str, dict] = {
    "task.create": {
        "method": "createTask",
        "description": "Create a new task in OmniFocus",
        "params": {
            "name": {"type": "string", "required": True, "description": "Task name"},
            "projectId": {"type": "string", "required": False, "description": "Project ID to assign the task to"},
            "note": {"type": "string", "required": False, "description": "Task note or description"},
            "flagged": {"type": "boolean", "required": False, "description": "Whether the task is flagged"},
            "dueDate": {"type": "string", "required": False, "description": "Due date (ISO 8601 string)"},
            "deferDate": {"type": "string", "required": False, "description": "Defer date (ISO 8601 string)"},
            "plannedDate": {"type": "string", "required": False, "description": "Planned date (ISO 8601 string)"},
            "estimatedMinutes": {"type": "integer", "required": False, "description": "Estimated duration in minutes"},
            "tagIds": {"type": "array[string]", "required": False, "description": "List of tag IDs to apply"},
        },
    },
    "task.get": {
        "method": "getTask",
        "description": "Get details of a specific task",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Task ID to retrieve"},
        },
    },
    "task.update": {
        "method": "updateTask",
        "description": "Update properties of an existing task",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Task ID to update"},
            "name": {"type": "string", "required": False, "description": "New task name"},
            "projectId": {"type": "string", "required": False, "description": "Project ID to move the task to"},
            "note": {"type": "string", "required": False, "description": "New task note or description"},
            "flagged": {"type": "boolean", "required": False, "description": "Whether the task is flagged"},
            "dueDate": {"type": "string", "required": False, "description": "New due date (ISO 8601 string)"},
            "deferDate": {"type": "string", "required": False, "description": "New defer date (ISO 8601 string)"},
            "plannedDate": {"type": "string", "required": False, "description": "New planned date (ISO 8601 string)"},
            "estimatedMinutes": {"type": "integer", "required": False, "description": "New estimated duration in minutes"},
            "tagIds": {"type": "array[string]", "required": False, "description": "New list of tag IDs to apply"},
        },
    },
    "task.complete": {
        "method": "completeTask",
        "description": "Mark a task as completed",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Task ID to complete"},
        },
    },
    "task.delete": {
        "method": "deleteTask",
        "description": "Delete a task",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Task ID to delete"},
        },
    },
    "task.move": {
        "method": "moveTask",
        "description": "Move a task to a different project or inbox",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Task ID to move"},
            "targetProjectId": {"type": "string", "required": False, "description": "Destination project ID (null for inbox)"},
            "parentTaskId": {"type": "string", "required": False, "description": "Make subtask of this task ID"},
            "position": {"type": "integer", "required": False, "description": "Position within target (0-indexed)"},
        },
    },
    "task.list": {
        "method": "queryTasks",
        "description": "List tasks with filters and pagination. Returns {status, data:{tasks:[]}, meta:{total, limit, offset, has_more}}.",
        "params": {
            "projectId": {"type": "string", "required": False, "description": "Filter by project ID"},
            "tagId": {"type": "string", "required": False, "description": "Filter by tag ID"},
            "flagged": {"type": "boolean", "required": False, "description": "Filter by flagged status"},
            "completed": {"type": "boolean", "required": False, "description": "Filter by completed status (true/false)"},
            "dropped": {"type": "boolean", "required": False, "description": "Filter by dropped status (true/false)"},
            "includeCompleted": {"type": "boolean", "required": False, "description": "Include completed tasks (legacy, prefer --completed)"},
            "hasEstimate": {"type": "boolean", "required": False, "description": "Filter by has duration estimate (true = has estimate, false = no estimate)"},
            "dueBefore": {"type": "string", "required": False, "description": "Tasks due before this date (ISO 8601)"},
            "dueAfter": {"type": "string", "required": False, "description": "Tasks due after this date (ISO 8601)"},
            "deferBefore": {"type": "string", "required": False, "description": "Tasks deferred before this date (ISO 8601)"},
            "deferAfter": {"type": "string", "required": False, "description": "Tasks deferred after this date (ISO 8601)"},
            "addedBefore": {"type": "string", "required": False, "description": "Tasks added before this date (ISO 8601)"},
            "addedAfter": {"type": "string", "required": False, "description": "Tasks added after this date (ISO 8601)"},
            "isOverdue": {"type": "boolean", "required": False, "description": "Filter to overdue tasks only"},
            "isAvailable": {"type": "boolean", "required": False, "description": "Filter to available (not blocked/deferred) tasks only"},
            "limit": {"type": "integer", "required": False, "description": "Max tasks to return (enables pagination)"},
            "offset": {"type": "integer", "required": False, "description": "Number of tasks to skip (use with limit)"},
        },
    },
    "task.count": {
        "method": "queryTasks",
        "description": "Count tasks matching filters. Fast — returns only {status, data:{count:N}}. Supports all the same filters as task.list.",
        "params": {
            "projectId": {"type": "string", "required": False, "description": "Filter by project ID"},
            "tagId": {"type": "string", "required": False, "description": "Filter by tag ID"},
            "flagged": {"type": "boolean", "required": False, "description": "Count only flagged tasks"},
            "completed": {"type": "boolean", "required": False, "description": "Filter by completed status"},
            "dropped": {"type": "boolean", "required": False, "description": "Filter by dropped status"},
            "hasEstimate": {"type": "boolean", "required": False, "description": "Filter by has duration estimate"},
            "dueBefore": {"type": "string", "required": False, "description": "Tasks due before this date (ISO 8601)"},
            "dueAfter": {"type": "string", "required": False, "description": "Tasks due after this date (ISO 8601)"},
            "addedBefore": {"type": "string", "required": False, "description": "Tasks added before this date (ISO 8601)"},
            "addedAfter": {"type": "string", "required": False, "description": "Tasks added after this date (ISO 8601)"},
            "isOverdue": {"type": "boolean", "required": False, "description": "Count only overdue tasks"},
            "isAvailable": {"type": "boolean", "required": False, "description": "Count only available tasks"},
        },
    },
    "task.subtasks": {
        "method": "getTaskSubtasks",
        "description": "Get subtasks of a task",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Parent task ID"},
        },
    },
    "task.add-subtask": {
        "method": "createSubtask",
        "description": "Create a subtask under a parent task",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Parent task ID"},
            "name": {"type": "string", "required": True, "description": "Subtask name"},
            "note": {"type": "string", "required": False, "description": "Subtask note"},
            "flagged": {"type": "boolean", "required": False, "description": "Whether the subtask is flagged"},
            "dueDate": {"type": "string", "required": False, "description": "Due date (ISO 8601)"},
            "deferDate": {"type": "string", "required": False, "description": "Defer date (ISO 8601)"},
            "estimatedMinutes": {"type": "integer", "required": False, "description": "Duration in minutes"},
            "tagIds": {"type": "array[string]", "required": False, "description": "Tag IDs to apply"},
        },
    },
    "task.hierarchy": {
        "method": "getTaskHierarchy",
        "description": "Get full task hierarchy tree",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Root task ID"},
        },
    },
    "task.flatten": {
        "method": "flattenTaskHierarchy",
        "description": "Flatten a task hierarchy (promote subtasks)",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Parent task ID to flatten"},
        },
    },
    "task.batch-status": {
        "method": "checkTaskCompletionStatus",
        "description": "Batch check completion/dropped status of multiple tasks",
        "params": {
            "taskIds": {"type": "array[string]", "required": True, "description": "List of OmniFocus task IDs to check"},
        },
    },
    "search": {
        "method": "searchTasks",
        "description": "Search tasks with advanced filters",
        "params": {
            "query": {"type": "string", "required": True, "description": "Search query string"},
            "scope": {"type": "string", "required": False, "description": "Search scope (e.g. project, folder)"},
            "scopeId": {"type": "string", "required": False, "description": "ID of the scope entity"},
            "tagId": {"type": "string", "required": False, "description": "Filter by tag ID"},
            "flagged": {"type": "boolean", "required": False, "description": "Filter by flagged status"},
            "isAvailable": {"type": "boolean", "required": False, "description": "Filter to available tasks only"},
            "dueBefore": {"type": "string", "required": False, "description": "Filter tasks due before this date"},
            "dueAfter": {"type": "string", "required": False, "description": "Filter tasks due after this date"},
            "deferBefore": {"type": "string", "required": False, "description": "Filter tasks deferred before this date"},
            "deferAfter": {"type": "string", "required": False, "description": "Filter tasks deferred after this date"},
            "isOverdue": {"type": "boolean", "required": False, "description": "Filter to overdue tasks only"},
            "maxResults": {"type": "integer", "required": False, "description": "Maximum number of results to return"},
        },
    },
    "project.list": {
        "method": "listProjects",
        "description": "List all projects with optional filters",
        "params": {
            "completion": {"type": "string", "required": False, "description": "Filter by completion status"},
            "folderId": {"type": "string", "required": False, "description": "Filter by folder ID"},
            "listByFolder": {"type": "boolean", "required": False, "description": "Group results by folder"},
        },
    },
    "project.get": {
        "method": "getProjectById",
        "description": "Get details of a specific project",
        "params": {
            "projectId": {"type": "string", "required": True, "description": "Project ID to retrieve"},
        },
    },
    "project.create": {
        "method": "createProject",
        "description": "Create a new project in OmniFocus",
        "params": {
            "name": {"type": "string", "required": True, "description": "Project name"},
            "folderId": {"type": "string", "required": False, "description": "Folder ID to create the project in"},
            "properties": {"type": "object", "required": False, "description": "Additional project properties"},
        },
    },
    "project.update": {
        "method": "setProjectProperties",
        "description": "Update properties of an existing project",
        "params": {
            "projectId": {"type": "string", "required": True, "description": "Project ID to update"},
            "properties": {"type": "object", "required": True, "description": "Properties to set on the project"},
        },
    },
    "project.complete": {
        "method": "completeProject",
        "description": "Mark a project as completed",
        "params": {
            "projectId": {"type": "string", "required": True, "description": "Project ID to complete"},
        },
    },
    "project.move": {
        "method": "moveProject",
        "description": "Move a project to a different folder",
        "params": {
            "projectId": {"type": "string", "required": True, "description": "Project ID to move"},
            "folderId": {"type": "string", "required": True, "description": "Destination folder ID"},
            "position": {"type": "integer", "required": False, "description": "Position within folder"},
        },
    },
    "project.convert": {
        "method": "convertTaskToProject",
        "description": "Convert a task into a project",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Task ID to convert"},
            "folderId": {"type": "string", "required": False, "description": "Folder to place new project"},
        },
    },
    "folder.list": {
        "method": "listFolders",
        "description": "List all folders",
        "params": {},
    },
    "folder.get": {
        "method": "getFolderById",
        "description": "Get details of a specific folder",
        "params": {
            "folderId": {"type": "string", "required": True, "description": "Folder ID to retrieve"},
        },
    },
    "folder.create": {
        "method": "createFolder",
        "description": "Create a new folder",
        "params": {
            "name": {"type": "string", "required": True, "description": "Folder name"},
            "parentFolderId": {"type": "string", "required": False, "description": "Parent folder ID for nesting"},
        },
    },
    "folder.delete": {
        "method": "deleteFolder",
        "description": "Delete a folder",
        "params": {
            "folderId": {"type": "string", "required": True, "description": "Folder ID to delete"},
        },
    },
    "folder.tree": {
        "method": "getFolderHierarchy",
        "description": "Get folder hierarchy tree",
        "params": {
            "folderId": {"type": "string", "required": False, "description": "Root folder ID (omit for entire library)"},
        },
    },
    "inbox.list": {
        "method": "listInbox",
        "description": "List items in the OmniFocus inbox",
        "params": {
            "limit": {"type": "integer", "required": False, "description": "Maximum number of items to return"},
            "includeCompleted": {"type": "boolean", "required": False, "description": "Include completed items"},
        },
    },
    "inbox.process": {
        "method": "processInboxItem",
        "description": "Process an inbox item by assigning project, tags, and dates",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Inbox task ID to process"},
            "projectId": {"type": "string", "required": False, "description": "Project ID to assign"},
            "tagIds": {"type": "array[string]", "required": False, "description": "Tag IDs to apply"},
            "flagged": {"type": "boolean", "required": False, "description": "Whether to flag the task"},
            "dueDate": {"type": "string", "required": False, "description": "Due date (ISO 8601 string)"},
            "deferDate": {"type": "string", "required": False, "description": "Defer date (ISO 8601 string)"},
        },
    },
    "inbox.context": {
        "method": "getInboxProcessingContext",
        "description": "Get context for processing an inbox item (available projects, tags)",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Inbox item ID"},
        },
    },
    "inbox.bulk": {
        "method": "executeBulkInboxProcessing",
        "description": "Process multiple inbox items at once",
        "params": {
            "operations": {"type": "array[object]", "required": True, "description": "Array of {taskId, projectId, action} objects"},
            "validateFirst": {"type": "boolean", "required": False, "description": "Validate before executing"},
            "continueOnError": {"type": "boolean", "required": False, "description": "Continue if an operation fails"},
        },
    },
    "tags.list": {
        "method": "listTags",
        "description": "List all tags",
        "params": {},
    },
    "tags.get": {
        "method": "getTagById",
        "description": "Get details of a specific tag",
        "params": {
            "tagId": {"type": "string", "required": True, "description": "Tag ID to retrieve"},
        },
    },
    "tags.create": {
        "method": "createTag",
        "description": "Create a new tag",
        "params": {
            "name": {"type": "string", "required": True, "description": "Tag name"},
            "parentTagId": {"type": "string", "required": False, "description": "Parent tag ID for nesting"},
        },
    },
    "tags.rename": {
        "method": "updateTag",
        "description": "Rename an existing tag",
        "params": {
            "tagId": {"type": "string", "required": True, "description": "Tag ID to rename"},
            "name": {"type": "string", "required": True, "description": "New tag name"},
        },
    },
    "tags.delete": {
        "method": "deleteTag",
        "description": "Delete a tag",
        "params": {
            "tagId": {"type": "string", "required": True, "description": "Tag ID to delete"},
            "force": {"type": "boolean", "required": False, "description": "Force deletion even if tag is in use"},
        },
    },
    "perspective.list": {
        "method": "listPerspectives",
        "description": "List all perspectives",
        "params": {
            "includeBuiltIn": {"type": "boolean", "required": False, "description": "Include built-in perspectives"},
        },
    },
    "perspective.get": {
        "method": "getPerspective",
        "description": "Get perspective details",
        "params": {
            "perspectiveId": {"type": "string", "required": True, "description": "Perspective ID"},
        },
    },
    "perspective.switch": {
        "method": "switchToPerspective",
        "description": "Switch OmniFocus to a perspective view",
        "params": {
            "perspectiveId": {"type": "string", "required": False, "description": "Perspective ID"},
            "perspectiveName": {"type": "string", "required": False, "description": "Perspective name (alternative to ID)"},
        },
    },
    "review.list": {
        "method": "listProjectsNeedingReview",
        "description": "List projects needing review",
        "params": {},
    },
    "review.mark": {
        "method": "markProjectReviewed",
        "description": "Mark a project as reviewed",
        "params": {
            "projectId": {"type": "string", "required": True, "description": "Project ID to mark reviewed"},
        },
    },
    "review.next": {
        "method": "getProjectNextReview",
        "description": "Get next review date for a project",
        "params": {
            "projectId": {"type": "string", "required": True, "description": "Project ID"},
        },
    },
    "analytics.health": {
        "method": "getProjectHealth",
        "description": "Get project health metrics",
        "params": {},
    },
    "analytics.workload": {
        "method": "getWorkloadSummary",
        "description": "Get workload summary",
        "params": {},
    },
    "analytics.trends": {
        "method": "getTrendInsights",
        "description": "Get trend insights",
        "params": {},
    },
    "analytics.summary": {
        "method": "getAnalyticsSummary",
        "description": "Get analytics summary",
        "params": {},
    },
    "system.health": {
        "method": "health",
        "description": "Check OmniFocus plugin health status",
        "params": {},
    },
    "task.get-group-type": {
        "method": "getTaskGroupType",
        "description": "Get the group type of a task",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Task ID"},
        },
    },
    "task.set-group-type": {
        "method": "setTaskGroupType",
        "description": "Set the group type of a task",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Task ID"},
            "groupType": {"type": "string", "required": True, "description": "Group type: sequential or parallel"},
        },
    },
    "project.get-group-type": {
        "method": "getProjectGroupType",
        "description": "Get the group type of a project",
        "params": {
            "projectId": {"type": "string", "required": True, "description": "Project ID"},
        },
    },
    "project.set-group-type": {
        "method": "setProjectGroupType",
        "description": "Set the group type of a project",
        "params": {
            "projectId": {"type": "string", "required": True, "description": "Project ID"},
            "groupType": {"type": "string", "required": True, "description": "Group type: sequential or parallel"},
        },
    },
    "validate.transaction": {
        "method": "validateTransaction",
        "description": "Validate a transaction before executing",
        "params": {
            "operations": {"type": "array[object]", "required": True, "description": "Operations to validate"},
        },
    },
    "validate.move": {
        "method": "validateMove",
        "description": "Validate a move operation",
        "params": {
            "taskId": {"type": "string", "required": True, "description": "Task ID to move"},
            "targetProjectId": {"type": "string", "required": False, "description": "Target project ID"},
            "parentTaskId": {"type": "string", "required": False, "description": "Target parent task ID"},
        },
    },
    "validate.create": {
        "method": "validateCreate",
        "description": "Validate a create operation",
        "params": {
            "name": {"type": "string", "required": True, "description": "Item name"},
        },
    },
    "automation.suggest": {
        "method": "suggestAutomation",
        "description": "Get automation suggestions",
        "params": {},
    },
    "automation.diagnose": {
        "method": "diagnoseIssues",
        "description": "Diagnose common issues",
        "params": {},
    },
    "automation.cleanup": {
        "method": "suggestCleanup",
        "description": "Get cleanup suggestions",
        "params": {},
    },
    "transaction.begin": {
        "method": "beginTransaction",
        "description": "Begin a new transaction",
        "params": {},
    },
    "transaction.execute": {
        "method": "executeTransactional",
        "description": "Execute operations within a transaction",
        "params": {
            "operations": {"type": "array[object]", "required": True, "description": "Operations to execute"},
        },
    },
    "transaction.accept": {
        "method": "acceptTransaction",
        "description": "Accept and commit a transaction",
        "params": {
            "transactionId": {"type": "string", "required": True, "description": "Transaction ID to accept"},
        },
    },
    "transaction.rollback": {
        "method": "rollbackTransaction",
        "description": "Rollback a transaction",
        "params": {
            "transactionId": {"type": "string", "required": True, "description": "Transaction ID to rollback"},
        },
    },
    "transaction.history": {
        "method": "getTransactionHistory",
        "description": "Get transaction history",
        "params": {},
    },
}


def get_schema(key: str) -> dict | None:
    """Return the schema for a given group.action key, or None if not found."""
    return SCHEMAS.get(key)


def list_schemas() -> list[str]:
    """Return a sorted list of all registered schema keys."""
    return sorted(SCHEMAS.keys())
