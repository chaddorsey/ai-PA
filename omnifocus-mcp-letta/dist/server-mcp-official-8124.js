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
export class OmniFocusMCPServer {
    server;
    // to support multiple simultaneous connections
    transports = {};
    toolInterval;
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
        this.toolInterval?.close();
        await this.server.close();
    }
    setupTools() {
        // Define available tools
        const setToolSchema = () => this.server.setRequestHandler(ListToolsRequestSchema, async () => {
            const tools = [
                {
                    name: "query",
                    description: "Query and read data from OmniFocus - tasks, projects, folders, tags, perspectives, inbox",
                    inputSchema: {
                        type: "object",
                        properties: {
                            type: {
                                type: "string",
                                enum: ["tasks", "projects", "folders", "tags", "perspectives", "inbox", "hierarchy", "remaining", "task", "project", "folder", "tag", "perspective"],
                                description: "Type of data to query"
                            },
                            filters: {
                                type: "object",
                                properties: {
                                    taskId: { type: "string", description: "Specific task UUID" },
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
                                    limit: { type: "integer", exclusiveMinimum: 0, description: "Maximum number of results" },
                                    maxResults: { type: "integer", exclusiveMinimum: 0, description: "Maximum number of results" }
                                },
                                additionalProperties: false,
                                description: "Optional filters and search parameters"
                            }
                        },
                        required: ["type"],
                        additionalProperties: false
                    }
                },
                {
                    name: "execute",
                    description: "Execute operations on OmniFocus - create, update, delete, move, process items, manage transactions",
                    inputSchema: {
                        type: "object",
                        properties: {
                            operation: {
                                type: "string",
                                enum: [
                                    "createTask", "updateTask", "deleteTask", "completeTask", "moveTask",
                                    "createProject", "updateProject", "moveProject", "convertTaskToProject", "setProjectProperties",
                                    "createFolder", "deleteFolder", "moveProject", "validateProjectMove",
                                    "processInboxItem", "executeBulkInboxProcessing", "getInboxProcessingContext",
                                    "createSubtask", "flattenTaskHierarchy", "moveTaskBranch", "restructureTaskHierarchy",
                                    "switchToPerspective", "setProjectGroupType", "setProjectCompletionBehavior", "setTaskGroupType",
                                    "beginTransaction", "executeTransactional", "acceptTransaction", "rollbackTransaction", "rollbackRecentTransaction",
                                    "getTransactionHistory", "validateTransaction"
                                ],
                                description: "The operation to execute"
                            },
                            parameters: {
                                type: "object",
                                additionalProperties: true,
                                description: "Parameters for the operation"
                            }
                        },
                        required: ["operation"],
                        additionalProperties: false
                    }
                },
                {
                    name: "omnifocus",
                    description: "Universal OmniFocus tool - handles any OmniFocus operation with intelligent routing and natural language processing",
                    inputSchema: {
                        type: "object",
                        properties: {
                            action: {
                                type: "string",
                                description: "The action to perform (e.g., 'list tasks', 'create project', 'process inbox', 'get flagged tasks')"
                            },
                            parameters: {
                                type: "object",
                                additionalProperties: true,
                                description: "Parameters for the action"
                            },
                            context: {
                                type: "object",
                                properties: {
                                    entityType: {
                                        type: "string",
                                        enum: ["task", "project", "folder", "tag", "perspective", "inbox"],
                                        description: "Type of entity being operated on"
                                    },
                                    operationType: {
                                        type: "string",
                                        enum: ["create", "read", "update", "delete", "move", "process", "query", "transaction"],
                                        description: "Type of operation"
                                    },
                                    scope: {
                                        type: "string",
                                        enum: ["single", "multiple", "bulk", "hierarchy"],
                                        description: "Scope of the operation"
                                    }
                                },
                                additionalProperties: false,
                                description: "Context hints to help route the request"
                            }
                        },
                        required: ["action"],
                        additionalProperties: false
                    }
                }
            ];
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
            // Tool execution logic
            const { type, filters = {}, operation, parameters = {}, action, context = {} } = args;
            let command;
            let commandArgs = {
                ...(typeof parameters === 'object' && parameters !== null ? parameters : {}),
                ...(typeof filters === 'object' && filters !== null ? filters : {})
            };
            switch (toolName) {
                case "query":
                    switch (type) {
                        case "tasks":
                            command = "universalQuery";
                            if (typeof filters === 'object' && filters !== null && 'search' in filters) {
                                commandArgs.search = filters.search;
                            }
                            break;
                        case "remaining":
                            command = "listRemaining";
                            break;
                        case "task":
                            command = "getTask";
                            if (typeof filters === 'object' && filters !== null && 'taskId' in filters) {
                                commandArgs.taskId = filters.taskId;
                            }
                            break;
                        case "projects":
                            command = "listProjects";
                            break;
                        case "project":
                            command = "getProjectById";
                            if (typeof filters === 'object' && filters !== null && 'projectId' in filters) {
                                commandArgs.projectId = filters.projectId;
                            }
                            break;
                        case "folders":
                            command = "listFolders";
                            break;
                        case "folder":
                            command = "getFolderById";
                            if (typeof filters === 'object' && filters !== null && 'folderId' in filters) {
                                commandArgs.folderId = filters.folderId;
                            }
                            break;
                        case "tags":
                            command = "listTags";
                            break;
                        case "tag":
                            command = "listTasksByTag";
                            if (typeof filters === 'object' && filters !== null && 'tagId' in filters) {
                                commandArgs.tagId = filters.tagId;
                            }
                            break;
                        case "perspectives":
                            command = "listPerspectives";
                            break;
                        case "perspective":
                            command = "getPerspective";
                            if (typeof filters === 'object' && filters !== null && 'perspectiveId' in filters) {
                                commandArgs.perspectiveId = filters.perspectiveId;
                            }
                            break;
                        case "inbox":
                            command = "listInbox";
                            break;
                        case "hierarchy":
                            command = "getProjectTree";
                            break;
                        default:
                            throw new Error(`Unknown query type: ${type}`);
                    }
                    break;
                case "execute":
                    command = typeof operation === 'string' ? operation : 'unknown';
                    commandArgs = typeof parameters === 'object' && parameters !== null ? parameters : {};
                    break;
                case "omnifocus":
                    // Intelligent routing based on action
                    const actionLower = typeof action === 'string' ? action.toLowerCase() : '';
                    if (actionLower.includes("list") || actionLower.includes("get") || actionLower.includes("query") || actionLower.includes("show")) {
                        if (actionLower.includes("task")) {
                            if (actionLower.includes("remaining") || actionLower.includes("incomplete")) {
                                command = "listRemaining";
                            }
                            else if (actionLower.includes("search") || actionLower.includes("find")) {
                                command = "searchTasks";
                            }
                            else if (actionLower.includes("universal") || actionLower.includes("advanced")) {
                                command = "universalQuery";
                            }
                            else if (actionLower.includes("flagged")) {
                                command = "queryTasks";
                                commandArgs.flagged = true;
                            }
                            else if (actionLower.includes("by tag")) {
                                command = "listTasksByTag";
                            }
                            else if (actionLower.includes("by project")) {
                                command = "listTasksByProject";
                            }
                            else if (actionLower.includes("by perspective")) {
                                command = "listTasksByPerspective";
                            }
                            else {
                                command = "queryTasks";
                            }
                        }
                        else if (actionLower.includes("project")) {
                            if (actionLower.includes("hierarchy") || actionLower.includes("tree")) {
                                command = "getProjectTree";
                            }
                            else if (actionLower.includes("by folder")) {
                                command = "getProjectsByFolder";
                            }
                            else {
                                command = "listProjects";
                            }
                        }
                        else if (actionLower.includes("folder")) {
                            command = "listFolders";
                        }
                        else if (actionLower.includes("tag")) {
                            command = "listTags";
                        }
                        else if (actionLower.includes("perspective")) {
                            command = "listPerspectives";
                        }
                        else if (actionLower.includes("inbox")) {
                            command = "listInbox";
                        }
                        else {
                            command = "universalQuery";
                        }
                    }
                    else if (actionLower.includes("create")) {
                        if (actionLower.includes("task")) {
                            command = "createTask";
                        }
                        else if (actionLower.includes("project")) {
                            command = "createProject";
                        }
                        else if (actionLower.includes("folder")) {
                            command = "createFolder";
                        }
                        else if (actionLower.includes("subtask")) {
                            command = "createSubtask";
                        }
                        else {
                            throw new Error(`Unknown create operation: ${action}`);
                        }
                    }
                    else if (actionLower.includes("update") || actionLower.includes("modify") || actionLower.includes("set")) {
                        if (actionLower.includes("task")) {
                            command = "updateTask";
                        }
                        else if (actionLower.includes("project")) {
                            command = "setProjectProperties";
                        }
                        else {
                            throw new Error(`Unknown update operation: ${action}`);
                        }
                    }
                    else if (actionLower.includes("delete")) {
                        if (actionLower.includes("task")) {
                            command = "deleteTask";
                        }
                        else if (actionLower.includes("folder")) {
                            command = "deleteFolder";
                        }
                        else {
                            throw new Error(`Unknown delete operation: ${action}`);
                        }
                    }
                    else if (actionLower.includes("complete") || actionLower.includes("finish")) {
                        command = "completeTask";
                    }
                    else if (actionLower.includes("move")) {
                        if (actionLower.includes("task")) {
                            command = "moveTask";
                        }
                        else if (actionLower.includes("project")) {
                            command = "moveProject";
                        }
                        else if (actionLower.includes("branch")) {
                            command = "moveTaskBranch";
                        }
                        else {
                            command = "moveTask";
                        }
                    }
                    else if (actionLower.includes("process") && actionLower.includes("inbox")) {
                        if (actionLower.includes("bulk")) {
                            command = "executeBulkInboxProcessing";
                        }
                        else if (actionLower.includes("context")) {
                            command = "getInboxProcessingContext";
                        }
                        else {
                            command = "processInboxItem";
                        }
                    }
                    else if (actionLower.includes("switch") && actionLower.includes("perspective")) {
                        command = "switchToPerspective";
                    }
                    else if (actionLower.includes("flatten")) {
                        command = "flattenTaskHierarchy";
                    }
                    else if (actionLower.includes("restructure")) {
                        command = "restructureTaskHierarchy";
                    }
                    else if (actionLower.includes("convert") && actionLower.includes("project")) {
                        command = "convertTaskToProject";
                    }
                    else if (actionLower.includes("transaction")) {
                        if (actionLower.includes("begin")) {
                            command = "beginTransaction";
                        }
                        else if (actionLower.includes("execute")) {
                            command = "executeTransactional";
                        }
                        else if (actionLower.includes("rollback")) {
                            command = "rollbackRecentTransaction";
                        }
                        else {
                            command = "getTransactionHistory";
                        }
                    }
                    else {
                        // Try to use the action as a direct command
                        command = typeof action === 'string' ? action : 'unknown';
                    }
                    break;
                default:
                    throw new Error(`Unknown tool: ${toolName}`);
            }
            const result = await callOmniFocus({ command, args: commandArgs });
            return asJsonText(result);
        });
    }
    // send message streaming message every second
    async streamMessages(transport) {
        try {
            // based on LoggingMessageNotificationSchema to trigger setNotificationHandler on client
            const message = {
                method: "notifications/message",
                params: { level: "info", data: "OmniFocus MCP Connection established" },
            };
            this.sendNotification(transport, message);
            let messageCount = 0;
            const interval = setInterval(async () => {
                messageCount++;
                const data = `OmniFocus MCP Message ${messageCount} at ${new Date().toISOString()}`;
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
                            params: { level: "info", data: "OmniFocus MCP Streaming complete!" },
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
const server = new OmniFocusMCPServer(new Server({
    name: "omnifocus-mcp",
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
    console.log(`🚀 OmniFocus MCP Streamable HTTP Server listening on port ${PORT}`);
    console.log(`   Main endpoint: http://localhost:${PORT}/mcp`);
    console.log(`   Network accessible: http://192.168.7.114:${PORT}/mcp`);
    console.log(`   Available tools: query, execute, omnifocus`);
});
process.on("SIGINT", async () => {
    console.log("Shutting down server...");
    await server.cleanup();
    process.exit(0);
});
