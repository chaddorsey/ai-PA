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
      id: { type: "string", description: "UUID to mark complete" },
      scope: {
        type: "string",
        enum: ["task", "project"],
        description: "Scope of the identifier",
        default: "task",
      },
    },
    required: ["id"],
    additionalProperties: false,
  },
  listUncompletedTasks: {
    type: "object" as const,
    properties: {
      projectId: { type: "string", description: "Filter by project UUID", nullable: true },
      onlyFlagged: {
        type: "boolean",
        description: "Return only flagged tasks",
      },
      onlyAvailable: {
        type: "boolean",
        description: "Return only OmniFocus available tasks",
      },
    },
    additionalProperties: false,
  },
  listProjects: {
    type: "object" as const,
    properties: {
      folderId: {
        type: "string",
        description: "Filter to a specific folder UUID",
      },
      listProjectNames: {
        type: "boolean",
        description: "Include task names in addition to task IDs",
      },
      listByFolder: {
        type: "boolean",
        description: "Group results by folder",
      },
    },
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
};

type CompletionScope = "task" | "project";

interface CompletionSuccessResponse {
  completedAt?: string;
  alreadyCompleted?: boolean;
  success?: boolean;
}

interface CompletionErrorResponse {
  error: string;
}

type CompletionBridgeResponse = CompletionSuccessResponse | CompletionErrorResponse;

interface CompletionErrorEntry {
  id: string;
  scope: CompletionScope | "unknown";
  message: string;
}

async function performCompletion(id: string, scope: unknown): Promise<CompletionResult> {
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
      await callOmniFocus({ command: "completeProject", args: { projectId: id } }),
    );
    if (isCompletionErrorResponse(response)) {
      errors.push({ id, scope: "project", message: response.error });
    } else {
      completed.push(toCompletionSuccessEntry(id, "project", response));
    }
  } else {
    errors.push({ id, scope: "unknown", message: `Unsupported scope: ${String(scope)}` });
  }

  if (completed.length === 0 && errors.length === 0) {
    errors.push({ id, scope: "unknown", message: "No completion action performed" });
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

function isCompletionErrorResponse(value: CompletionBridgeResponse): value is CompletionErrorResponse {
  return Boolean((value as CompletionErrorResponse)?.error);
}

const tools = [
  {
    name: "taskOperations",
    description: "Manage tasks – list, get, create, update, complete, delete, move",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "get", "create", "update", "complete", "delete", "move"],
          description: "Task operation to perform",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters specific to the action",
        },
        filters: {
          type: "object",
          properties: {
            projectId: { type: "string", description: "Filter by project UUID" },
            tagId: { type: "string", description: "Filter by tag UUID" },
            includeCompleted: { type: "boolean", description: "Include completed tasks" },
            includeDropped: { type: "boolean", description: "Include dropped tasks" },
            active: { type: "boolean", description: "Filter for active tasks" },
            flagged: { type: "boolean", description: "Filter for flagged tasks" },
            limit: { type: "number", exclusiveMinimum: 0, description: "Maximum number of results" },
          },
          additionalProperties: false,
          description: "Optional filters for list operations",
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
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "taskQuery",
    description: "Query/search tasks with advanced filtering and freshness options",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query (optional)" },
        scope: {
          type: "string",
          enum: ["all", "project", "tag", "perspective"],
          description: "Optional scope for search",
        },
        searchScope: {
          type: "string",
          enum: ["nameOnly", "nameAndNotes"],
          description: "Where to search (names only vs names + notes)",
        },
        filters: {
          type: "object",
          additionalProperties: true,
          description: "Advanced filter object (dates, duration, status, tags)",
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
      additionalProperties: false,
    },
  },
  {
    name: "taskHierarchy",
    description: "Manage task hierarchy – create subtasks, flatten, move branches, restructure",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["createSubtask", "flatten", "moveBranch", "restructure"],
          description: "Hierarchy action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "projectOperations",
    description: "Manage projects – list, get, create, update, move, convert",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "get", "create", "update", "move", "convertTask"],
          description: "Project action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
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
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "projectSettings",
    description: "Update project settings – group types, completion behaviour, properties",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["setGroupType", "setCompletionBehavior", "setProperties"],
          description: "Project setting action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "folderOperations",
    description: "Manage folders – list, get, create, delete",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "get", "create", "delete"],
          description: "Folder action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "folderNavigation",
    description: "Navigate folders – get tree and validate moves",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["getTree", "validateMove"],
          description: "Navigation action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "inboxOperations",
    description: "Inbox management – list, process, get context",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "process", "getContext"],
          description: "Inbox action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "bulkInboxProcessing",
    description: "Execute batch inbox operations",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["executeBulk"],
          description: "Bulk processing action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for bulk processing",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "perspectiveOperations",
    description: "Manage perspectives – list, get, switch",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "get", "switch"],
          description: "Perspective action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
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
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "tagOperations",
    description: "Manage tags – list and query tasks by tag",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "queryTasks"],
          description: "Tag action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
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
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "validationOperations",
    description: "Validation helpers – validate transactions or moves",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["validateTransaction", "validateMove"],
          description: "Validation action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "transactionOperations",
    description: "Manage transactions – begin, execute, accept, rollback, get history",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["begin", "execute", "accept", "rollback", "rollbackRecent", "getHistory"],
          description: "Transaction action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "taskGroupOperations",
    description: "Manage task group types",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["setGroupType"],
          description: "Task group action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "reviewOperations",
    description: "Review support – list projects needing review, mark reviewed",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list", "markReviewed"],
          description: "Review action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "automationSupport",
    description: "Automation helpers – suggestions, diagnostics, cleanup",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["suggest", "diagnose", "cleanup"],
          description: "Automation support action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
        },
      },
      required: ["action"],
      additionalProperties: false,
    },
  },
  {
    name: "analyticsInsights",
    description: "Analytics insights – project health, workload, trends",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["projectHealth", "workload", "trends"],
          description: "Analytics action",
        },
        parameters: {
          type: "object",
          additionalProperties: true,
          description: "Parameters for the action",
        },
      },
      required: ["action"],
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
    description: "Mark tasks or projects as completed by ID",
    inputSchema: quickToolSchemas.markCompleted,
  },
  {
    name: "listUncompletedTasks",
    description: "List incomplete tasks with optional filters",
    inputSchema: quickToolSchemas.listUncompletedTasks,
  },
  {
    name: "listProjects",
    description: "List projects with optional grouping and detail flags",
    inputSchema: quickToolSchemas.listProjects,
  },
  {
    name: "moveTaskToProject",
    description: "Move a task into a specified project",
    inputSchema: quickToolSchemas.moveTaskToProject,
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
      const bTime = normalizeFreshnessValue(b?.modified) || normalizeFreshnessValue(b?.added);
      const aTime = normalizeFreshnessValue(a?.modified) || normalizeFreshnessValue(a?.added);
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

  const id = item.id ?? item.taskId ?? item.projectId ?? item.folderId ?? item.tagId ?? item.perspectiveId;
  if (id !== undefined) {
    minimal.id = id;
  }

  const name =
    item.name ?? item.taskName ?? item.projectName ?? item.folderName ?? item.tagName ?? item.perspectiveName;
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
  if (detailLevel === "full") {
    return data;
  }

  const apply = (item: any) => {
    if (detailLevel === "minimal") {
      return createMinimalRecord(item);
    }
    if (detailLevel === "standard") {
      return removeHeavyFields(item);
    }
    return item;
  };

  if (Array.isArray(data)) {
    return data.map(apply);
  }

  if (data && typeof data === "object" && Array.isArray((data as any).result)) {
    return { ...data, result: (data as any).result.map(apply) };
  }

  return apply(data);
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
        }))
      : base.taskIds.map((taskId: string) => ({ taskId, name: "" }));
    return { ...base, tasks };
  }

  return base;
}

class OmniFocusSimplifiedMCPServer {
  private readonly server: Server;
  private readonly transports: Record<string, StreamableHTTPServerTransport> = {};

  constructor(server: Server) {
    this.server = server;
    this.registerHandlers();
  }

  private registerHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const args = request.params.arguments ?? {};
      const toolName = request.params.name;

      if (!toolName) {
        throw new Error("tool name undefined");
      }

      let detailLevel: DetailLevel = "standard";
      let sortOrder: SortOrder = "default";
      let command: string;
      let commandArgs: any = args;

      switch (toolName) {
        case "taskOperations": {
          const { action, parameters = {}, filters = {}, detailLevel: dl, sortOrder: so } = args;
          detailLevel = getDetailLevel(dl);
          sortOrder = getSortOrder(so);
          switch (action) {
            case "list":
              command = "listRemaining";
              commandArgs = typeof filters === "object" && filters !== null ? { ...filters } : {};
              break;
            case "get":
              command = "getTask";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            case "create":
              command = "createTask";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            case "update":
              command = "updateTask";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            case "complete":
              command = "completeTask";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            case "delete":
              command = "deleteTask";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            case "move":
              command = "moveTask";
              commandArgs = parameters;
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
          const { projectId, onlyFlagged, onlyAvailable } = args;
          const rawList = normalizeResult<{ result?: any[] } | any[]>(
            await callOmniFocus({ command: "listRemaining", args: {} }),
          );
          const detailed = filterResponseByDetailLevel(rawList, "standard");
          const tasks = Array.isArray(detailed) ? detailed : detailed?.result ?? [];
          const filtered = tasks
            .filter((task: any) => {
              if (projectId && task.projectId !== projectId) {
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
           const { folderId, listProjectNames, listByFolder } = args;
          const rawProjects = normalizeResult<{ result?: any[] } | any[]>(
            await callOmniFocus({ command: "listProjects", args: {} }),
          );
          const detailed = filterResponseByDetailLevel(rawProjects, "standard");
          const projects = Array.isArray(detailed) ? detailed : detailed?.result ?? [];

          const folderLookup: Record<string, { folderId: string | null; folderName: string | null }> = {};
          const getFolderInfo = (project: any) => {
            if (project.folderId && !folderLookup[project.folderId]) {
              folderLookup[project.folderId] = {
                folderId: project.folderId,
                folderName: project.folderName ?? project.folder?.name ?? null,
              };
            }
            return folderLookup[project.folderId ?? ""] ?? {
              folderId: project.folderId ?? null,
              folderName: project.folderName ?? project.folder?.name ?? null,
            };
          };

          const includeNames = Boolean(listProjectNames);

          const projectSummaries = [] as any[];
          for (const project of projects) {
            if (folderId && (project.folderId ?? null) !== folderId) {
              continue;
            }

            const folderInfo = getFolderInfo(project);
            const taskList = includeNames
              ? normalizeResult<{ result?: any[] } | any[]>(
                  await callOmniFocus({ command: "listTasksByProject", args: { projectId: project.id ?? project.projectId } }),
                )
              : null;
            const taskItems = Array.isArray(taskList) ? taskList : taskList?.result ?? [];
            const summary = toProjectSummary(
              {
                ...project,
                folderId: folderInfo.folderId,
                folderName: folderInfo.folderName,
                tasks: taskItems,
                taskIds: taskItems.map((task: any) => task.id ?? task.taskId),
              },
              includeNames,
            );
            projectSummaries.push(summary);
          }

          if (listByFolder) {
            const grouped: Record<string, { folderId: string | null; folderName: string | null; projects: any[] }> = {};
            for (const project of projectSummaries) {
              const groupId = project.folderId ?? "__root__";
              if (!grouped[groupId]) {
                grouped[groupId] = {
                  folderId: project.folderId ?? null,
                  folderName: project.folderName ?? null,
                  projects: [],
                };
              }
              grouped[groupId].projects.push(project);
            }
            return asJsonText(Object.values(grouped));
          }

          return asJsonText(projectSummaries);
        }
        case "moveTaskToProject": {
          const { taskId, projectId } = args;
          const resolvedTaskId = requireString(taskId, "taskId");
          const resolvedProjectId = requireString(projectId, "projectId");
          const result = normalizeResult<{ error?: string }>(
            await callOmniFocus({
              command: "moveTask",
              args: { taskId: resolvedTaskId, targetProjectId: resolvedProjectId },
            }),
          );
          if (result?.error) {
            throw new Error(result.error);
          }
          return asJsonText({ taskId: resolvedTaskId, projectId: resolvedProjectId, status: "moved" });
        }
        case "taskQuery": {
          const { detailLevel: dl, sortOrder: so, query, scope, searchScope, filters = {} } = args;
          detailLevel = getDetailLevel(dl);
          sortOrder = getSortOrder(so);

          if (query) {
            command = "searchTasks";
            commandArgs = {
              query,
              ...(typeof scope === "string" ? { scope } : {}),
              ...(typeof filters === "object" && filters !== null ? filters : {}),
            };
            if (searchScope) {
              commandArgs.searchScope = searchScope;
            }
          } else {
            command = "queryTasks";
            commandArgs = {
              ...(typeof filters === "object" && filters !== null ? filters : {}),
            };
          }
          break;
        }
        case "taskHierarchy": {
          const { action, parameters = {} } = args;
          sortOrder = "default";
          switch (action) {
            case "createSubtask":
              command = "createSubtask";
              break;
            case "flatten":
              command = "flattenTaskHierarchy";
              break;
            case "moveBranch":
              command = "moveTaskBranch";
              break;
            case "restructure":
              command = "restructureTaskHierarchy";
              break;
            default:
              throw new Error(`Unknown hierarchy action: ${action}`);
          }
          commandArgs = parameters;
          break;
        }
        case "projectOperations": {
          const { action, parameters = {}, detailLevel: dl, sortOrder: so } = args;
          detailLevel = getDetailLevel(dl);
          sortOrder = getSortOrder(so);
          switch (action) {
            case "list":
              command = "listProjects";
              commandArgs = {};
              break;
            case "get":
              command = "getProjectById";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            case "create":
              command = "createProject";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            case "update":
              command = "updateProject";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            case "move":
              command = "moveProject";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            case "convertTask":
              command = "convertTaskToProject";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            default:
              throw new Error(`Unknown project action: ${action}`);
          }
          break;
        }
        case "projectSettings": {
          const { action, parameters = {} } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "setGroupType":
              command = "setProjectGroupType";
              break;
            case "setCompletionBehavior":
              command = "setProjectCompletionBehavior";
              break;
            case "setProperties":
              command = "setProjectProperties";
              break;
            default:
              throw new Error(`Unknown project settings action: ${action}`);
          }
          commandArgs = parameters;
          break;
        }
        case "folderOperations": {
          const { action, parameters = {} } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "list":
              command = "listFolders";
              commandArgs = parameters;
              break;
            case "get":
              command = "getFolderById";
              commandArgs = parameters;
              break;
            case "create":
              command = "createFolder";
              commandArgs = parameters;
              break;
            case "delete":
              command = "deleteFolder";
              commandArgs = parameters;
              break;
            default:
              throw new Error(`Unknown folder action: ${action}`);
          }
          break;
        }
        case "folderNavigation": {
          const { action, parameters = {} } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "getTree":
              command = "getProjectTree";
              commandArgs = parameters;
              break;
            case "validateMove":
              command = "validateProjectMove";
              commandArgs = parameters;
              break;
            default:
              throw new Error(`Unknown folder navigation action: ${action}`);
          }
          break;
        }
        case "inboxOperations": {
          const { action, parameters = {} } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "list":
              command = "listInbox";
              commandArgs = parameters;
              break;
            case "process":
              command = "processInboxItem";
              commandArgs = parameters;
              break;
            case "getContext":
              command = "getInboxProcessingContext";
              commandArgs = parameters;
              break;
            default:
              throw new Error(`Unknown inbox action: ${action}`);
          }
          break;
        }
        case "bulkInboxProcessing": {
          const { action, parameters = {} } = args;
          detailLevel = "standard";
          sortOrder = "default";
          if (action !== "executeBulk") {
            throw new Error(`Unknown bulk inbox action: ${action}`);
          }
          command = "executeBulkInboxProcessing";
          commandArgs = parameters;
          break;
        }
        case "perspectiveOperations": {
          const { action, parameters = {}, detailLevel: dl, sortOrder: so } = args;
          detailLevel = getDetailLevel(dl);
          sortOrder = getSortOrder(so);
          switch (action) {
            case "list":
              command = "listPerspectives";
              commandArgs = {};
              break;
            case "get":
              command = "getPerspective";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            case "switch":
              command = "switchToPerspective";
              commandArgs = parameters;
              sortOrder = "default";
              break;
            default:
              throw new Error(`Unknown perspective action: ${action}`);
          }
          break;
        }
        case "tagOperations": {
          const { action, parameters = {}, detailLevel: dl, sortOrder: so } = args;
          detailLevel = getDetailLevel(dl);
          sortOrder = getSortOrder(so);
          switch (action) {
            case "list":
              command = "listTags";
              commandArgs = {};
              break;
            case "queryTasks":
              command = "listTasksByTag";
              commandArgs = parameters;
              break;
            default:
              throw new Error(`Unknown tag action: ${action}`);
          }
          if (action !== "list") {
            sortOrder = "default";
          }
          break;
        }
        case "validationOperations": {
          const { action, parameters = {} } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "validateTransaction":
              command = "validateTransaction";
              break;
            case "validateMove":
              command = "validateProjectMove";
              break;
            default:
              throw new Error(`Unknown validation action: ${action}`);
          }
          commandArgs = parameters;
          break;
        }
        case "transactionOperations": {
          const { action, parameters = {} } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "begin":
              command = "beginTransaction";
              break;
            case "execute":
              command = "executeTransactional";
              break;
            case "accept":
              command = "acceptTransaction";
              break;
            case "rollback":
              command = "rollbackTransaction";
              break;
            case "rollbackRecent":
              command = "rollbackRecentTransaction";
              break;
            case "getHistory":
              command = "getTransactionHistory";
              break;
            default:
              throw new Error(`Unknown transaction action: ${action}`);
          }
          commandArgs = parameters;
          break;
        }
        case "taskGroupOperations": {
          const { action, parameters = {} } = args;
          detailLevel = "standard";
          sortOrder = "default";
          if (action !== "setGroupType") {
            throw new Error(`Unknown task group action: ${action}`);
          }
          command = "setTaskGroupType";
          commandArgs = parameters;
          break;
        }
        case "reviewOperations": {
          const { action, parameters = {} } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "list":
              command = "listProjectsNeedingReview";
              break;
            case "markReviewed":
              command = "markProjectReviewed";
              break;
            default:
              throw new Error(`Unknown review action: ${action}`);
          }
          commandArgs = parameters;
          break;
        }
        case "automationSupport": {
          const { action, parameters = {} } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "suggest":
              command = "suggestAutomation";
              break;
            case "diagnose":
              command = "diagnoseAutomation";
              break;
            case "cleanup":
              command = "cleanupAutomationArtifacts";
              break;
            default:
              throw new Error(`Unknown automation action: ${action}`);
          }
          commandArgs = parameters;
          break;
        }
        case "analyticsInsights": {
          const { action, parameters = {} } = args;
          detailLevel = "standard";
          sortOrder = "default";
          switch (action) {
            case "projectHealth":
              command = "getProjectHealth";
              break;
            case "workload":
              command = "getWorkloadSummary";
              break;
            case "trends":
              command = "getTrendInsights";
              break;
            default:
              throw new Error(`Unknown analytics action: ${action}`);
          }
          commandArgs = parameters;
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

      const rawResult = await callOmniFocus({ command, args: commandArgs });

      let parsedResult = rawResult;
      if (typeof rawResult === "string") {
        try {
          parsedResult = JSON.parse(rawResult);
        } catch (error) {
          console.warn("Failed to parse string result as JSON.");
        }
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

  private async streamMessages(transport: StreamableHTTPServerTransport) {
    const message: LoggingMessageNotification = {
      method: "notifications/message",
      params: { level: "info", data: "OmniFocus MCP Simplified Connection established" },
    };
    await this.sendNotification(transport, message);
  }

  private async sendNotification(
    transport: StreamableHTTPServerTransport,
    notification: Notification
  ) {
    const jsonRpcNotification: JSONRPCNotification = {
      ...notification,
      jsonrpc: JSON_RPC,
    };
    await transport.send(jsonRpcNotification);
  }

  private isInitializeRequest(body: any): boolean {
    const check = (value: any) => InitializeRequestSchema.safeParse(value).success;
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
    }
  )
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

