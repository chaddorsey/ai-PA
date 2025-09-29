import express from "express";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { CallToolRequestSchema, ListToolsRequestSchema, InitializeRequestSchema, } from "@modelcontextprotocol/sdk/types.js";
import { randomUUID } from "crypto";
import { callOmniFocus } from "./bridge.js";
const SESSION_ID_HEADER_NAME = "mcp-session-id";
const JSON_RPC = "2.0";
// Helper function to format responses
function asJsonText(body) {
    return {
        content: [
            { type: "text", text: JSON.stringify(body, null, 2) }
        ],
    };
}
// All 71 tools from the original server.ts
export const tools = [
    {
        name: "listRemaining",
        description: "Return all of your incomplete OmniFocus tasks",
        inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
        name: "getTask",
        description: "Fetch details for one task",
        inputSchema: {
            type: "object",
            properties: {
                taskId: { type: "string", description: "The task's UUID" }
            },
            required: ["taskId"],
            additionalProperties: false
        }
    },
    {
        name: "listProjects",
        description: "Return all your OmniFocus projects",
        inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
        name: "getProjectById",
        description: "Fetch details for one project",
        inputSchema: {
            type: "object",
            properties: {
                projectId: { type: "string", description: "The project's UUID" }
            },
            required: ["projectId"],
            additionalProperties: false
        }
    },
    {
        name: "listFolders",
        description: "Return all your OmniFocus folders",
        inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
        name: "getFolderById",
        description: "Fetch details for one folder",
        inputSchema: {
            type: "object",
            properties: {
                folderId: { type: "string", description: "The folder's UUID" }
            },
            required: ["folderId"],
            additionalProperties: false
        }
    },
    {
        name: "listTags",
        description: "Return all your OmniFocus tags",
        inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
        name: "listTasksByTag",
        description: "Return all tasks with a specific tag",
        inputSchema: {
            type: "object",
            properties: {
                tagId: { type: "string", description: "The tag's UUID" }
            },
            required: ["tagId"],
            additionalProperties: false
        }
    },
    {
        name: "listPerspectives",
        description: "Return all your OmniFocus perspectives",
        inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
        name: "getPerspective",
        description: "Fetch details for one perspective",
        inputSchema: {
            type: "object",
            properties: {
                perspectiveId: { type: "string", description: "The perspective's UUID" }
            },
            required: ["perspectiveId"],
            additionalProperties: false
        }
    },
    {
        name: "listInbox",
        description: "Return all tasks in your inbox",
        inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
        name: "getProjectTree",
        description: "Return the hierarchical structure of your projects",
        inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
        name: "queryTasks",
        description: "Query tasks with advanced filtering options",
        inputSchema: {
            type: "object",
            properties: {
                projectId: { type: "string", description: "Filter by project UUID" },
                tagId: { type: "string", description: "Filter by tag UUID" },
                folderId: { type: "string", description: "Filter by folder UUID" },
                perspectiveId: { type: "string", description: "Filter by perspective" },
                includeCompleted: { type: "boolean", description: "Include completed items" },
                includeDropped: { type: "boolean", description: "Include dropped/inactive items" },
                active: { type: "boolean", description: "Filter for active items" },
                flagged: { type: "boolean", description: "Filter for flagged items" },
                dueBefore: { type: "string", description: "ISO date string for due date upper bound" },
                dueAfter: { type: "string", description: "ISO date string for due date lower bound" },
                deferBefore: { type: "string", description: "ISO date string for defer date upper bound" },
                deferAfter: { type: "string", description: "ISO date string for defer date lower bound" },
                minDuration: { type: "number", exclusiveMinimum: 0, description: "Minimum estimated duration in minutes" },
                maxDuration: { type: "number", exclusiveMinimum: 0, description: "Maximum estimated duration in minutes" },
                search: { type: "string", description: "Search query for text matching" },
                fuzzy: { type: "boolean", description: "Enable fuzzy matching" },
                limit: { type: "integer", exclusiveMinimum: 0, description: "Maximum number of results" }
            },
            additionalProperties: false
        }
    },
    {
        name: "searchTasks",
        description: "Search tasks by text content",
        inputSchema: {
            type: "object",
            properties: {
                search: { type: "string", description: "Search query" },
                fuzzy: { type: "boolean", description: "Enable fuzzy matching" },
                limit: { type: "integer", exclusiveMinimum: 0, description: "Maximum number of results" }
            },
            required: ["search"],
            additionalProperties: false
        }
    },
    {
        name: "universalQuery",
        description: "Universal query tool that can search across all OmniFocus entities",
        inputSchema: {
            type: "object",
            properties: {
                search: { type: "string", description: "Search query" },
                entityTypes: {
                    type: "array",
                    items: { type: "string", enum: ["tasks", "projects", "folders", "tags", "perspectives"] },
                    description: "Types of entities to search"
                },
                limit: { type: "integer", exclusiveMinimum: 0, description: "Maximum number of results" }
            },
            required: ["search"],
            additionalProperties: false
        }
    },
    {
        name: "listTasksByProject",
        description: "Return all tasks in a specific project",
        inputSchema: {
            type: "object",
            properties: {
                projectId: { type: "string", description: "The project's UUID" }
            },
            required: ["projectId"],
            additionalProperties: false
        }
    },
    {
        name: "listTasksByPerspective",
        description: "Return all tasks matching a perspective",
        inputSchema: {
            type: "object",
            properties: {
                perspectiveId: { type: "string", description: "The perspective's UUID" }
            },
            required: ["perspectiveId"],
            additionalProperties: false
        }
    },
    {
        name: "getProjectsByFolder",
        description: "Return all projects in a specific folder",
        inputSchema: {
            type: "object",
            properties: {
                folderId: { type: "string", description: "The folder's UUID" }
            },
            required: ["folderId"],
            additionalProperties: false
        }
    },
    {
        name: "createTask",
        description: "Create a new task",
        inputSchema: {
            type: "object",
            properties: {
                name: { type: "string", description: "Task name" },
                note: { type: "string", description: "Task note" },
                projectId: { type: "string", description: "Parent project UUID" },
                dueDate: { type: "string", description: "Due date (ISO string)" },
                deferDate: { type: "string", description: "Defer date (ISO string)" },
                duration: { type: "number", description: "Estimated duration in minutes" },
                flagged: { type: "boolean", description: "Whether task is flagged" }
            },
            required: ["name"],
            additionalProperties: false
        }
    },
    {
        name: "updateTask",
        description: "Update an existing task",
        inputSchema: {
            type: "object",
            properties: {
                taskId: { type: "string", description: "The task's UUID" },
                name: { type: "string", description: "Task name" },
                note: { type: "string", description: "Task note" },
                projectId: { type: "string", description: "Parent project UUID" },
                dueDate: { type: "string", description: "Due date (ISO string)" },
                deferDate: { type: "string", description: "Defer date (ISO string)" },
                duration: { type: "number", description: "Estimated duration in minutes" },
                flagged: { type: "boolean", description: "Whether task is flagged" }
            },
            required: ["taskId"],
            additionalProperties: false
        }
    },
    {
        name: "deleteTask",
        description: "Delete a task",
        inputSchema: {
            type: "object",
            properties: {
                taskId: { type: "string", description: "The task's UUID" }
            },
            required: ["taskId"],
            additionalProperties: false
        }
    },
    {
        name: "completeTask",
        description: "Mark a task as complete",
        inputSchema: {
            type: "object",
            properties: {
                taskId: { type: "string", description: "The task's UUID" }
            },
            required: ["taskId"],
            additionalProperties: false
        }
    },
    {
        name: "moveTask",
        description: "Move a task to a different project",
        inputSchema: {
            type: "object",
            properties: {
                taskId: { type: "string", description: "The task's UUID" },
                projectId: { type: "string", description: "Target project UUID" }
            },
            required: ["taskId", "projectId"],
            additionalProperties: false
        }
    },
    {
        name: "createProject",
        description: "Create a new project",
        inputSchema: {
            type: "object",
            properties: {
                name: { type: "string", description: "Project name" },
                note: { type: "string", description: "Project note" },
                folderId: { type: "string", description: "Parent folder UUID" },
                status: { type: "string", enum: ["active", "onHold", "dropped"], description: "Project status" }
            },
            required: ["name"],
            additionalProperties: false
        }
    },
    {
        name: "updateProject",
        description: "Update an existing project",
        inputSchema: {
            type: "object",
            properties: {
                projectId: { type: "string", description: "The project's UUID" },
                name: { type: "string", description: "Project name" },
                note: { type: "string", description: "Project note" },
                folderId: { type: "string", description: "Parent folder UUID" },
                status: { type: "string", enum: ["active", "onHold", "dropped"], description: "Project status" }
            },
            required: ["projectId"],
            additionalProperties: false
        }
    },
    {
        name: "moveProject",
        description: "Move a project to a different folder",
        inputSchema: {
            type: "object",
            properties: {
                projectId: { type: "string", description: "The project's UUID" },
                folderId: { type: "string", description: "Target folder UUID" }
            },
            required: ["projectId", "folderId"],
            additionalProperties: false
        }
    },
    {
        name: "convertTaskToProject",
        description: "Convert a task to a project",
        inputSchema: {
            type: "object",
            properties: {
                taskId: { type: "string", description: "The task's UUID" }
            },
            required: ["taskId"],
            additionalProperties: false
        }
    },
    {
        name: "setProjectProperties",
        description: "Set various properties on a project",
        inputSchema: {
            type: "object",
            properties: {
                projectId: { type: "string", description: "The project's UUID" },
                properties: { type: "object", description: "Properties to set" }
            },
            required: ["projectId", "properties"],
            additionalProperties: false
        }
    },
    {
        name: "createFolder",
        description: "Create a new folder",
        inputSchema: {
            type: "object",
            properties: {
                name: { type: "string", description: "Folder name" },
                note: { type: "string", description: "Folder note" }
            },
            required: ["name"],
            additionalProperties: false
        }
    },
    {
        name: "deleteFolder",
        description: "Delete a folder",
        inputSchema: {
            type: "object",
            properties: {
                folderId: { type: "string", description: "The folder's UUID" }
            },
            required: ["folderId"],
            additionalProperties: false
        }
    },
    {
        name: "validateProjectMove",
        description: "Validate if a project can be moved to a folder",
        inputSchema: {
            type: "object",
            properties: {
                projectId: { type: "string", description: "The project's UUID" },
                folderId: { type: "string", description: "Target folder UUID" }
            },
            required: ["projectId", "folderId"],
            additionalProperties: false
        }
    },
    {
        name: "processInboxItem",
        description: "Process a single inbox item",
        inputSchema: {
            type: "object",
            properties: {
                taskId: { type: "string", description: "The inbox task's UUID" },
                action: { type: "string", enum: ["convert", "delete", "defer"], description: "Action to take" },
                parameters: { type: "object", description: "Action-specific parameters" }
            },
            required: ["taskId", "action"],
            additionalProperties: false
        }
    },
    {
        name: "executeBulkInboxProcessing",
        description: "Process multiple inbox items in bulk",
        inputSchema: {
            type: "object",
            properties: {
                items: {
                    type: "array",
                    items: {
                        type: "object",
                        properties: {
                            taskId: { type: "string" },
                            action: { type: "string", enum: ["convert", "delete", "defer"] },
                            parameters: { type: "object" }
                        },
                        required: ["taskId", "action"]
                    }
                }
            },
            required: ["items"],
            additionalProperties: false
        }
    },
    {
        name: "getInboxProcessingContext",
        description: "Get context information for inbox processing",
        inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
        name: "createSubtask",
        description: "Create a subtask under an existing task",
        inputSchema: {
            type: "object",
            properties: {
                parentTaskId: { type: "string", description: "Parent task UUID" },
                name: { type: "string", description: "Subtask name" },
                note: { type: "string", description: "Subtask note" }
            },
            required: ["parentTaskId", "name"],
            additionalProperties: false
        }
    },
    {
        name: "flattenTaskHierarchy",
        description: "Flatten a task hierarchy by promoting subtasks",
        inputSchema: {
            type: "object",
            properties: {
                taskId: { type: "string", description: "Root task UUID" }
            },
            required: ["taskId"],
            additionalProperties: false
        }
    },
    {
        name: "moveTaskBranch",
        description: "Move an entire task branch to a different project",
        inputSchema: {
            type: "object",
            properties: {
                taskId: { type: "string", description: "Root task UUID" },
                projectId: { type: "string", description: "Target project UUID" }
            },
            required: ["taskId", "projectId"],
            additionalProperties: false
        }
    },
    {
        name: "restructureTaskHierarchy",
        description: "Restructure a task hierarchy",
        inputSchema: {
            type: "object",
            properties: {
                taskId: { type: "string", description: "Root task UUID" },
                structure: { type: "object", description: "New hierarchy structure" }
            },
            required: ["taskId", "structure"],
            additionalProperties: false
        }
    },
    {
        name: "switchToPerspective",
        description: "Switch to a specific perspective",
        inputSchema: {
            type: "object",
            properties: {
                perspectiveId: { type: "string", description: "The perspective's UUID" }
            },
            required: ["perspectiveId"],
            additionalProperties: false
        }
    },
    {
        name: "setProjectGroupType",
        description: "Set the group type for a project",
        inputSchema: {
            type: "object",
            properties: {
                projectId: { type: "string", description: "The project's UUID" },
                groupType: { type: "string", enum: ["sequential", "parallel"], description: "Group type" }
            },
            required: ["projectId", "groupType"],
            additionalProperties: false
        }
    },
    {
        name: "setProjectCompletionBehavior",
        description: "Set completion behavior for a project",
        inputSchema: {
            type: "object",
            properties: {
                projectId: { type: "string", description: "The project's UUID" },
                behavior: { type: "string", enum: ["automatic", "manual"], description: "Completion behavior" }
            },
            required: ["projectId", "behavior"],
            additionalProperties: false
        }
    },
    {
        name: "setTaskGroupType",
        description: "Set the group type for a task",
        inputSchema: {
            type: "object",
            properties: {
                taskId: { type: "string", description: "The task's UUID" },
                groupType: { type: "string", enum: ["sequential", "parallel"], description: "Group type" }
            },
            required: ["taskId", "groupType"],
            additionalProperties: false
        }
    },
    {
        name: "beginTransaction",
        description: "Begin a transaction for batch operations",
        inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
        name: "executeTransactional",
        description: "Execute operations within a transaction",
        inputSchema: {
            type: "object",
            properties: {
                operations: { type: "array", items: { type: "object" } }
            },
            required: ["operations"],
            additionalProperties: false
        }
    },
    {
        name: "acceptTransaction",
        description: "Accept and commit a transaction",
        inputSchema: {
            type: "object",
            properties: {
                transactionId: { type: "string", description: "Transaction ID" }
            },
            required: ["transactionId"],
            additionalProperties: false
        }
    },
    {
        name: "rollbackTransaction",
        description: "Rollback a transaction",
        inputSchema: {
            type: "object",
            properties: {
                transactionId: { type: "string", description: "Transaction ID" }
            },
            required: ["transactionId"],
            additionalProperties: false
        }
    },
    {
        name: "rollbackRecentTransaction",
        description: "Rollback the most recent transaction",
        inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
        name: "getTransactionHistory",
        description: "Get history of transactions",
        inputSchema: { type: "object", properties: {}, additionalProperties: false }
    },
    {
        name: "validateTransaction",
        description: "Validate a transaction before execution",
        inputSchema: {
            type: "object",
            properties: {
                operations: { type: "array", items: { type: "object" } }
            },
            required: ["operations"],
            additionalProperties: false
        }
    }
];
export class OmniFocusFullMCPServer {
    server;
    // to support multiple simultaneous connections
    transports = {};
    constructor(server) {
        this.server = server;
        this.setupTools();
    }
    async handleGetRequest(req, res) {
        const sessionId = req.headers["mcp-session-id"];
        if (!sessionId || !this.transports[sessionId]) {
            res
                .status(400)
                .json(this.createErrorResponse("Bad Request: invalid session ID or method."));
            return;
        }
        console.log(`Establishing SSE stream for session ${sessionId}`);
        const transport = this.transports[sessionId];
        await transport.handleRequest(req, res);
        await this.streamMessages(transport);
        return;
    }
    async handlePostRequest(req, res) {
        const sessionId = req.headers[SESSION_ID_HEADER_NAME];
        let transport;
        try {
            // reuse existing transport
            if (sessionId && this.transports[sessionId]) {
                transport = this.transports[sessionId];
                await transport.handleRequest(req, res, req.body);
                return;
            }
            // create new transport
            if (!sessionId && this.isInitializeRequest(req.body)) {
                const transport = new StreamableHTTPServerTransport({
                    sessionIdGenerator: () => randomUUID(),
                });
                await this.server.connect(transport);
                await transport.handleRequest(req, res, req.body);
                // session ID will only be available (if in not Stateless-Mode)
                // after handling the first request
                const sessionId = transport.sessionId;
                if (sessionId) {
                    this.transports[sessionId] = transport;
                }
                return;
            }
            res
                .status(400)
                .json(this.createErrorResponse("Bad Request: invalid session ID or method."));
            return;
        }
        catch (error) {
            console.error("Error handling MCP request:", error);
            res.status(500).json(this.createErrorResponse("Internal server error."));
            return;
        }
    }
    async cleanup() {
        await this.server.close();
    }
    setupTools() {
        // Define available tools
        const setToolSchema = () => this.server.setRequestHandler(ListToolsRequestSchema, async () => {
            return { tools };
        });
        setToolSchema();
        // handle tool calls
        this.server.setRequestHandler(CallToolRequestSchema, async (request, extra) => {
            const args = request.params.arguments;
            const toolName = request.params.name;
            console.log("Received request for tool:", toolName, args);
            if (!args) {
                throw new Error("arguments undefined");
            }
            if (!toolName) {
                throw new Error("tool name undefined");
            }
            // Execute the tool by calling OmniFocus with the tool name as command
            const result = await callOmniFocus({ command: toolName, args });
            return asJsonText(result);
        });
    }
    // send message streaming message every second
    async streamMessages(transport) {
        try {
            // based on LoggingMessageNotificationSchema to trigger setNotificationHandler on client
            const message = {
                method: "notifications/message",
                params: { level: "info", data: "OmniFocus MCP Full Connection established" },
            };
            this.sendNotification(transport, message);
            let messageCount = 0;
            const interval = setInterval(async () => {
                messageCount++;
                const data = `OmniFocus MCP Full Message ${messageCount} at ${new Date().toISOString()}`;
                const message = {
                    method: "notifications/message",
                    params: { level: "info", data: data },
                };
                try {
                    this.sendNotification(transport, message);
                    if (messageCount === 2) {
                        clearInterval(interval);
                        const message = {
                            method: "notifications/message",
                            params: { level: "info", data: "OmniFocus MCP Full Streaming complete!" },
                        };
                        this.sendNotification(transport, message);
                    }
                }
                catch (error) {
                    console.error("Error sending message:", error);
                    clearInterval(interval);
                }
            }, 1000);
        }
        catch (error) {
            console.error("Error sending message:", error);
        }
    }
    async sendNotification(transport, notification) {
        const rpcNotificaiton = {
            ...notification,
            jsonrpc: JSON_RPC,
        };
        await transport.send(rpcNotificaiton);
    }
    createErrorResponse(message) {
        return {
            jsonrpc: "2.0",
            error: {
                code: -32000,
                message: message,
            },
            id: randomUUID(),
        };
    }
    isInitializeRequest(body) {
        const isInitial = (data) => {
            const result = InitializeRequestSchema.safeParse(data);
            return result.success;
        };
        if (Array.isArray(body)) {
            return body.some((request) => isInitial(request));
        }
        return isInitial(body);
    }
}
// Default port
let PORT = 8124;
// Parse command-line arguments for --port=XXXX
for (let i = 2; i < process.argv.length; i++) {
    const arg = process.argv[i];
    if (arg.startsWith("--port=")) {
        const value = parseInt(arg.split("=")[1], 10);
        if (!isNaN(value)) {
            PORT = value;
        }
        else {
            console.error("Invalid value for --port");
            process.exit(1);
        }
    }
}
const server = new OmniFocusFullMCPServer(new Server({
    name: "omnifocus-full-mcp",
    version: "1.0.0",
}, {
    capabilities: {
        tools: {},
        logging: {},
    },
}));
const app = express();
app.use(express.json());
const router = express.Router();
// single endpoint for the client to send messages to
const MCP_ENDPOINT = "/mcp";
router.post(MCP_ENDPOINT, async (req, res) => {
    await server.handlePostRequest(req, res);
});
router.get(MCP_ENDPOINT, async (req, res) => {
    await server.handleGetRequest(req, res);
});
app.use("/", router);
app.listen(PORT, () => {
    console.log(`🚀 OmniFocus MCP Full Streamable HTTP Server listening on port ${PORT}`);
    console.log(`   Main endpoint: http://localhost:${PORT}/mcp`);
    console.log(`   Network accessible: http://192.168.7.114:${PORT}/mcp`);
    console.log(`   Available tools: ${tools.length} tools (full feature set)`);
});
process.on("SIGINT", async () => {
    console.log("Shutting down server...");
    await server.cleanup();
    process.exit(0);
});
