import express, { Request, Response } from "express";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  CallToolRequestSchema,
  InitializeRequestSchema,
  JSONRPCNotification,
  ListToolsRequestSchema,
  LoggingMessageNotification,
  Notification,
} from "@modelcontextprotocol/sdk/types.js";
import { randomUUID } from "node:crypto";

import { callOmniFocus } from "./bridge.js";
import { tools as fullTools } from "./server-mcp-full-8124.js";

const SESSION_ID_HEADER_NAME = "mcp-session-id";
const JSON_RPC = "2.0";

const tools = fullTools;

function asJsonText(body: unknown) {
  return {
    content: [{ type: "text", text: JSON.stringify(body, null, 2) }],
  };
}

class OmniFocusFullMCPServer {
  private readonly server: Server;
  private readonly transports: Record<string, StreamableHTTPServerTransport> = {};

  constructor(server: Server) {
    this.server = server;
    this.setupTools();
  }

  async handleGetRequest(req: Request, res: Response) {
    const sessionId = req.headers[SESSION_ID_HEADER_NAME] as string | undefined;
    if (!sessionId || !this.transports[sessionId]) {
      res.sendStatus(400);
      return;
    }

    const transport = this.transports[sessionId];
    await transport.handleRequest(req, res);
    await this.streamMessages(transport);
  }

  async handlePostRequest(req: Request, res: Response) {
    const sessionId = req.headers[SESSION_ID_HEADER_NAME] as string | undefined;
    const payload = this.normalizeIncomingMessage(req.body);

    try {
      if (sessionId && this.transports[sessionId]) {
        const transport = this.transports[sessionId];
        await transport.handleRequest(req, res, payload);
        return;
      }

      if (!sessionId && this.isInitializeRequest(payload)) {
        const transport = new StreamableHTTPServerTransport({
          sessionIdGenerator: () => randomUUID(),
        });

        await this.server.connect(transport);
        await transport.handleRequest(req, res, payload);

        const newSessionId = transport.sessionId;
        if (newSessionId) {
          this.transports[newSessionId] = transport;
        }
        return;
      }

      res.sendStatus(400);
    } catch (error) {
      console.error("Error handling full MCP request:", error);
      res.sendStatus(500);
    }
  }

  async cleanup() {
    await this.server.close();
  }

  private setupTools() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;
      if (!name || !args) {
        throw new Error("Missing tool name or arguments");
      }

      const result = await callOmniFocus({ command: name, args });
      return asJsonText(result);
    });
  }

  private async streamMessages(transport: StreamableHTTPServerTransport) {
    const log = async (data: string) => {
      const message: LoggingMessageNotification = {
        method: "notifications/message",
        params: { level: "info", data },
      };
      await this.sendNotification(transport, message);
    };

    await log("OmniFocus MCP full tool connection established");
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

const app = express();
app.use(express.json());

const fullServer = new OmniFocusFullMCPServer(
  new Server(
    {
      name: "omnifocus-full-mcp",
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

const MCP_ENDPOINT = "/mcp";

app.post(MCP_ENDPOINT, async (req: Request, res: Response) => {
  await fullServer.handlePostRequest(req, res);
});

app.get(MCP_ENDPOINT, async (req: Request, res: Response) => {
  await fullServer.handleGetRequest(req, res);
});

app.get("/health", (_req, res) => {
  res.json({ status: "healthy", mode: "full", toolCount: tools.length });
});

const PORT = Number.parseInt(process.env.PORT ?? "8890", 10);

const serverHandle = app.listen(PORT, () => {
  console.log(`🚀 OmniFocus full MCP (HTTP) listening on port ${PORT}`);
});

const shutdown = async () => {
  await fullServer.cleanup();
  serverHandle.close(() => process.exit(0));
};

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

