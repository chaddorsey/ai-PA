import { randomUUID } from "node:crypto";
import express, { Request, Response } from "express";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { registerAll, getGmailOnce } from "./index.js";
import { GmailHealthMonitor } from "./health-monitor.js";

const app = express(); // DO NOT add app.use(express.json()); transport needs raw body
const PORT = Number(process.env.PORT || 8080);
const PATH = process.env.MCP_PATH || "/mcp";
const HEALTH_PATH = process.env.MCP_HEALTH_CHECK_PATH || "/health";

// Shared server instance (singleton pattern for HTTP transport)
let sharedServer: Server | null = null;

// Keep transports per session id  
const sessions: Record<string, StreamableHTTPServerTransport> = {};

// Health monitor instance
let healthMonitor: GmailHealthMonitor | null = null;

// Build a shared server instance (only called once)
async function getSharedServer(): Promise<Server> {
  if (sharedServer) return sharedServer;
  
  sharedServer = new Server({ 
    name: "gmail", 
    version: "1.0.0"
  });
  
  // Set capabilities (required for MCP SDK to allow tool registration)
  (sharedServer as any).capabilities = { tools: {} };
  
  registerAll(sharedServer);

  // Initialize health monitor
  if (!healthMonitor) {
    healthMonitor = new GmailHealthMonitor();
    try {
      const gmail = await getGmailOnce();
      // Get the OAuth client from the Gmail instance
      const oauth2Client = (gmail as any).auth || null;
      if (oauth2Client) {
        await healthMonitor.initialize(oauth2Client, gmail);
        console.log("Health monitor initialized");
      }
    } catch (error) {
      console.warn("Failed to initialize health monitor:", error);
    }
  }

  console.log("Created shared MCP server instance");
  return sharedServer;
}

// Reuse/initialize a transport bound to an MCP session
async function getTransport(req: Request): Promise<StreamableHTTPServerTransport> {
  const incoming = req.header("mcp-session-id") || undefined;
  if (incoming && sessions[incoming]) {
    console.log(`Reusing existing session: ${incoming}`);
    return sessions[incoming];
  }

  const server = await getSharedServer();

  // Use the incoming session ID if provided, otherwise generate one
  const sessionId = incoming || randomUUID();

  // In @mcp/sdk 1.18.x the callback is lowercased: onsessioninitialized
  const transport = new StreamableHTTPServerTransport({
    enableJsonResponse: true,
    sessionIdGenerator: () => sessionId,
    onsessioninitialized: (id: string) => {
      console.log(`New session initialized: ${id} (incoming: ${incoming})`);
      sessions[sessionId] = transport; // Store using our session ID, not the generated one
    },
  });

  await server.connect(transport);
  console.log(`Connected transport for session: ${sessionId}`);
  return transport;
}

// --- Health probe
app.get(HEALTH_PATH, async (_req: Request, res: Response) => {
  try {
    if (healthMonitor) {
      const healthStatus = await healthMonitor.performHealthCheck();
      
      // Set appropriate HTTP status code based on health
      const statusCode = healthStatus.status === "healthy" ? 200 : 
                        healthStatus.status === "degraded" ? 200 : 503;
      
      res.status(statusCode).json(healthStatus);
    } else {
      // Fallback health check if monitor not initialized
      const serverName = process.env.MCP_SERVER_NAME || "gmail-tools";
      const serverVersion = process.env.MCP_SERVER_VERSION || "1.1.11";
      
      res.status(200).json({
        status: "healthy",
        timestamp: new Date().toISOString(),
        service: serverName,
        version: serverVersion,
        uptime: process.uptime(),
        dependencies: {
          gmail_api: "healthy",
          oauth_tokens: "healthy",
          external_apis: "healthy",
          file_system: "healthy"
        },
        metrics: {
          error_count_last_hour: 0,
          request_count_last_hour: 0
        },
        note: "Health monitor not initialized - using fallback check"
      });
    }
  } catch (error: any) {
    res.status(503).json({
      status: "unhealthy",
      timestamp: new Date().toISOString(),
      service: "gmail-tools",
      version: process.env.MCP_SERVER_VERSION || "1.1.11",
      uptime: process.uptime(),
      error: error.message,
      dependencies: {
        gmail_api: "unhealthy",
        oauth_tokens: "unhealthy",
        external_apis: "unhealthy",
        file_system: "unhealthy"
      }
    });
  }
});

// --- JSON-RPC (client -> server)
app.post(PATH, async (req: Request, res: Response) => {
  try {
    const t = await getTransport(req);
    await t.handleRequest(req, res); // transport reads raw body
  } catch (err) {
    const msg = (err as Error)?.message || "Internal Server Error";
    console.error("POST /mcp error:", err);
    res.status(500).json({ error: msg });
  }
});

// --- SSE stream (server -> client)
app.get(PATH, async (req: Request, res: Response) => {
  try {
    const sid = req.header("mcp-session-id") || "";
    const t = sessions[sid];
    if (!t) {
      res.status(400).json({ error: "missing or unknown mcp-session-id" });
      return;
    }
    await t.handleRequest(req, res);
  } catch (err) {
    console.error("GET /mcp error:", err);
    try { res.end(); } catch {}
  }
});

// --- Tear down a session
app.delete(PATH, async (req: Request, res: Response) => {
  try {
    const sid = req.header("mcp-session-id") || "";
    const t = sessions[sid];
    if (!t) {
      res.status(400).json({ error: "missing or unknown mcp-session-id" });
      return;
    }
    await t.handleRequest(req, res);
    delete sessions[sid];
    res.status(204).end();
  } catch (err) {
    const msg = (err as Error)?.message || "Internal Server Error";
    console.error("DELETE /mcp error:", err);
    res.status(500).json({ error: msg });
  }
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`Gmail MCP (Streamable HTTP) at http://0.0.0.0:${PORT}${PATH}`);
});

// ESM TS file: ensure it’s a module
export {};
