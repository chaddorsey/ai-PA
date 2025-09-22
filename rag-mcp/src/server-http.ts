#!/usr/bin/env node
/**
 * RAG MCP Server - HTTP Transport
 * 
 * This module provides HTTP transport for the RAG MCP Server,
 * following standardized patterns for health checks and MCP protocol.
 */

import { randomUUID } from "node:crypto";
import express, { Request, Response } from "express";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

const app = express();
const PORT = Number(process.env.PORT || 8082);
const PATH = process.env.MCP_PATH || "/mcp";
const HEALTH_PATH = process.env.MCP_HEALTH_CHECK_PATH || "/health";

// RAG Tool Schemas
const SearchDocumentsSchema = z.object({
  query: z.string().describe("The search query to find relevant documents"),
  limit: z.number().optional().describe("Maximum number of documents to return (default: 10)"),
  collection: z.string().optional().describe("Document collection to search (default: 'default')")
});

const RetrieveDocumentSchema = z.object({
  document_id: z.string().describe("The unique identifier of the document to retrieve"),
  collection: z.string().optional().describe("Document collection containing the document")
});

const IndexDocumentSchema = z.object({
  content: z.string().describe("The content of the document to index"),
  metadata: z.record(z.any()).optional().describe("Optional metadata for the document"),
  collection: z.string().optional().describe("Document collection to index into (default: 'default')")
});

const QueryVectorSchema = z.object({
  query: z.string().describe("The query to search for in vector space"),
  limit: z.number().optional().describe("Maximum number of results to return (default: 10)"),
  threshold: z.number().optional().describe("Similarity threshold (0-1, default: 0.7)")
});

// RAG Tool Handlers
async function handleSearchDocuments(args: z.infer<typeof SearchDocumentsSchema>) {
  // TODO: Implement actual document search functionality
  return {
    documents: [
      {
        id: "doc-1",
        title: "Sample Document 1",
        content: "This is a sample document that matches your query.",
        score: 0.95,
        metadata: { source: "example", created: "2025-01-20" }
      }
    ],
    total: 1,
    query: args.query,
    collection: args.collection || "default"
  };
}

async function handleRetrieveDocument(args: z.infer<typeof RetrieveDocumentSchema>) {
  // TODO: Implement actual document retrieval functionality
  return {
    id: args.document_id,
    content: "This is the content of the requested document.",
    metadata: { source: "example", created: "2025-01-20" },
    collection: args.collection || "default"
  };
}

async function handleIndexDocument(args: z.infer<typeof IndexDocumentSchema>) {
  // TODO: Implement actual document indexing functionality
  return {
    id: `doc-${Date.now()}`,
    status: "indexed",
    collection: args.collection || "default",
    metadata: args.metadata || {}
  };
}

async function handleQueryVector(args: z.infer<typeof QueryVectorSchema>) {
  // TODO: Implement actual vector query functionality
  return {
    results: [
      {
        id: "vec-1",
        content: "This is a vector search result.",
        similarity: 0.92,
        metadata: { source: "vector_db" }
      }
    ],
    query: args.query,
    threshold: args.threshold || 0.7
  };
}

// Shared server instance (singleton pattern for HTTP transport)
let sharedServer: Server | null = null;

// Keep transports per session id
const sessions: Record<string, StreamableHTTPServerTransport> = {};

// Build a shared server instance (only called once)
async function getSharedServer(): Promise<Server> {
  if (sharedServer) return sharedServer;

  sharedServer = new Server({
    name: "rag-tools",
    version: "1.0.0"
  });

  // Set capabilities (required for MCP SDK to allow tool registration)
  (sharedServer as any).capabilities = { tools: {} };

  // Register RAG Tools
  sharedServer.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
      tools: [
        {
          name: "search_documents",
          description: "Search for documents using text-based queries",
          inputSchema: {
            type: "object",
            properties: SearchDocumentsSchema.shape,
            required: ["query"]
          }
        },
        {
          name: "retrieve_document",
          description: "Retrieve a specific document by its ID",
          inputSchema: {
            type: "object",
            properties: RetrieveDocumentSchema.shape,
            required: ["document_id"]
          }
        },
        {
          name: "index_document",
          description: "Index a new document for future retrieval",
          inputSchema: {
            type: "object",
            properties: IndexDocumentSchema.shape,
            required: ["content"]
          }
        },
        {
          name: "query_vector",
          description: "Query documents using vector similarity search",
          inputSchema: {
            type: "object",
            properties: QueryVectorSchema.shape,
            required: ["query"]
          }
        }
      ]
    };
  });

  sharedServer.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;

    try {
      switch (name) {
        case "search_documents": {
          const validatedArgs = SearchDocumentsSchema.parse(args);
          const result = await handleSearchDocuments(validatedArgs);
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(result, null, 2)
              }
            ]
          };
        }

        case "retrieve_document": {
          const validatedArgs = RetrieveDocumentSchema.parse(args);
          const result = await handleRetrieveDocument(validatedArgs);
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(result, null, 2)
              }
            ]
          };
        }

        case "index_document": {
          const validatedArgs = IndexDocumentSchema.parse(args);
          const result = await handleIndexDocument(validatedArgs);
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(result, null, 2)
              }
            ]
          };
        }

        case "query_vector": {
          const validatedArgs = QueryVectorSchema.parse(args);
          const result = await handleQueryVector(validatedArgs);
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(result, null, 2)
              }
            ]
          };
        }

        default:
          throw new Error(`Unknown tool: ${name}`);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Unknown error";
      return {
        content: [
          {
            type: "text",
            text: `Error: ${errorMessage}`
          }
        ],
        isError: true
      };
    }
  });

  console.log("Created shared RAG MCP server instance");
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
app.get(HEALTH_PATH, (_req: Request, res: Response) => {
  const serverName = process.env.MCP_SERVER_NAME || "rag-tools";
  const serverVersion = process.env.MCP_SERVER_VERSION || "1.0.0";

  res.status(200).json({
    status: "healthy",
    timestamp: new Date().toISOString(),
    service: serverName,
    version: serverVersion,
    uptime: process.uptime(),
    dependencies: {
      vector_database: "healthy", // TODO: Add actual vector DB health check
      document_store: "healthy", // TODO: Add actual document store health check
      external_apis: "healthy"
    }
  });
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
    if (sessions[sid]) {
      sessions[sid].disconnect();
      delete sessions[sid];
      console.log(`Session ${sid} torn down.`);
      res.status(200).json({ message: `Session ${sid} torn down.` });
    } else {
      res.status(404).json({ error: `Session ${sid} not found.` });
    }
  } catch (err) {
    const msg = (err as Error)?.message || "Internal Server Error";
    console.error("DELETE /mcp error:", err);
    res.status(500).json({ error: msg });
  }
});

app.listen(PORT, () => {
  console.log(`RAG MCP server listening on port ${PORT}`);
  console.log(`Health check available at http://localhost:${PORT}${HEALTH_PATH}`);
  console.log(`MCP endpoint available at http://localhost:${PORT}${PATH}`);
});

