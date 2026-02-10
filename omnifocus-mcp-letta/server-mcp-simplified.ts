import express, { Request, Response } from "express";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  LoggingMessageNotification,
  Notification,
  InitializeRequestSchema,
  JSONRPCNotification,
  JSONRPCResponse,
} from "@modelcontextprotocol/sdk/types.js";
import { randomUUID } from "crypto";

import { callOmniFocus } from "./bridge.js";
import {
  detailLevelEnum,
  sortOrderEnum,
  DetailLevel,
  SortOrder,
  CompletionSuccess,
  CompletionResult,
} from "./schemas.js";

const SESSION_ID_HEADER_NAME = "mcp-session-id";
const JSON_RPC = "2.0";

const freshnessDescription =
  "Controls result ordering. Use 'freshness' to return newest/most recently modified items first.";

const detailLevelDescription =
  "Control response size: minimal (id, name, status, timestamps), standard (default - plus common metadata), full (include all fields such as notes or attachments).";

const quickToolSchemas = {
  markCompleted: {
    type: "object" as const,
    properties: {
      id: {
        type: "string",
        description: "Task or project UUID to mark complete",
      },
      scope: {
        type: "string",
        enum: ["task", "project"],
        description: "Scope of the identifier",
        default: "task",
      },
    },
    required: ["id", "scope"],
    additionalProperties: false,
  },
  listUncompletedTasks: {
    type: "object" as const,
    properties: {
      projectId: {
        type: "string",
        description: "Filter by project UUID",
        nullable: true,
      },
      folderId: {
        type: "string",
        description: "Filter by folder UUID - returns tasks from all projects in that folder",
        nullable: true,
      },
      includeSubfolders: {
        type: "boolean",
        description: "When using folderId, also include tasks from subfolders (default false)",
      },
      onlyFlagged: {
        type: "boolean",
        description: "Return only flagged tasks (default false)",
      },
      onlyAvailable: {
        type: "boolean",
        description:
          "Return only OmniFocus available tasks (not blocked/deferred). Default false; requires availability data from OmniFocus.",
      },
    },
    required: ["projectId", "folderId", "includeSubfolders", "onlyFlagged", "onlyAvailable"],
    additionalProperties: false,
  },
  listProjects: {
    type: "object" as const,
    properties: {
      folderId: {
        type: "string",
        description: "Filter to a specific folder UUID (null or omit for all).",
      },
      includeSubfolders: {
        type: "boolean",
        description: "When using folderId, also include projects from subfolders (default false).",
      },
      includeTasks: {
        type: "boolean",
        description: "Include task summaries for each project (default false, or true when detailLevel is full).",
      },
      listProjectNames: {
        type: "boolean",
        description:
          "If true, include task names alongside IDs (increases payload size).",
      },
      listByFolder: {
        type: "boolean",
        description:
          "If true, group results by folder with `projects` arrays per folder.",
      },
      completion: {
        type: "string",
        description:
          "Filter projects by completion state (`all`, `active`, `completed`, `dropped`).",
      },
      detailLevel: {
        type: "string",
        enum: detailLevelEnum.options,
        default: "standard",
        description: detailLevelDescription,
      },
      includeCounts: {
        type: "boolean",
        description: "Include task count summary (default true).",
      },
    },
    required: ["folderId", "includeSubfolders", "includeTasks", "listProjectNames", "listByFolder", "completion", "detailLevel", "includeCounts"],
    additionalProperties: false,
  },
  moveTaskToProject: {
    type: "object" as const,
    properties: {
      taskId: { type: "string", description: "Task UUID to move" },
      projectId: { type: "string", description: "Target project UUID" },
    },
    required: ["taskId", "projectId"],
    additionalProperties: false,
  },
  tasksHelp: {
    type: "object" as const,
    properties: {},
    required: [],
    description: "No parameters required.",
    additionalProperties: false,
  },
};

const HELP_MARKDOWN = `# OmniFocus Simplified MCP Quick Reference

## Getting Started
- Initialize:
  \`tools/list\` shows available commands after \`initialize\` (protocol 2024-11-05).
- Use \`mcp-session-id\` header from the \`initialize\` response for subsequent requests.

## Common Calls
- **Mark task or project complete**
  \`\`\`
  {"jsonrpc":"2.0","id":"markTask","method":"tools/call","params":{"name":"markCompleted","arguments":{"id":"TASK_UUID"}}}
  \`\`\`
  Use \`scope:"project"\` when completing a project.

- **List incomplete tasks**
  \`\`\`
  {"jsonrpc":"2.0","id":"tasks","method":"tools/call","params":{"name":"listUncompletedTasks","arguments":{"projectId":"PROJECT_UUID","onlyFlagged":false,"onlyAvailable":true}}}
  \`\`\`

- **List projects grouped by folder**
  \`\`\`
  {"jsonrpc":"2.0","id":"projects","method":"tools/call","params":{"name":"listProjects","arguments":{"detailLevel":"full","listByFolder":true,"completion":"active"}}}
  \`\`\`

## Tips
- \`detailLevel\` determines field richness (\`minimal\`, \`standard\`, \`full\`).
- \`completion\` accepts \`all\`, \`active\`, \`completed\`, \`dropped\`.
- Prefer \`listByFolder:true\` when presenting hierarchical summaries.
- Refer to project metadata docs for field descriptions.
`;

type CompletionScope = "task" | "project";

interface CompletionSuccessResponse {
  completedAt?: string;
  alreadyCompleted?: boolean;
  success?: boolean;
}

interface CompletionErrorResponse {
  error: string;
}

type CompletionBridgeResponse =
  | CompletionSuccessResponse
  | CompletionErrorResponse;

interface CompletionErrorEntry {
  id: string;
  scope: CompletionScope | "unknown";
  message: string;
}

async function performCompletion(
  id: string,
  scope: unknown,
): Promise<CompletionResult> {
  const completed: CompletionSuccess[] = [];
  const errors: CompletionErrorEntry[] = [];

  if (scope === "task") {
    const response = normalizeResult<CompletionBridgeResponse>(
      await callOmniFocus({ command: "completeTask", args: { taskId: id } }),
    );
    if (isCompletionErrorResponse(response)) {
      errors.push({ id, scope: "task", message: response.error });
    } else {
      completed.push(toCompletionSuccessEntry(id, "task", response));
    }
  } else if (scope === "project") {
    const response = normalizeResult<CompletionBridgeResponse>(
      await callOmniFocus({
        command: "completeProject",
        args: { projectId: id },
      }),
    );
    if (isCompletionErrorResponse(response)) {
      errors.push({ id, scope: "project", message: response.error });
    } else {
      completed.push(toCompletionSuccessEntry(id, "project", response));
    }
  } else {
    errors.push({
      id,
      scope: "unknown",
      message: `Unsupported scope: ${String(scope)}`,
    });
  }

  if (completed.length === 0 && errors.length === 0) {
    errors.push({
      id,
      scope: "unknown",
      message: "No completion action performed",
    });
  }

  return {
    completed,
    ...(errors.length > 0 ? { errors } : {}),
  };
}

function toCompletionSuccessEntry(
  id: string,
  scope: CompletionScope,
  response: CompletionSuccessResponse,
): CompletionSuccess {
  const completedAt = response.completedAt ?? new Date().toISOString();
  const base: CompletionSuccess = {
    id,
    scope,
    completionStatus: "completed",
    completedAt,
  };
  if (response.alreadyCompleted) {
    base.alreadyCompleted = true;
  }
  return base;
}

function isCompletionErrorResponse(
  value: CompletionBridgeResponse,
): value is CompletionErrorResponse {
  return Boolean((value as CompletionErrorResponse)?.error);
}

const tools = [
  {
    name: "taskOperations",
    description:
      "Manage tasks – list, get, create, update, complete, delete, move. Use taskId for get/update/complete/delete/move. Use name+projectId for create.",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "get", "create", "update", "complete", "delete", "move"],
          description: "Task operation: list (use filters), get/update/complete/delete (use taskId), create (use name), move (use taskId+targetProjectId)",
        },
        // Common identifier
        taskId: {
          type: "string",
          description: "Task UUID - required for get, update, complete, delete, move actions",
        },
        // Create/update fields
        name: {
          type: "string",
          description: "Task name - required for create, optional for update",
        },
        note: {
          type: "string",
          description: "Task notes/description",
        },
        projectId: {
          type: "string",
          description: "Project UUID to assign task to (for create or update)",
        },
        flagged: {
          type: "boolean",
          description: "Whether task is flagged",
        },
        dueDate: {
          type: "string",
          description: "Due date in ISO format (e.g., 2024-12-31T17:00:00Z)",
        },
        deferDate: {
          type: "string",
          description: "Defer/start date in ISO format",
        },
        estimatedMinutes: {
          type: "number",
          description: "Estimated duration in minutes",
        },
        tagIds: {
          type: "array",
          items: { type: "string" },
          description: "Array of tag UUIDs to assign",
        },
        completed: {
          type: "boolean",
          description: "For update: set completion status (true=complete, false=uncomplete)",
        },
        dropped: {
          type: "boolean",
          description: "For update: set dropped status",
        },
        // Move-specific fields
        targetProjectId: {
          type: "string",
          description: "For move: destination project UUID (null for inbox)",
        },
        parentTaskId: {
          type: "string",
          description: "For move: make this a subtask of specified parent task",
        },
        position: {
          type: "number",
          description: "For move: position within target (0-indexed)",
        },
        // List filters
        filters: {
          type: "object",
          properties: {
            projectId: { type: "string", description: "Filter by project UUID" },
            folderId: { type: "string", description: "Filter by folder UUID" },
            includeSubfolders: { type: "boolean", description: "Include tasks from subfolders" },
            tagId: { type: "string", description: "Filter by tag UUID" },
            includeCompleted: { type: "boolean", description: "Include completed tasks" },
            includeDropped: { type: "boolean", description: "Include dropped tasks" },
            active: { type: "boolean", description: "Filter for active tasks" },
            flagged: { type: "boolean", description: "Filter for flagged tasks" },
            limit: { type: "number", description: "Maximum results" },
          },
          required: ["projectId", "folderId", "includeSubfolders", "tagId", "includeCompleted", "includeDropped", "active", "flagged", "limit"],
          additionalProperties: false,
          description: "Filters for list action only",
        },
        detailLevel: {
          type: "string",
          enum: detailLevelEnum.options,
          default: "standard",
          description: detailLevelDescription,
        },
        sortOrder: {
          type: "string",
          enum: sortOrderEnum.options,
          default: "default",
          description: freshnessDescription,
        },
      },
      required: ["action", "taskId", "name", "note", "projectId", "flagged", "dueDate", "deferDate", "estimatedMinutes", "tagIds", "completed", "dropped", "targetProjectId", "parentTaskId", "position", "filters", "detailLevel", "sortOrder"],
      additionalProperties: false,
    },
  },
  {
    name: "taskQuery",
    description:
      "Query/search tasks with advanced filtering. Use query for text search, scope to limit search area.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Text to search for in task names/notes" },
        scope: {
          type: "string",
          enum: ["all", "project", "tag", "perspective"],
          description: "Limit search to: all, project, tag, or perspective",
        },
        scopeId: {
          type: "string",
          description: "UUID of project/tag/perspective when scope is not 'all'",
        },
        searchScope: {
          type: "string",
          enum: ["nameOnly", "nameAndNotes"],
          description: "Search in names only or include notes",
          default: "nameOnly",
        },
        dueBefore: {
          type: "string",
          description: "Filter tasks due before this date (ISO format)",
        },
        dueAfter: {
          type: "string",
          description: "Filter tasks due after this date (ISO format)",
        },
        flagged: {
          type: "boolean",
          description: "Filter for flagged tasks only",
        },
        available: {
          type: "boolean",
          description: "Filter for available (not blocked/deferred) tasks only",
        },
        detailLevel: {
          type: "string",
          enum: detailLevelEnum.options,
          default: "standard",
          description: detailLevelDescription,
        },
        sortOrder: {
          type: "string",
          enum: sortOrderEnum.options,
          default: "default",
          description: freshnessDescription,
        },
      },
      required: ["query", "scope", "scopeId", "searchScope", "dueBefore", "dueAfter", "flagged", "available", "detailLevel", "sortOrder"],
      additionalProperties: false,
    },
  },
  {
    name: "taskHierarchy",
    description:
      "Manage task hierarchy – create subtasks, flatten task groups, move branches",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["createSubtask", "flatten", "moveBranch", "restructure"],
          description: "createSubtask: add child task, flatten: convert subtasks to siblings, moveBranch: move task with children",
        },
        taskId: {
          type: "string",
          description: "Parent task UUID for createSubtask, or task to flatten/move",
        },
        name: {
          type: "string",
          description: "For createSubtask: name of new subtask",
        },
        targetTaskId: {
          type: "string",
          description: "For moveBranch: destination parent task UUID",
        },
        targetProjectId: {
          type: "string",
          description: "For moveBranch: destination project UUID",
        },
        position: {
          type: "number",
          description: "Position within target (0-indexed)",
        },
        includeChildren: {
          type: "boolean",
          description: "For moveBranch: include all descendants (default true)",
          default: true,
        },
      },
      required: ["action", "taskId", "name", "targetTaskId", "targetProjectId", "position", "includeChildren"],
      additionalProperties: false,
    },
  },
  {
    name: "projectOperations",
    description: "Manage projects – list, get, create, update, move, convertTask. Use projectId for get/update/move.",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "get", "create", "update", "move", "convertTask"],
          description: "list: all projects, get: single project, create: new project, update: modify, move: relocate, convertTask: task→project",
        },
        projectId: {
          type: "string",
          description: "Project UUID - required for get, update, move actions",
        },
        taskId: {
          type: "string",
          description: "For convertTask: task UUID to convert to project",
        },
        name: {
          type: "string",
          description: "Project name - required for create, optional for update",
        },
        note: {
          type: "string",
          description: "Project notes",
        },
        folderId: {
          type: "string",
          description: "Folder UUID - for create/move, or to filter list",
        },
        status: {
          type: "string",
          enum: ["active", "onHold", "completed", "dropped"],
          description: "Project status",
        },
        sequential: {
          type: "boolean",
          description: "True for sequential project (tasks done in order)",
        },
        flagged: {
          type: "boolean",
          description: "Whether project is flagged",
        },
        dueDate: {
          type: "string",
          description: "Due date in ISO format",
        },
        deferDate: {
          type: "string",
          description: "Defer/start date in ISO format",
        },
        completedByChildren: {
          type: "boolean",
          description: "Auto-complete when all tasks done",
        },
        position: {
          type: "number",
          description: "Position within folder (for create/move)",
        },
        completion: {
          type: "string",
          enum: ["all", "active", "completed", "dropped"],
          description: "For list: filter by completion state",
        },
        includeTasks: {
          type: "boolean",
          description: "For list/get: include task details",
        },
        detailLevel: {
          type: "string",
          enum: detailLevelEnum.options,
          default: "standard",
          description: detailLevelDescription,
        },
        sortOrder: {
          type: "string",
          enum: sortOrderEnum.options,
          default: "default",
          description: freshnessDescription,
        },
      },
      required: ["action", "projectId", "taskId", "name", "note", "folderId", "status", "sequential", "flagged", "dueDate", "deferDate", "completedByChildren", "position", "completion", "includeTasks", "detailLevel", "sortOrder"],
      additionalProperties: false,
    },
  },
  {
    name: "projectSettings",
    description:
      "Update project settings – group types, completion behaviour, properties",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["setGroupType", "setCompletionBehavior", "setProperties"],
          description: "setGroupType: parallel/sequential, setCompletionBehavior: auto-complete rules, setProperties: bulk update",
        },
        projectId: {
          type: "string",
          description: "Project UUID - required",
        },
        sequential: {
          type: "boolean",
          description: "For setGroupType: true=sequential, false=parallel",
        },
        completedByChildren: {
          type: "boolean",
          description: "For setCompletionBehavior: auto-complete when children done",
        },
        properties: {
          type: "object",
          description: "For setProperties: object with property names and values",
          properties: {},
          required: [],
          additionalProperties: true,
        },
      },
      required: ["action", "projectId", "sequential", "completedByChildren", "properties"],
      additionalProperties: false,
    },
  },
  {
    name: "folderOperations",
    description: "Manage folders – list, get, create, delete. Use folderId for get/delete.",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "get", "create", "delete"],
          description: "list: all folders, get: single folder by folderId, create: new folder, delete: remove folder",
        },
        folderId: {
          type: "string",
          description: "Folder UUID - required for get, delete",
        },
        name: {
          type: "string",
          description: "For create: folder name",
        },
        parentFolderId: {
          type: "string",
          description: "For create/list: parent folder UUID (null for top-level)",
        },
        includeEmpty: {
          type: "boolean",
          description: "For list: include folders with no projects",
          default: true,
        },
        maxDepth: {
          type: "number",
          description: "For list: maximum nesting depth to return",
        },
      },
      required: ["action", "folderId", "name", "parentFolderId", "includeEmpty", "maxDepth"],
      additionalProperties: false,
    },
  },
  {
    name: "folderNavigation",
    description: "Navigate folders – get tree and validate moves. For getTree, use includeProjects:true to see projects.",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["getTree", "validateMove"],
          description: "Navigation action: getTree returns folder hierarchy, validateMove checks if a move is valid",
        },
        folderId: {
          type: "string",
          description: "Optional folder UUID to start from (omit for entire library tree)",
        },
        includeProjects: {
          type: "boolean",
          description: "Include projects in tree output (default false, recommended true for full hierarchy view)",
          default: false,
        },
        maxDepth: {
          type: "number",
          description: "Maximum depth to traverse (omit for unlimited)",
        },
        targetFolderId: {
          type: "string",
          description: "For validateMove: the destination folder UUID",
        },
        projectId: {
          type: "string",
          description: "For validateMove: the project UUID to move",
        },
      },
      required: ["action", "folderId", "includeProjects", "maxDepth", "targetFolderId", "projectId"],
      additionalProperties: false,
    },
  },
  {
    name: "inboxOperations",
    description: "Inbox management – list inbox items, process items to projects, get context",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "process", "getContext"],
          description: "list: view inbox, process: move item to project, getContext: get item details",
        },
        itemId: {
          type: "string",
          description: "Inbox item UUID - for process, getContext",
        },
        targetProjectId: {
          type: "string",
          description: "For process: destination project UUID",
        },
        includeCompleted: {
          type: "boolean",
          description: "For list: include completed inbox items",
          default: false,
        },
        sortBy: {
          type: "string",
          enum: ["added", "name", "dueDate"],
          description: "For list: sort order",
          default: "added",
        },
        limit: {
          type: "number",
          description: "For list: maximum items to return",
        },
      },
      required: ["action", "itemId", "targetProjectId", "includeCompleted", "sortBy", "limit"],
      additionalProperties: false,
    },
  },
  {
    name: "bulkInboxProcessing",
    description: "Execute batch inbox operations - process multiple items at once",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["executeBulk"],
          description: "executeBulk: process multiple inbox items",
        },
        operations: {
          type: "array",
          items: {
            type: "object",
            properties: {
              itemId: { type: "string", description: "Inbox item UUID" },
              targetProjectId: { type: "string", description: "Destination project UUID" },
              action: { type: "string", enum: ["move", "delete", "complete"] },
            },
            required: ["itemId", "targetProjectId", "action"],
            additionalProperties: false,
          },
          description: "Array of operations to perform",
        },
        validateFirst: {
          type: "boolean",
          description: "Validate all operations before executing",
          default: true,
        },
        continueOnError: {
          type: "boolean",
          description: "Continue processing if an operation fails",
          default: false,
        },
      },
      required: ["action", "operations", "validateFirst", "continueOnError"],
      additionalProperties: false,
    },
  },
  {
    name: "perspectiveOperations",
    description: "Manage perspectives – list available, get details, switch active view",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "get", "switch"],
          description: "list: all perspectives, get: perspective details, switch: change active perspective",
        },
        perspectiveId: {
          type: "string",
          description: "Perspective UUID - for get, switch",
        },
        perspectiveName: {
          type: "string",
          description: "Perspective name - alternative to perspectiveId for switch",
        },
        includeBuiltIn: {
          type: "boolean",
          description: "For list: include built-in perspectives (Inbox, Projects, etc.)",
          default: true,
        },
        sortOrder: {
          type: "string",
          enum: sortOrderEnum.options,
          default: "default",
          description: freshnessDescription,
        },
        detailLevel: {
          type: "string",
          enum: detailLevelEnum.options,
          default: "standard",
          description: detailLevelDescription,
        },
      },
      required: ["action", "perspectiveId", "perspectiveName", "includeBuiltIn", "sortOrder", "detailLevel"],
      additionalProperties: false,
    },
  },
  {
    name: "tagOperations",
    description: "Manage tags – list all tags, get tag details, query tasks by tag",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "get", "create", "update", "delete", "queryTasks"],
          description: "list: all tags, get: tag details, create/update/delete: manage tags, queryTasks: find tasks with tag",
        },
        tagId: {
          type: "string",
          description: "Tag UUID - for get, update, delete, queryTasks",
        },
        name: {
          type: "string",
          description: "Tag name - for create, update",
        },
        parentTagId: {
          type: "string",
          description: "Parent tag UUID - for create (nested tags)",
        },
        includeNested: {
          type: "boolean",
          description: "For list/queryTasks: include nested/child tags",
          default: false,
        },
        detailLevel: {
          type: "string",
          enum: detailLevelEnum.options,
          default: "standard",
          description: detailLevelDescription,
        },
        sortOrder: {
          type: "string",
          enum: sortOrderEnum.options,
          default: "default",
          description: freshnessDescription,
        },
      },
      required: ["action", "tagId", "name", "parentTagId", "includeNested", "detailLevel", "sortOrder"],
      additionalProperties: false,
    },
  },
  {
    name: "validationOperations",
    description: "Validation helpers – validate operations before executing",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["validateTransaction", "validateMove", "validateCreate"],
          description: "validateTransaction: check transaction validity, validateMove: check move validity, validateCreate: check creation params",
        },
        taskId: {
          type: "string",
          description: "For validateMove: task to move",
        },
        projectId: {
          type: "string",
          description: "For validateMove/validateCreate: target or parent project",
        },
        targetFolderId: {
          type: "string",
          description: "For validateMove: destination folder",
        },
        name: {
          type: "string",
          description: "For validateCreate: name to validate",
        },
        transactionId: {
          type: "string",
          description: "For validateTransaction: transaction to validate",
        },
      },
      required: ["action", "taskId", "projectId", "targetFolderId", "name", "transactionId"],
      additionalProperties: false,
    },
  },
  {
    name: "transactionOperations",
    description:
      "Manage undo transactions – begin batch, execute, accept, rollback",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["begin", "execute", "accept", "rollback", "rollbackRecent", "getHistory"],
          description: "begin: start batch, execute: run operations, accept: commit, rollback: undo, getHistory: view past transactions",
        },
        transactionId: {
          type: "string",
          description: "Transaction UUID - for execute, accept, rollback",
        },
        operations: {
          type: "array",
          description: "For execute: array of operations to perform in transaction",
          items: { type: "object", properties: {}, required: [], additionalProperties: true },
        },
        count: {
          type: "number",
          description: "For rollbackRecent/getHistory: number of transactions",
          default: 1,
        },
      },
      required: ["action", "transactionId", "operations", "count"],
      additionalProperties: false,
    },
  },
  {
    name: "taskGroupOperations",
    description: "Manage task group types – set sequential or parallel execution",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["getGroupType", "setGroupType"],
          description: "getGroupType: check current setting, setGroupType: change sequential/parallel",
        },
        taskId: {
          type: "string",
          description: "Parent task UUID with subtasks",
        },
        sequential: {
          type: "boolean",
          description: "For setGroupType: true=sequential (one at a time), false=parallel (all available)",
        },
      },
      required: ["action", "taskId", "sequential"],
      additionalProperties: false,
    },
  },
  {
    name: "reviewOperations",
    description: "Review support – list projects needing review, mark as reviewed",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "markReviewed", "getNextReview"],
          description: "list: projects due for review, markReviewed: complete review, getNextReview: next review date",
        },
        projectId: {
          type: "string",
          description: "Project UUID - for markReviewed, getNextReview",
        },
        includeOnHold: {
          type: "boolean",
          description: "For list: include on-hold projects",
          default: false,
        },
        overdue: {
          type: "boolean",
          description: "For list: only show overdue reviews",
          default: false,
        },
      },
      required: ["action", "projectId", "includeOnHold", "overdue"],
      additionalProperties: false,
    },
  },
  {
    name: "automationSupport",
    description: "Automation helpers – get suggestions, run diagnostics, cleanup stale items",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["suggest", "diagnose", "cleanup"],
          description: "suggest: get actionable suggestions, diagnose: check for issues, cleanup: remove stale items",
        },
        scope: {
          type: "string",
          enum: ["all", "project", "folder", "inbox"],
          description: "Limit scope of analysis",
        },
        scopeId: {
          type: "string",
          description: "Project or folder UUID when scope is not 'all'",
        },
        dryRun: {
          type: "boolean",
          description: "For cleanup: preview changes without applying",
          default: true,
        },
        maxAge: {
          type: "number",
          description: "For cleanup: days since last modification to consider stale",
          default: 90,
        },
      },
      required: ["action", "scope", "scopeId", "dryRun", "maxAge"],
      additionalProperties: false,
    },
  },
  {
    name: "analyticsInsights",
    description: "Analytics insights – project health scores, workload analysis, completion trends",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["projectHealth", "workload", "trends", "summary"],
          description: "projectHealth: stalled/blocked projects, workload: task distribution, trends: completion rates, summary: overview",
        },
        projectId: {
          type: "string",
          description: "For projectHealth: specific project to analyze",
        },
        folderId: {
          type: "string",
          description: "Limit analysis to projects in folder",
        },
        period: {
          type: "string",
          enum: ["day", "week", "month", "quarter", "year"],
          description: "For trends: time period to analyze",
          default: "week",
        },
        includeCompleted: {
          type: "boolean",
          description: "Include completed items in analysis",
          default: false,
        },
      },
      required: ["action", "projectId", "folderId", "period", "includeCompleted"],
      additionalProperties: false,
    },
  },
  {
    name: "systemOperations",
    description: "System operations – health/status information",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["health"],
          description: "System action",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "markCompleted",
    description:
      "Mark a task or project as completed by ID. Provide `id` and optionally `scope` (`task` default or `project`). Returns completion status.",
    inputSchema: quickToolSchemas.markCompleted,
  },
  {
    name: "listUncompletedTasks",
    description:
      "List incomplete tasks with optional filters (`projectId`, `onlyFlagged`, `onlyAvailable`). Useful for quick inbox or project reviews.",
    inputSchema: quickToolSchemas.listUncompletedTasks,
  },
  {
    name: "listProjects",
    description:
      "List projects, optionally grouped by folder. Supports `completion` filters, `detailLevel`, `listByFolder`, `listProjectNames`, and `folderId` scope.",
    inputSchema: quickToolSchemas.listProjects,
  },
  {
    name: "moveTaskToProject",
    description: "Move a task into a specified project",
    inputSchema: quickToolSchemas.moveTaskToProject,
  },
  {
    name: "tasksHelp",
    description:
      "Retrieve OmniFocus quick-access help in markdown format, including initialization and tool invocation examples.",
    inputSchema: quickToolSchemas.tasksHelp,
  },
];

function asJsonText(body: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(body, null, 2) }],
  };
}

function getDetailLevel(value: unknown): DetailLevel {
  const result = detailLevelEnum.safeParse(value);
  return result.success ? result.data : "standard";
}

function getSortOrder(value: unknown): SortOrder {
  const result = sortOrderEnum.safeParse(value);
  return result.success ? result.data : "default";
}

/**
 * Clean up args by removing empty strings, null, undefined values.
 * Also treats maxDepth: 0 as undefined (meaning unlimited).
 * This is needed because OpenAI strict mode requires all properties to be sent,
 * but OmniFocus may fail on empty string values.
 */
function cleanArgs(args: Record<string, unknown>): Record<string, unknown> {
  const cleaned: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(args)) {
    // Skip empty strings, null, undefined
    if (value === "" || value === null || value === undefined) continue;
    // Skip maxDepth: 0 (treat as unlimited)
    if (key === "maxDepth" && value === 0) continue;
    // Skip empty arrays
    if (Array.isArray(value) && value.length === 0) continue;
    cleaned[key] = value;
  }
  return cleaned;
}

function normalizeFreshnessValue(value: unknown): number {
  if (typeof value === "string") {
    const time = Date.parse(value);
    if (!Number.isNaN(time)) {
      return time;
    }
  }
  return Number.NEGATIVE_INFINITY;
}

function sortByFreshness(data: any): any {
  const sortArray = (array: any[]) => {
    return [...array].sort((a, b) => {
      const bTime =
        normalizeFreshnessValue(b?.modified) ||
        normalizeFreshnessValue(b?.added);
      const aTime =
        normalizeFreshnessValue(a?.modified) ||
        normalizeFreshnessValue(a?.added);
      if (bTime === aTime) {
        return 0;
      }
      return bTime - aTime;
    });
  };

  if (Array.isArray(data)) {
    return sortArray(data);
  }

  if (data && typeof data === "object" && Array.isArray((data as any).result)) {
    return { ...data, result: sortArray((data as any).result) };
  }

  return data;
}

function createMinimalRecord(item: any) {
  if (!item || typeof item !== "object") {
    return item;
  }

  const minimal: any = {};

  const id =
    item.id ??
    item.taskId ??
    item.projectId ??
    item.folderId ??
    item.tagId ??
    item.perspectiveId;
  if (id !== undefined) {
    minimal.id = id;
  }

  const name =
    item.name ??
    item.taskName ??
    item.projectName ??
    item.folderName ??
    item.tagName ??
    item.perspectiveName;
  if (name !== undefined) {
    minimal.name = name;
  }

  if (item.status !== undefined) {
    minimal.status = item.status;
  } else if (item.completed !== undefined) {
    minimal.completed = item.completed;
  }

  if (item.flagged !== undefined) {
    minimal.flagged = item.flagged;
  }

  minimal.added = item.added ?? null;
  minimal.modified = item.modified ?? null;

  if ("plannedDate" in item) {
    minimal.plannedDate = item.plannedDate ?? null;
  }
  if ("effectivePlannedDate" in item) {
    minimal.effectivePlannedDate = item.effectivePlannedDate ?? null;
  }

  return minimal;
}

function removeHeavyFields(item: any) {
  if (!item || typeof item !== "object") {
    return item;
  }
  const clone: any = { ...item };
  delete clone.note;
  delete clone.notes;
  delete clone.attachments;
  delete clone.configuration;
  delete clone.serverSideProcessing;
  return clone;
}

function filterResponseByDetailLevel(data: any, detailLevel: DetailLevel): any {
  if (!data) {
    return data;
  }

  if (Array.isArray(data)) {
    return data.map((item) => filterResponseByDetailLevel(item, detailLevel));
  }

  if (typeof data === "object" && data !== null) {
    let working = data as Record<string, unknown>;

    if (Object.prototype.hasOwnProperty.call(working, "result")) {
      working = {
        ...working,
        result: filterResponseByDetailLevel(
          (working as any).result,
          detailLevel,
        ),
      };
    }

    if (
      (working as any).detailLevel &&
      (working as any).detailLevel !== detailLevel
    ) {
      // continue to clamp below to enforce requested detail level
    }

    if (Array.isArray((working as any).result)) {
      return {
        ...working,
        result: (working as any).result.map((item: any) =>
          filterResponseByDetailLevel(item, detailLevel),
        ),
      };
    }

    if (
      detailLevel in working ||
      "minimal" in working ||
      "standard" in working ||
      "full" in working
    ) {
      const target =
        working[detailLevel] ??
        working.standard ??
        working.full ??
        working.minimal ??
        working;
      return filterResponseByDetailLevel(target, detailLevel);
    }

    data = working;
  }

  const MINIMAL_FIELDS = [
    "id",
    "taskId",
    "name",
    "status",
    "completionState",
    "added",
    "modified",
    "created",
    "projectId",
    "inInbox",
    "flagged",
    "deferDate",
    "deferred",
    "due",
    "dueDate",
    "duration",
    "durationMinutes",
    "detailLevel",
    "result",
  ];
  const STANDARD_FIELDS = MINIMAL_FIELDS.concat([
    "sequential",
    "nextReviewDate",
    "lastReviewDate",
    "folderId",
    "folderName",
    "taskIds",
    "taskCounts",
    "tasks",
    "projects",
    // Folder hierarchy fields
    "folder",
    "subfolders",
    "parentFolderId",
    "projectCount",
    "subfolderCount",
    "path",
    "active",
    "taskCount",
    "completed",
  ]);
  const FULL_FIELDS = STANDARD_FIELDS.concat(["note", "tasks", "folderPath"]);

  const clampToFields = (value: any, fields: string[]): any => {
    if (!value || typeof value !== "object") {
      return value;
    }
    const result: Record<string, unknown> = {};
    fields.forEach((field) => {
      if (field in value) {
        result[field] = value[field];
      }
    });
    return {
      ...result,
      detailLevel,
    };
  };

  if (detailLevel === "minimal") {
    return clampToFields(data, MINIMAL_FIELDS);
  }

  if (detailLevel === "standard") {
    return clampToFields(data, STANDARD_FIELDS);
  }

  if (detailLevel === "full") {
    return clampToFields(data, FULL_FIELDS);
  }

  return data;
}

function applySortOrder(data: any, sortOrder: SortOrder): any {
  if (sortOrder !== "freshness") {
    return data;
  }
  return sortByFreshness(data);
}

function requireString(value: unknown, name: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value;
}

function isAvailableTask(task: any): boolean {
  if (!task || typeof task !== "object") {
    return false;
  }
  if (task.completed || task.dropped) {
    return false;
  }
  if (task.deferDate) {
    const deferDate = Date.parse(task.deferDate);
    if (!Number.isNaN(deferDate) && deferDate > Date.now()) {
      return false;
    }
  }
  return true;
}

function normalizeResult<T = unknown>(raw: any): T {
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw) as T;
    } catch (error) {
      console.warn("Failed to parse JSON string result", error);
      return raw as T;
    }
  }
  return raw as T;
}

function toTaskSummary(task: any) {
  return {
    taskId: task.id ?? task.taskId ?? null,
    name: task.name ?? task.taskName ?? "",
    projectId: task.projectId ?? null,
    inInbox: Boolean(task.projectId == null),
    flagged: Boolean(task.flagged),
    created: task.added ?? task.created ?? null,
    due: task.dueDate ?? task.due ?? null,
    deferred: task.deferDate ?? task.deferred ?? null,
    durationMinutes: task.duration ?? task.durationMinutes ?? null,
  };
}

function toProjectSummary(project: any, includeTaskNames: boolean) {
  const folderId = project.folderId ?? project.folderID ?? null;
  const folderName = project.folderName ?? project.folder?.name ?? null;
  const base = {
    projectId: project.id ?? project.projectId ?? null,
    name: project.name ?? project.projectName ?? "",
    description: project.note ?? project.description ?? null,
    folderId,
    folderName,
    taskIds: Array.isArray(project.taskIds)
      ? project.taskIds
      : Array.isArray(project.tasks)
        ? project.tasks.map((task: any) => task.id ?? task.taskId)
        : [],
  };

  if (includeTaskNames) {
    const tasks = Array.isArray(project.tasks)
      ? project.tasks.map((task: any) => ({
          taskId: task.id ?? task.taskId,
          name: task.name ?? task.taskName ?? "",
          durationMinutes: task.duration ?? task.durationMinutes ?? null,
        }))
      : base.taskIds.map((taskId: string) => ({
          taskId,
          name: "",
          durationMinutes: null,
        }));
    return { ...base, tasks };
  }

  return base;
}

class OmniFocusSimplifiedMCPServer {
  private readonly server: Server;
  private readonly transports: Record<string, StreamableHTTPServerTransport> =
    {};

  constructor(server: Server) {
    this.server = server;
    this.registerHandlers();
  }

  private registerHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools,
    }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const args = request.params.arguments ?? {};
      const toolName = request.params.name;

      if (!toolName) {
        throw new Error("tool name undefined");
      }

      if (toolName === "tasksHelp") {
        return {
          content: [
            {
              type: "text" as const,
              text: HELP_MARKDOWN,
            },
          ],
        };
      }

      let detailLevel: DetailLevel = "standard";
      let sortOrder: SortOrder = "default";
      let command: string;
      let commandArgs: any = args;

      switch (toolName) {
        case "taskOperations": {
          const {
            action,
            taskId,
            name,
            note,
            projectId,
            flagged,
            dueDate,
            deferDate,
            estimatedMinutes,
            tagIds,
            completed,
            dropped,
            targetProjectId,
            parentTaskId,
            position,
            filters = {},
            detailLevel: dl,
            sortOrder: so,
          } = args;
          detailLevel = getDetailLevel(dl);
          sortOrder = getSortOrder(so);
          switch (action) {
            case "list":
              command = "listRemaining";
              commandArgs =
                typeof filters === "object" && filters !== null
                  ? { ...filters }
                  : {};
              break;
            case "get":
              command = "getTask";
              commandArgs = { taskId };
              sortOrder = "default";
              break;
            case "create":
              command = "createTask";
              commandArgs = { name, projectId, note, flagged, dueDate, deferDate, estimatedMinutes, tagIds };
              sortOrder = "default";
              break;
            case "update":
              command = "updateTask";
              commandArgs = { taskId, name, note, flagged, completed, dropped, dueDate, deferDate, estimatedMinutes, projectId, tagIds };
              sortOrder = "default";
              break;
            case "complete":
              command = "completeTask";
              commandArgs = { taskId };
              sortOrder = "default";
              break;
            case "delete":
              command = "deleteTask";
              commandArgs = { taskId };
              sortOrder = "default";
              break;
            case "move":
              command = "moveTask";
              commandArgs = { taskId, targetProjectId, parentTaskId, position };
              sortOrder = "default";
              break;
            default:
              throw new Error(`Unknown task action: ${action}`);
          }
          break;
        }
        case "markCompleted": {
          const { id, scope = "task" } = args;
          const resolvedId = requireString(id, "id");

          const completionResult = await performCompletion(resolvedId, scope);
          return asJsonText(completionResult);
        }
        case "listUncompletedTasks": {
          const { projectId, folderId, includeSubfolders, onlyFlagged, onlyAvailable } = args;
          const rawList = normalizeResult<{ result?: any[] } | any[]>(
            await callOmniFocus({ command: "listRemaining", args: {} }),
          );

          const tasksArray = Array.isArray(rawList)
            ? rawList
            : rawList &&
                typeof rawList === "object" &&
                Array.isArray((rawList as any).result)
              ? (rawList as any).result
              : [];

          // If filtering by folder, get the list of valid folder IDs
          let validFolderIds: Set<string> | null = null;
          if (folderId) {
            validFolderIds = new Set<string>([folderId as string]);
            if (includeSubfolders) {
              // Get subfolder IDs from the folder hierarchy
              const folderTree = normalizeResult<any>(
                await callOmniFocus({ command: "getProjectTree", args: { folderId, includeProjects: false } }),
              );
              const collectFolderIds = (node: any) => {
                if (node?.folder?.id) validFolderIds!.add(node.folder.id);
                if (node?.subfolders) node.subfolders.forEach(collectFolderIds);
              };
              collectFolderIds(folderTree);
            }
          }

          const filtered = tasksArray
            .filter((task: any) => {
              if (projectId && task.projectId !== projectId) {
                return false;
              }
              if (validFolderIds && !validFolderIds.has(task.folderId)) {
                return false;
              }
              if (onlyFlagged && !task.flagged) {
                return false;
              }
              if (onlyAvailable && !isAvailableTask(task)) {
                return false;
              }
              return true;
            })
            .map(toTaskSummary);

          return asJsonText(filtered);
        }
        case "listProjects": {
          const {
            folderId,
            includeSubfolders,
            includeTasks: explicitIncludeTasks,
            listProjectNames,
            listByFolder,
            completion,
            detailLevel: dl,
            includeCounts,
          } = args;

          const detailLvl = getDetailLevel(dl);
          const includeNames = Boolean(listProjectNames);
          // includeTasks: explicit param takes precedence, otherwise true for full detail or listProjectNames
          const shouldIncludeTasks = explicitIncludeTasks === true || includeNames || detailLvl === "full";

          // If includeSubfolders, we need to get subfolder IDs first
          let folderIds: string[] | null = null;
          if (folderId) {
            folderIds = [folderId as string];
            if (includeSubfolders) {
              const folderTree = normalizeResult<any>(
                await callOmniFocus({ command: "getProjectTree", args: { folderId, includeProjects: false } }),
              );
              const collectFolderIds = (node: any, ids: string[]) => {
                if (node?.folder?.id && node.folder.id !== "root") ids.push(node.folder.id as string);
                if (node?.subfolders) node.subfolders.forEach((sub: any) => collectFolderIds(sub, ids));
              };
              collectFolderIds(folderTree, folderIds!);
            }
          }

          const rawProjects = normalizeResult<{ result?: any[] } | any[]>(
            await callOmniFocus({
              command: "listProjects",
              args: {
                completion,
                includeTasks: shouldIncludeTasks,
                includeNotes: detailLvl === "full",
                includeFolderPath: detailLvl === "full",
                includeCounts: includeCounts !== false,
                folderId: folderIds && folderIds.length === 1 ? folderIds[0] : null,
                listByFolder: Boolean(listByFolder),
              },
            }),
          );

          // If we have multiple folder IDs (subfolder case), filter the results
          let rawProjectsArray = Array.isArray(rawProjects)
            ? rawProjects
            : rawProjects &&
                typeof rawProjects === "object" &&
                Array.isArray((rawProjects as any).result)
              ? (rawProjects as any).result
              : null;

          // Filter by folder IDs if we have multiple (includeSubfolders case)
          if (folderIds && folderIds.length > 1 && rawProjectsArray) {
            const folderIdSet = new Set(folderIds);
            rawProjectsArray = rawProjectsArray.filter((p: any) =>
              p.folderId && folderIdSet.has(p.folderId)
            );
          }

          console.log(
            `[listProjects] folderId=${folderId ?? "<all>"} includeSubfolders=${includeSubfolders ?? false} completion=${completion ?? "<default>"} rawLength=${rawProjectsArray ? rawProjectsArray.length : "n/a"}`,
          );
          if (rawProjectsArray && rawProjectsArray.length > 0) {
            const firstProject = rawProjectsArray[0];
            console.log(
              `[listProjects] first project id=${firstProject?.id ?? "<unknown>"} folderId=${firstProject?.folderId ?? "<none>"} name=${firstProject?.name ?? "<unnamed>"}`,
            );
          }

          // Use filtered array if we filtered, otherwise original response
          const projectsToFilter = rawProjectsArray ?? rawProjects;
          const detailed = filterResponseByDetailLevel(projectsToFilter, detailLvl);

          if (Array.isArray(detailed)) {
            return asJsonText(detailed);
          }

          if (
            detailed &&
            typeof detailed === "object" &&
            Array.isArray((detailed as any).result)
          ) {
            return asJsonText((detailed as any).result);
          }

          // Fallback: return whatever structure came back (e.g., grouped object)
          return asJsonText(detailed ?? []);
        }
        case "moveTaskToProject": {
          const { taskId, projectId } = args;
          const resolvedTaskId = requireString(taskId, "taskId");
          const resolvedProjectId = requireString(projectId, "projectId");
          const result = normalizeResult<{ error?: string }>(
            await callOmniFocus({
              command: "moveTask",
              args: {
                taskId: resolvedTaskId,
                targetProjectId: resolvedProjectId,
              },
            }),
          );
          if (result?.error) {
            throw new Error(result.error);
          }
          return asJsonText({
            taskId: resolvedTaskId,
            projectId: resolvedProjectId,
            status: "moved",
          });
        }
        case "taskQuery": {
          const {
            query,
            scope,
            scopeId,
            searchScope,
            dueBefore,
            dueAfter,
            flagged,
            available,
            detailLevel: dl,
            sortOrder: so,
          } = args;
          detailLevel = getDetailLevel(dl);
          sortOrder = getSortOrder(so);

          if (query) {
            command = "searchTasks";
            commandArgs = {
              query,
              ...(typeof scope === "string" && scope ? { scope } : {}),
              ...(typeof scopeId === "string" && scopeId ? { scopeId } : {}),
              ...(typeof searchScope === "string" && searchScope ? { searchScope } : {}),
              ...(typeof dueBefore === "string" && dueBefore ? { dueBefore } : {}),
              ...(typeof dueAfter === "string" && dueAfter ? { dueAfter } : {}),
              ...(typeof flagged === "boolean" ? { flagged } : {}),
              ...(typeof available === "boolean" ? { available } : {}),
            };
          } else {
            command = "queryTasks";
            commandArgs = {
              ...(typeof scope === "string" && scope ? { scope } : {}),
              ...(typeof scopeId === "string" && scopeId ? { scopeId } : {}),
              ...(typeof dueBefore === "string" && dueBefore ? { dueBefore } : {}),
              ...(typeof dueAfter === "string" && dueAfter ? { dueAfter } : {}),
              ...(typeof flagged === "boolean" ? { flagged } : {}),
              ...(typeof available === "boolean" ? { available } : {}),
            };
          }
          break;
        }
        case "taskHierarchy": {
          const { action, taskId, name, targetTaskId, targetProjectId, position, includeChildren } = args;
          sortOrder = "default";
          switch (action) {
            case "createSubtask":
              command = "createSubtask";
              commandArgs = { parentTaskId: taskId, name };
              break;
            case "flatten":
              command = "flattenTaskHierarchy";
              commandArgs = { taskId };
              break;
            case "moveBranch":
              command = "moveTaskBranch";
              commandArgs = { taskId, targetTaskId, targetProjectId, position, includeChildren };
              break;
            case "restructure":
              command = "restructureTaskHierarchy";
              commandArgs = { taskId };
              break;
            default:
              throw new Error(`Unknown hierarchy action: ${action}`);
          }
          break;
        }
        case "projectOperations": {
          const {
            action,
            projectId,
            taskId,
            name,
            note,
            folderId,
            status,
            sequential,
            flagged,
            dueDate,
            deferDate,
            completedByChildren,
            position,
            completion,
            includeTasks,
            detailLevel: dl,
            sortOrder: so,
          } = args;
          detailLevel = getDetailLevel(dl);
          sortOrder = getSortOrder(so);
          switch (action) {
            case "list":
              command = "listProjects";
              commandArgs = {
                completion,
                folderId,
                includeTasks: includeTasks || detailLevel === "full",
                includeNotes: detailLevel === "full",
                includeFolderPath: detailLevel === "full",
                includeCounts: true,
              };
              break;
            case "get":
              command = "getProjectById";
              commandArgs = {
                projectId,
                options: {
                  includeNotes: detailLevel === "full",
                  includeTasks: includeTasks || detailLevel === "full",
                  includeFolderPath: detailLevel === "full",
                  includeCounts: true,
                },
              };
              sortOrder = "default";
              break;
            case "create":
              command = "createProject";
              commandArgs = { name, folderId, position, properties: { note, sequential, flagged, dueDate, deferDate, completedByChildren } };
              sortOrder = "default";
              break;
            case "update":
              command = "setProjectProperties";
              commandArgs = { projectId, properties: { name, note, status, sequential, flagged, dueDate, deferDate, completedByChildren } };
              sortOrder = "default";
              break;
            case "move":
              command = "moveProject";
              commandArgs = { projectId, folderId, position };
              sortOrder = "default";
              break;
            case "convertTask":
              command = "convertTaskToProject";
              commandArgs = { taskId, folderId, position };
              sortOrder = "default";
              break;
            default:
              throw new Error(`Unknown project action: ${action}`);
          }
          break;
        }
        case "projectSettings": {
          const { action, projectId, sequential, completedByChildren, properties } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "setGroupType":
              command = "setProjectGroupType";
              commandArgs = { projectId, sequential };
              break;
            case "setCompletionBehavior":
              command = "setProjectCompletionBehavior";
              commandArgs = { projectId, completedByChildren };
              break;
            case "setProperties":
              command = "setProjectProperties";
              commandArgs = { projectId, properties };
              break;
            default:
              throw new Error(`Unknown project settings action: ${action}`);
          }
          break;
        }
        case "folderOperations": {
          const { action, folderId, name, parentFolderId, includeEmpty, maxDepth } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "list":
              command = "listFolders";
              commandArgs = { parentFolderId, includeEmpty, maxDepth };
              break;
            case "get":
              command = "getFolderById";
              commandArgs = { folderId };
              break;
            case "create":
              command = "createFolder";
              commandArgs = { name, parentFolderId };
              break;
            case "delete":
              command = "deleteFolder";
              commandArgs = { folderId };
              break;
            default:
              throw new Error(`Unknown folder action: ${action}`);
          }
          break;
        }
        case "folderNavigation": {
          const { action, folderId, includeProjects, maxDepth, targetFolderId, projectId } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "getTree":
              command = "getFolderHierarchy";
              commandArgs = { folderId, includeProjects, maxDepth };
              break;
            case "validateMove":
              command = "validateProjectMove";
              commandArgs = { projectId, targetFolderId };
              break;
            default:
              throw new Error(`Unknown folder navigation action: ${action}`);
          }
          break;
        }
        case "inboxOperations": {
          const { action, itemId, targetProjectId, includeCompleted, sortBy, limit } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "list":
              command = "listInbox";
              commandArgs = { includeCompleted, sortBy, limit };
              break;
            case "process":
              command = "processInboxItem";
              commandArgs = { itemId, targetProjectId };
              break;
            case "getContext":
              command = "getInboxProcessingContext";
              commandArgs = { itemId };
              break;
            default:
              throw new Error(`Unknown inbox action: ${action}`);
          }
          break;
        }
        case "bulkInboxProcessing": {
          const { action, operations, validateFirst, continueOnError } = args;
          detailLevel = "standard";
          sortOrder = "default";
          if (action !== "executeBulk") {
            throw new Error(`Unknown bulk inbox action: ${action}`);
          }
          command = "executeBulkInboxProcessing";
          commandArgs = { item_operations: operations, execution_options: { validate_before_execute: validateFirst, continue_on_errors: continueOnError } };
          break;
        }
        case "perspectiveOperations": {
          const {
            action,
            perspectiveId,
            perspectiveName,
            includeBuiltIn,
            detailLevel: dl,
            sortOrder: so,
          } = args;
          detailLevel = getDetailLevel(dl);
          sortOrder = getSortOrder(so);
          switch (action) {
            case "list":
              command = "listPerspectives";
              commandArgs = { includeBuiltIn };
              break;
            case "get":
              command = "getPerspective";
              commandArgs = { perspectiveId };
              sortOrder = "default";
              break;
            case "switch":
              command = "switchToPerspective";
              commandArgs = { perspectiveId, perspectiveName };
              sortOrder = "default";
              break;
            default:
              throw new Error(`Unknown perspective action: ${action}`);
          }
          break;
        }
        case "tagOperations": {
          const {
            action,
            tagId,
            name,
            parentTagId,
            includeNested,
            detailLevel: dl,
            sortOrder: so,
          } = args;
          detailLevel = getDetailLevel(dl);
          sortOrder = getSortOrder(so);
          switch (action) {
            case "list":
              command = "listTags";
              commandArgs = { includeNested };
              break;
            case "get":
              command = "getTagById";
              commandArgs = { tagId };
              sortOrder = "default";
              break;
            case "create":
              command = "createTag";
              commandArgs = { name, parentTagId };
              sortOrder = "default";
              break;
            case "update":
              command = "updateTag";
              commandArgs = { tagId, name };
              sortOrder = "default";
              break;
            case "delete":
              command = "deleteTag";
              commandArgs = { tagId };
              sortOrder = "default";
              break;
            case "queryTasks":
              command = "listTasksByTag";
              commandArgs = { tagId, includeNested };
              sortOrder = "default";
              break;
            default:
              throw new Error(`Unknown tag action: ${action}`);
          }
          break;
        }
        case "validationOperations": {
          const { action, taskId, projectId, targetFolderId, name, transactionId } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "validateTransaction":
              command = "validateTransaction";
              commandArgs = { transactionId };
              break;
            case "validateMove":
              command = "validateProjectMove";
              commandArgs = { projectId, targetFolderId };
              break;
            case "validateCreate":
              command = "validateProjectCreation";
              commandArgs = { name, folderId: targetFolderId };
              break;
            default:
              throw new Error(`Unknown validation action: ${action}`);
          }
          break;
        }
        case "transactionOperations": {
          const { action, transactionId, operations, count } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "begin":
              command = "beginTransaction";
              commandArgs = {};
              break;
            case "execute":
              command = "executeTransactional";
              commandArgs = { transactionId, operations };
              break;
            case "accept":
              command = "acceptTransaction";
              commandArgs = { transactionId };
              break;
            case "rollback":
              command = "rollbackTransaction";
              commandArgs = { transactionId };
              break;
            case "rollbackRecent":
              command = "rollbackRecentTransaction";
              commandArgs = { count };
              break;
            case "getHistory":
              command = "getTransactionHistory";
              commandArgs = { count };
              break;
            default:
              throw new Error(`Unknown transaction action: ${action}`);
          }
          break;
        }
        case "taskGroupOperations": {
          const { action, taskId, sequential } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "getGroupType":
              command = "getTaskGroupType";
              commandArgs = { taskId };
              break;
            case "setGroupType":
              command = "setTaskGroupType";
              commandArgs = { taskId, sequential };
              break;
            default:
              throw new Error(`Unknown task group action: ${action}`);
          }
          break;
        }
        case "reviewOperations": {
          const { action, projectId, includeOnHold, overdue } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "list":
              command = "listProjectsNeedingReview";
              commandArgs = { includeOnHold, overdue };
              break;
            case "markReviewed":
              command = "markProjectReviewed";
              commandArgs = { projectId };
              break;
            case "getNextReview":
              command = "getProjectNextReview";
              commandArgs = { projectId };
              break;
            default:
              throw new Error(`Unknown review action: ${action}`);
          }
          break;
        }
        case "automationSupport": {
          const { action, scope, scopeId, dryRun, maxAge } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "suggest":
              command = "suggestAutomation";
              commandArgs = { scope, scopeId };
              break;
            case "diagnose":
              command = "diagnoseAutomation";
              commandArgs = { scope, scopeId };
              break;
            case "cleanup":
              command = "cleanupAutomationArtifacts";
              commandArgs = { scope, scopeId, dryRun, maxAge };
              break;
            default:
              throw new Error(`Unknown automation action: ${action}`);
          }
          break;
        }
        case "analyticsInsights": {
          const { action, projectId, folderId, period, includeCompleted } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "projectHealth":
              command = "getProjectHealth";
              commandArgs = { projectId, folderId };
              break;
            case "workload":
              command = "getWorkloadSummary";
              commandArgs = { folderId, includeCompleted };
              break;
            case "trends":
              command = "getTrendInsights";
              commandArgs = { period, folderId, includeCompleted };
              break;
            case "summary":
              command = "getAnalyticsSummary";
              commandArgs = { folderId, includeCompleted };
              break;
            default:
              throw new Error(`Unknown analytics action: ${action}`);
          }
          break;
        }
        case "systemOperations": {
          const { action } = args;
          detailLevel = "standard";
          sortOrder = "default";
          if (action !== "health") {
            throw new Error(`Unknown system operation: ${action}`);
          }
          command = "health";
          commandArgs = {};
          break;
        }
        default:
          throw new Error(`Unknown tool: ${toolName}`);
      }

      const rawResult = await callOmniFocus({ command, args: cleanArgs(commandArgs) });

      let parsedResult = rawResult;
      if (typeof rawResult === "string") {
        try {
          parsedResult = JSON.parse(rawResult);
        } catch (error) {
          console.warn("Failed to parse string result as JSON.");
        }
      }
      if (toolName === "taskOperations" && args?.action === "get") {
        console.log("[taskOperations.get] parsedResult", parsedResult);
      }

      // Apply folder filtering for taskOperations list action
      if (toolName === "taskOperations" && args?.action === "list" && (args?.filters as any)?.folderId) {
        const filters = args.filters as {
          folderId?: string;
          includeSubfolders?: boolean;
          projectId?: string;
          tagId?: string;
          includeCompleted?: boolean;
          includeDropped?: boolean;
          active?: boolean;
          flagged?: boolean;
          limit?: number;
        };
        const { folderId, includeSubfolders, projectId, tagId, includeCompleted, includeDropped, active, flagged, limit } = filters;

        // Get folder IDs to filter by
        let validFolderIds: Set<string> = new Set([folderId as string]);
        if (includeSubfolders) {
          const folderTree = normalizeResult<any>(
            await callOmniFocus({ command: "getProjectTree", args: { folderId, includeProjects: false } }),
          );
          const collectFolderIds = (node: any) => {
            if (node?.folder?.id && node.folder.id !== "root") validFolderIds.add(node.folder.id);
            if (node?.subfolders) node.subfolders.forEach(collectFolderIds);
          };
          collectFolderIds(folderTree);
        }

        // Filter the task results
        let tasksArray = Array.isArray(parsedResult)
          ? parsedResult
          : parsedResult?.result && Array.isArray(parsedResult.result)
            ? parsedResult.result
            : [];

        tasksArray = tasksArray.filter((task: any) => {
          if (!validFolderIds.has(task.folderId)) return false;
          if (projectId && task.projectId !== projectId) return false;
          if (tagId && (!task.contexts || !task.contexts.includes(tagId))) return false;
          if (!includeCompleted && task.completed) return false;
          if (!includeDropped && task.dropped) return false;
          if (active === true && !task.active) return false;
          if (flagged === true && !task.flagged) return false;
          return true;
        });

        if (limit && limit > 0) {
          tasksArray = tasksArray.slice(0, limit);
        }

        parsedResult = tasksArray;
        console.log(`[taskOperations.list] folderId=${folderId} includeSubfolders=${includeSubfolders} filtered to ${tasksArray.length} tasks`);
      }

      const filtered = filterResponseByDetailLevel(parsedResult, detailLevel);
      const finalResult = applySortOrder(filtered, sortOrder);
      return asJsonText(finalResult);
    });
  }

  getTransport(sessionId: string) {
    return this.transports[sessionId];
  }

  removeTransport(sessionId: string) {
    delete this.transports[sessionId];
  }

  async attachTransport(sessionId: string | undefined) {
    const server = this.server;
    const resolvedSessionId = sessionId ?? randomUUID();
    let transport: StreamableHTTPServerTransport;

    transport = new StreamableHTTPServerTransport({
      enableJsonResponse: true,
      sessionIdGenerator: () => resolvedSessionId,
      onsessioninitialized: (id: string) => {
        this.transports[id] = transport;
      },
    });

    await server.connect(transport);
    this.transports[resolvedSessionId] = transport;
    return transport;
  }

  async handlePostRequest(req: Request, res: Response) {
    const sessionId = req.headers[SESSION_ID_HEADER_NAME] as string | undefined;
    const payload = this.normalizeIncomingMessage(req.body);

    try {
      if (sessionId && this.transports[sessionId]) {
        const existingTransport = this.transports[sessionId];
        await existingTransport.handleRequest(req, res, payload);
        return;
      }

      const transport = await this.attachTransport(sessionId);
      await transport.handleRequest(req, res, payload);

      const newSession = transport.sessionId ?? sessionId;
      if (newSession) {
        this.transports[newSession] = transport;
      }
    } catch (error) {
      console.error("Error handling MCP request:", error);
      res.status(500).json({ error: "Internal server error." });
    }
  }

  async handleGetRequest(req: Request, res: Response) {
    const sessionId = req.headers[SESSION_ID_HEADER_NAME] as string | undefined;
    if (!sessionId) {
      res.status(400).json({ error: "missing mcp-session-id" });
      return;
    }

    const transport = this.transports[sessionId];
    if (!transport) {
      res.status(400).json({ error: "unknown mcp-session-id" });
      return;
    }

    await transport.handleRequest(req, res);
    await this.streamMessages(transport);
  }

  async handleDeleteRequest(req: Request, res: Response) {
    const sessionId = req.headers[SESSION_ID_HEADER_NAME] as string | undefined;
    if (!sessionId) {
      res.status(400).json({ error: "missing mcp-session-id" });
      return;
    }

    const transport = this.transports[sessionId];
    if (!transport) {
      res.status(400).json({ error: "unknown mcp-session-id" });
      return;
    }

    await transport.handleRequest(req, res);
    this.removeTransport(sessionId);
    res.status(204).end();
  }

  async cleanup() {
    await this.server.close();
  }

  private async streamMessages(_transport: StreamableHTTPServerTransport) {}

  private async sendNotification(
    transport: StreamableHTTPServerTransport,
    notification: Notification,
  ) {
    const jsonRpcNotification: JSONRPCNotification = {
      ...notification,
      jsonrpc: JSON_RPC,
    };
    await transport.send(jsonRpcNotification);
  }

  private isInitializeRequest(body: any): boolean {
    const check = (value: any) =>
      InitializeRequestSchema.safeParse(value).success;
    if (Array.isArray(body)) {
      return body.some((item) => check(item));
    }
    return check(body);
  }

  private normalizeIncomingMessage(body: any): any {
    const normalize = (message: any) => {
      if (!message || typeof message !== "object") {
        return message;
      }

      if (message.method === "initialize" && message.params) {
        const params = message.params as Record<string, unknown>;
        if (params.client && !params.clientInfo) {
          const { client, ...rest } = params;
          return {
            ...message,
            params: {
              ...rest,
              clientInfo: client,
            },
          };
        }
      }

      return message;
    };

    if (Array.isArray(body)) {
      return body.map(normalize);
    }

    return normalize(body);
  }
}

const simplifiedServer = new OmniFocusSimplifiedMCPServer(
  new Server(
    {
      name: "omnifocus-simplified-mcp",
      version: "1.0.0",
    },
    {
      capabilities: {
        tools: {},
        logging: {},
      },
    },
  ),
);

const app = express();

const MCP_ENDPOINT = "/mcp";

app.get("/health", (_req, res) => {
  res.json({
    status: "healthy",
    mode: "simplified",
    toolCount: tools.length,
    timestamp: new Date().toISOString(),
  });
});

app.post(MCP_ENDPOINT, async (req: Request, res: Response) => {
  await simplifiedServer.handlePostRequest(req, res);
});

app.get(MCP_ENDPOINT, async (req: Request, res: Response) => {
  await simplifiedServer.handleGetRequest(req, res);
});

app.delete(MCP_ENDPOINT, async (req: Request, res: Response) => {
  await simplifiedServer.handleDeleteRequest(req, res);
});

const PORT = Number.parseInt(process.env.PORT ?? "8889", 10);

const serverHandle = app.listen(PORT, () => {
  console.log(`🚀 OmniFocus simplified MCP (HTTP) listening on port ${PORT}`);
});

const shutdown = async () => {
  await simplifiedServer.cleanup();
  serverHandle.close(() => process.exit(0));
};

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
