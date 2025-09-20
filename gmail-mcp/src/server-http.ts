import { randomUUID } from "node:crypto";
import express, { Request, Response } from "express";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { registerAll } from "./index.js";

const app = express(); // DO NOT add app.use(express.json()); transport needs raw body
const PORT = Number(process.env.PORT || 7331);
const PATH = process.env.MCP_PATH || "/mcp";

// Shared server instance (singleton pattern for HTTP transport)
let sharedServer: Server | null = null;

// Keep transports per session id  
const sessions: Record<string, StreamableHTTPServerTransport> = {};

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
app.get("/healthz", (_req: Request, res: Response) => {
  res.status(200).json({ ok: true });
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
