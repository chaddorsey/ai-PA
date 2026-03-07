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
        "description": "List tasks with optional filters",
        "params": {
            "projectId": {"type": "string", "required": False, "description": "Filter by project ID"},
            "tagId": {"type": "string", "required": False, "description": "Filter by tag ID"},
            "flagged": {"type": "boolean", "required": False, "description": "Filter by flagged status"},
            "includeCompleted": {"type": "boolean", "required": False, "description": "Include completed tasks in results"},
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
    "folder.list": {
        "method": "listFolders",
        "description": "List all folders",
        "params": {},
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
    "tags.list": {
        "method": "listTags",
        "description": "List all tags",
        "params": {},
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
}


def get_schema(key: str) -> dict | None:
    """Return the schema for a given group.action key, or None if not found."""
    return SCHEMAS.get(key)


def list_schemas() -> list[str]:
    """Return a sorted list of all registered schema keys."""
    return sorted(SCHEMAS.keys())
