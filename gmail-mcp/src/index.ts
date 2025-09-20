#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { google } from "googleapis";
import { z } from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";
import { OAuth2Client } from "google-auth-library";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import http from "http";
import open from "open";
import os from "os";
import { createEmailMessage, createEmailWithNodemailer } from "./utl.js";
import {
  createLabel,
  updateLabel,
  deleteLabel,
  listLabels,
  getOrCreateLabel,
  GmailLabel,
} from "./label-manager.js";
import {
  createFilter,
  listFilters,
  getFilter,
  deleteFilter,
  filterTemplates,
} from "./filter-manager.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Configuration paths
const CONFIG_DIR = path.join(os.homedir(), ".gmail-mcp");
const OAUTH_PATH =
  process.env.GMAIL_OAUTH_PATH || path.join(CONFIG_DIR, "gcp-oauth.keys.json");
const CREDENTIALS_PATH =
  process.env.GMAIL_CREDENTIALS_PATH ||
  path.join(CONFIG_DIR, "credentials.json");

let _gmailSingleton: ReturnType<typeof google.gmail> | null = null;

let oauth2Client: OAuth2Client | null = null;

/** Returns an OAuth2Client. Loads/validates keys and (optionally) tokens. */
async function ensureOAuthClient(): Promise<OAuth2Client> {
  // Your existing loadCredentials() probably set a global before; make it return the client:
  if (oauth2Client) return oauth2Client;
  oauth2Client = await loadCredentials(); // <— make loadCredentials() return OAuth2Client (see step 2)
  return oauth2Client;
}

/** Lazy Gmail: construct on first use so initialize/tools/list don’t touch Gmail. */
export async function getGmailOnce() {
  const client = await ensureOAuthClient();
  return google.gmail({ version: "v1", auth: client });
}


// ---- Types used in handlers ----
interface GmailMessagePart {
  partId?: string;
  mimeType?: string;
  filename?: string;
  headers?: Array<{ name: string; value: string }>;
  body?: { attachmentId?: string; size?: number; data?: string };
  parts?: GmailMessagePart[];
}
interface EmailAttachment {
  id: string;
  filename: string;
  mimeType: string;
  size: number;
}
interface EmailContent {
  text: string;
  html: string;
}

// ---- Helpers (shared by STDIO & HTTP) ----
function enableToolsCapability(server: any) {
  const cur = server.capabilities ?? {};
  // Prefer official setter if this SDK build exposes it
  if (typeof server.setCapabilities === "function") {
    server.setCapabilities({ ...cur, tools: { ...(cur.tools ?? {}) } });
  } else {
    // Fallback for builds that read from .capabilities
    server.capabilities = { ...cur, tools: { ...(cur.tools ?? {}) } };
  }
}


function extractEmailContent(messagePart: GmailMessagePart): EmailContent {
  let textContent = "";
  let htmlContent = "";

  if (messagePart.body?.data) {
    const content = Buffer.from(messagePart.body.data, "base64").toString("utf8");
    if (messagePart.mimeType === "text/plain") textContent = content;
    else if (messagePart.mimeType === "text/html") htmlContent = content;
  }

  if (messagePart.parts?.length) {
    for (const part of messagePart.parts) {
      const { text, html } = extractEmailContent(part);
      if (text) textContent += text;
      if (html) htmlContent += html;
    }
  }
  return { text: textContent, html: htmlContent };
}

async function loadCredentials(): Promise<OAuth2Client> {
  try {
    if (!process.env.GMAIL_OAUTH_PATH || !process.env.GMAIL_CREDENTIALS_PATH) {
      if (!fs.existsSync(CONFIG_DIR)) fs.mkdirSync(CONFIG_DIR, { recursive: true });
    }

    const localOAuthPath = path.join(process.cwd(), "gcp-oauth.keys.json");
    if (fs.existsSync(localOAuthPath) && OAUTH_PATH !== localOAuthPath) {
      fs.copyFileSync(localOAuthPath, OAUTH_PATH);
      console.log("OAuth keys found locally; copied to global config path.");
    }

    // --- OAuth client keys are REQUIRED ---
    if (!fs.existsSync(OAUTH_PATH)) {
      throw new Error(
        `OAuth client keys file not found at ${OAUTH_PATH}. Mount it (GMAIL_OAUTH_PATH) or place gcp-oauth.keys.json there.`
      );
    }
    const oauthStat = fs.statSync(OAUTH_PATH);
    if (!oauthStat.isFile()) {
      throw new Error(`GMAIL_OAUTH_PATH points to a non-file: ${OAUTH_PATH}`);
    }

    const keysContent = JSON.parse(fs.readFileSync(OAUTH_PATH, "utf8"));
    const keys = keysContent.installed || keysContent.web;
    if (!keys) throw new Error('Invalid OAuth keys file: missing "installed" or "web".');

    const callback =
      process.argv[2] === "auth" && process.argv[3]
        ? process.argv[3]
        : "http://localhost:3000/oauth2callback";

    const oauth2Client = new OAuth2Client(
      keys.client_id,
      keys.client_secret,
      callback
    );

    // --- Tokens (CREDENTIALS_PATH) are OPTIONAL on init ---
    if (fs.existsSync(CREDENTIALS_PATH)) {
      const credStat = fs.statSync(CREDENTIALS_PATH);
      if (!credStat.isFile()) {
        console.warn(`GMAIL_CREDENTIALS_PATH is not a file: ${CREDENTIALS_PATH} (ignoring for now)`);
      } else {
        try {
          const tokens = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, "utf8"));
          oauth2Client.setCredentials(tokens);
        } catch (e) {
          console.warn(`Failed to parse tokens at ${CREDENTIALS_PATH}: ${(e as Error).message} (ignore on init)`);
        }
      }
    }

    // --- CRITICAL: Auto-save refreshed tokens for long-term operation ---
    oauth2Client.on('tokens', (tokens) => {
      try {
        // Merge new tokens with existing credentials to preserve refresh_token
        let existingTokens = {};
        if (fs.existsSync(CREDENTIALS_PATH)) {
          existingTokens = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, "utf8"));
        }
        
        const updatedTokens = { ...existingTokens, ...tokens };
        fs.writeFileSync(CREDENTIALS_PATH, JSON.stringify(updatedTokens, null, 2));
        console.log(`[${new Date().toISOString()}] Auto-saved refreshed tokens to ${CREDENTIALS_PATH}`);
      } catch (error) {
        console.error(`[${new Date().toISOString()}] Failed to save refreshed tokens:`, error);
      }
    });

    return oauth2Client;
  } catch (error) {
    // If we crash here, the server 500s on initialize. Log loudly.
    console.error("Error loading credentials:", error);
    throw error;
  }
}

async function authenticate(oauth2Client: OAuth2Client): Promise<void> {
  const server = http.createServer();
  server.listen(3000);

  await new Promise<void>((resolve, reject) => {
    const authUrl = oauth2Client.generateAuthUrl({
      access_type: "offline",
      scope: [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.settings.basic",
      ],
    });

    console.log("Please visit this URL to authenticate:", authUrl);
    void open(authUrl);

    server.on("request", async (req, res) => {
      if (!req.url?.startsWith("/oauth2callback")) return;

      const url = new URL(req.url, "http://localhost:3000");
      const code = url.searchParams.get("code");
      if (!code) {
        res.writeHead(400).end("No code provided");
        return reject(new Error("No code provided"));
      }

      try {
        const { tokens } = await oauth2Client.getToken(code);
        oauth2Client.setCredentials(tokens);
        fs.writeFileSync(CREDENTIALS_PATH, JSON.stringify(tokens));
        res.writeHead(200).end("Authentication successful! You can close this window.");
        server.close();
        resolve();
      } catch (e) {
        res.writeHead(500).end("Authentication failed");
        reject(e);
      }
    });
  });
}

/** Create OAuth client + Gmail client. */
export async function createOauthAndGmail() {
  const oauth2Client = await loadCredentials();
  if (process.argv[2] === "auth") {
    await authenticate(oauth2Client);
    console.log("Authentication completed successfully");
    process.exit(0);
  }
  const gmail = google.gmail({ version: "v1", auth: oauth2Client });
  return { oauth2Client, gmail };
}

// ---- Schemas ----
const SendEmailSchema = z.object({
  to: z.array(z.string()),
  subject: z.string(),
  body: z.string(),
  htmlBody: z.string().optional(),
  mimeType: z
    .enum(["text/plain", "text/html", "multipart/alternative"])
    .optional()
    .default("text/plain"),
  cc: z.array(z.string()).optional(),
  bcc: z.array(z.string()).optional(),
  threadId: z.string().optional(),
  inReplyTo: z.string().optional(),
  attachments: z.array(z.string()).optional(),
});
const ReadEmailSchema = z.object({ messageId: z.string() });
const SearchEmailsSchema = z.object({
  query: z.string(),
  maxResults: z.number().optional(),
});
const ModifyEmailSchema = z.object({
  messageId: z.string(),
  labelIds: z.array(z.string()).optional(),
  addLabelIds: z.array(z.string()).optional(),
  removeLabelIds: z.array(z.string()).optional(),
});
const DeleteEmailSchema = z.object({ messageId: z.string() });
const ListEmailLabelsSchema = z.object({});
const CreateLabelSchema = z.object({
  name: z.string(),
  messageListVisibility: z.enum(["show", "hide"]).optional(),
  labelListVisibility: z
    .enum(["labelShow", "labelShowIfUnread", "labelHide"])
    .optional(),
});
const UpdateLabelSchema = z.object({
  id: z.string(),
  name: z.string().optional(),
  messageListVisibility: z.enum(["show", "hide"]).optional(),
  labelListVisibility: z
    .enum(["labelShow", "labelShowIfUnread", "labelHide"])
    .optional(),
});
const DeleteLabelSchema = z.object({ id: z.string() });
const GetOrCreateLabelSchema = z.object({
  name: z.string(),
  messageListVisibility: z.enum(["show", "hide"]).optional(),
  labelListVisibility: z
    .enum(["labelShow", "labelShowIfUnread", "labelHide"])
    .optional(),
});
const BatchModifyEmailsSchema = z.object({
  messageIds: z.array(z.string()),
  addLabelIds: z.array(z.string()).optional(),
  removeLabelIds: z.array(z.string()).optional(),
  batchSize: z.number().optional().default(50),
});
const BatchDeleteEmailsSchema = z.object({
  messageIds: z.array(z.string()),
  batchSize: z.number().optional().default(50),
});
const CreateFilterSchema = z.object({
  criteria: z.object({
    from: z.string().optional(),
    to: z.string().optional(),
    subject: z.string().optional(),
    query: z.string().optional(),
    negatedQuery: z.string().optional(),
    hasAttachment: z.boolean().optional(),
    excludeChats: z.boolean().optional(),
    size: z.number().optional(),
    sizeComparison: z.enum(["unspecified", "smaller", "larger"]).optional(),
  }),
  action: z.object({
    addLabelIds: z.array(z.string()).optional(),
    removeLabelIds: z.array(z.string()).optional(),
    forward: z.string().optional(),
  }),
});
const ListFiltersSchema = z.object({});
const GetFilterSchema = z.object({ filterId: z.string() });
const DeleteFilterSchema = z.object({ filterId: z.string() });
const CreateFilterFromTemplateSchema = z.object({
  template: z.enum([
    "fromSender",
    "withSubject",
    "withAttachments",
    "largeEmails",
    "containingText",
    "mailingList",
  ]),
  parameters: z.object({
    senderEmail: z.string().optional(),
    subjectText: z.string().optional(),
    searchText: z.string().optional(),
    listIdentifier: z.string().optional(),
    sizeInBytes: z.number().optional(),
    labelIds: z.array(z.string()).optional(),
    archive: z.boolean().optional(),
    markAsRead: z.boolean().optional(),
    markImportant: z.boolean().optional(),
  }),
});
const DownloadAttachmentSchema = z.object({
  messageId: z.string(),
  attachmentId: z.string(),
  filename: z.string().optional(),
  savePath: z.string().optional(),
});

// ---- Attach all tools to a given server ----
function forceEnableToolsCapability(server: any) {
  // 1) Newer SDKs (if present)
  if (typeof server.setCapabilities === "function") {
    const cur = typeof server.getCapabilities === "function" ? server.getCapabilities() : {};
    server.setCapabilities({ ...cur, tools: {} });
  }

  // 2) Most 1.18.x builds keep user options on `server.options`
  if (server.options) {
    server.options.capabilities = { ...(server.options.capabilities ?? {}), tools: {} };
  }

  // 3) Fallback for older code paths
  server.capabilities = { ...(server.capabilities ?? {}), tools: {} };

  // Debug what the SDK *thinks* now
  try {
    const seen =
      (typeof server.getCapabilities === "function" && server.getCapabilities()) ||
      server.options?.capabilities ||
      server.capabilities ||
      {};
    console.log("MCP effective capabilities (post-force):", JSON.stringify(seen));
  } catch {}
}


export function registerAll(server: Server) {
  // Ensure the internal _capabilities property is set (required for MCP SDK capability checks)
  (server as any)._capabilities = { tools: {} };

 server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: [
      { name: "send_email", description: "Sends a new email", inputSchema: zodToJsonSchema(SendEmailSchema) },
      { name: "draft_email", description: "Draft a new email", inputSchema: zodToJsonSchema(SendEmailSchema) },
      { name: "read_email", description: "Retrieves a specific email", inputSchema: zodToJsonSchema(ReadEmailSchema) },
      { name: "search_emails", description: "Search emails via Gmail query", inputSchema: zodToJsonSchema(SearchEmailsSchema) },
      { name: "modify_email", description: "Modify labels on an email", inputSchema: zodToJsonSchema(ModifyEmailSchema) },
      { name: "delete_email", description: "Delete an email", inputSchema: zodToJsonSchema(DeleteEmailSchema) },
      { name: "list_email_labels", description: "List Gmail labels", inputSchema: zodToJsonSchema(ListEmailLabelsSchema) },
      { name: "batch_modify_emails", description: "Batch label modifications", inputSchema: zodToJsonSchema(BatchModifyEmailsSchema) },
      { name: "batch_delete_emails", description: "Batch delete emails", inputSchema: zodToJsonSchema(BatchDeleteEmailsSchema) },
      { name: "create_label", description: "Create a label", inputSchema: zodToJsonSchema(CreateLabelSchema) },
      { name: "update_label", description: "Update a label", inputSchema: zodToJsonSchema(UpdateLabelSchema) },
      { name: "delete_label", description: "Delete a label", inputSchema: zodToJsonSchema(DeleteLabelSchema) },
      { name: "get_or_create_label", description: "Get or create a label", inputSchema: zodToJsonSchema(GetOrCreateLabelSchema) },
      { name: "create_filter", description: "Create a Gmail filter", inputSchema: zodToJsonSchema(CreateFilterSchema) },
      { name: "list_filters", description: "List Gmail filters", inputSchema: zodToJsonSchema(ListFiltersSchema) },
      { name: "get_filter", description: "Get a Gmail filter", inputSchema: zodToJsonSchema(GetFilterSchema) },
      { name: "delete_filter", description: "Delete a Gmail filter", inputSchema: zodToJsonSchema(DeleteFilterSchema) },
      { name: "create_filter_from_template", description: "Create filter from template", inputSchema: zodToJsonSchema(CreateFilterFromTemplateSchema) },
      { name: "download_attachment", description: "Download an attachment", inputSchema: zodToJsonSchema(DownloadAttachmentSchema) },
    ],
  }));

  server.setRequestHandler(CallToolRequestSchema, async (request: any) => {
    const { name, arguments: args } = request.params;

    async function handleEmailAction(action: "send" | "draft", validatedArgs: any) {
      const gmail = await getGmailOnce();

      let message: string;
      try {
        if (validatedArgs.attachments?.length) {
          message = await createEmailWithNodemailer(validatedArgs);
          const raw = Buffer.from(message).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
          if (action === "send") {
            const result = await gmail.users.messages.send({ userId: "me", requestBody: { raw, ...(validatedArgs.threadId && { threadId: validatedArgs.threadId }) } });
            return { content: [{ type: "text", text: `Email sent successfully with ID: ${result.data.id}` }] };
          } else {
            const result = await gmail.users.drafts.create({ userId: "me", requestBody: { message: { raw, ...(validatedArgs.threadId && { threadId: validatedArgs.threadId }) } } });
            return { content: [{ type: "text", text: `Email draft created successfully with ID: ${result.data.id}` }] };
          }
        } else {
          message = createEmailMessage(validatedArgs);
          const raw = Buffer.from(message).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
          const m: { raw: string; threadId?: string } = { raw };
          if (validatedArgs.threadId) m.threadId = validatedArgs.threadId;

          if (action === "send") {
            const result = await gmail.users.messages.send({ userId: "me", requestBody: m });
            return { content: [{ type: "text", text: `Email sent successfully with ID: ${result.data.id}` }] };
          } else {
            const result = await gmail.users.drafts.create({ userId: "me", requestBody: { message: m } });
            return { content: [{ type: "text", text: `Email draft created successfully with ID: ${result.data.id}` }] };
          }
        }
      } catch (err: any) {
        if (validatedArgs.attachments?.length) console.error(`Failed to send email with ${validatedArgs.attachments.length} attachments:`, err.message);
        throw err;
      }
    }

    // batch helper
    async function processBatches<T, U>(
      items: T[],
      batchSize: number,
      processFn: (batch: T[]) => Promise<U[]>
    ): Promise<{ successes: U[]; failures: { item: T; error: Error }[] }> {
      const successes: U[] = [];
      const failures: { item: T; error: Error }[] = [];

      for (let i = 0; i < items.length; i += batchSize) {
        const batch = items.slice(i, i + batchSize);
        try {
          const results = await processFn(batch);
          successes.push(...results);
        } catch {
          for (const item of batch) {
            try {
              const results = await processFn([item]);
              successes.push(...results);
            } catch (e) {
              failures.push({ item, error: e as Error });
            }
          }
        }
      }
      return { successes, failures };
    }


    try {
      switch (name) {
        case "send_email":
        case "draft_email": {
          const validatedArgs = SendEmailSchema.parse(args);
          return handleEmailAction(name === "send_email" ? "send" : "draft", validatedArgs);
        }
        case "read_email": {
          const { messageId } = ReadEmailSchema.parse(args);
          const gmail = await getGmailOnce();
          const r = await gmail.users.messages.get({ userId: "me", id: messageId, format: "full" });

          const headers = r.data.payload?.headers || [];
          const subject = headers.find((h: any) => h.name?.toLowerCase() === "subject")?.value || "";
          const from    = headers.find((h: any) => h.name?.toLowerCase() === "from")?.value || "";
          const to      = headers.find((h: any) => h.name?.toLowerCase() === "to")?.value || "";
          const date    = headers.find((h: any) => h.name?.toLowerCase() === "date")?.value || "";
          const threadId = r.data.threadId || "";

          const { text, html } = extractEmailContent((r.data.payload as GmailMessagePart) || {});
          const body = text || html || "";
          const note = !text && html ? "[Note: HTML-formatted email; no plain text available.]\n\n" : "";

          const attachments: EmailAttachment[] = [];
          const visit = (p: GmailMessagePart) => {
            if (p.body?.attachmentId) {
              const filename = p.filename || `attachment-${p.body.attachmentId}`;
              attachments.push({ id: p.body.attachmentId, filename, mimeType: p.mimeType || "application/octet-stream", size: p.body.size || 0 });
            }
            if (p.parts) p.parts.forEach(visit);
          };
          if (r.data.payload) visit(r.data.payload as GmailMessagePart);

          const attachInfo =
            attachments.length
              ? `\n\nAttachments (${attachments.length}):\n` +
                attachments.map(a => `- ${a.filename} (${a.mimeType}, ${Math.round(a.size / 1024)} KB, ID: ${a.id})`).join("\n")
              : "";

          return { content: [{ type: "text", text: `Thread ID: ${threadId}\nSubject: ${subject}\nFrom: ${from}\nTo: ${to}\nDate: ${date}\n\n${note}${body}${attachInfo}` }] };
        }

        case "search_emails": {
          const { query, maxResults } = SearchEmailsSchema.parse(args);
          const gmail = await getGmailOnce();
          const list = await gmail.users.messages.list({ userId: "me", q: query, maxResults: maxResults || 10 });
          const msgs = list.data.messages || [];
          const rows = await Promise.all(
            msgs.map(async (m: any) => {
              const d = await gmail.users.messages.get({ userId: "me", id: m.id!, format: "metadata", metadataHeaders: ["Subject", "From", "Date"] });
              const h = d.data.payload?.headers || [];
              return {
                id: m.id,
                subject: h.find((x: any) => x.name === "Subject")?.value || "",
                from:    h.find((x: any) => x.name === "From")?.value || "",
                date:    h.find((x: any) => x.name === "Date")?.value || "",
              };
            })
          );
          return { content: [{ type: "text", text: rows.map((r: any) => `ID: ${r.id}\nSubject: ${r.subject}\nFrom: ${r.from}\nDate: ${r.date}\n`).join("\n") }] };
        }

        case "modify_email": {
          const v = ModifyEmailSchema.parse(args);
          const gmail = await getGmailOnce();
          const body: any = {};
          if (v.labelIds) body.addLabelIds = v.labelIds;
          if (v.addLabelIds) body.addLabelIds = v.addLabelIds;
          if (v.removeLabelIds) body.removeLabelIds = v.removeLabelIds;
          await gmail.users.messages.modify({ userId: "me", id: v.messageId, requestBody: body });
          return { content: [{ type: "text", text: `Email ${v.messageId} labels updated successfully` }] };
        }

        case "delete_email": {
          const { messageId } = DeleteEmailSchema.parse(args);
          const gmail = await getGmailOnce();
          await gmail.users.messages.delete({ userId: "me", id: messageId });
          return { content: [{ type: "text", text: `Email ${messageId} deleted successfully` }] };
        }

        case "list_email_labels": {
          const gmail = await getGmailOnce();
          const res = await listLabels(gmail);
          const system = res.system.map((l: GmailLabel) => `ID: ${l.id}\nName: ${l.name}\n`).join("\n");
          const user   = res.user.map((l: GmailLabel) => `ID: ${l.id}\nName: ${l.name}\n`).join("\n");
          return { content: [{ type: "text", text: `Found ${res.count.total} labels (${res.count.system} system, ${res.count.user} user):\n\nSystem Labels:\n${system}\nUser Labels:\n${user}` }] };
        }

        case "batch_modify_emails": {
          const v = BatchModifyEmailsSchema.parse(args);
          const gmail = await getGmailOnce();
          const body: any = {};
          if (v.addLabelIds) body.addLabelIds = v.addLabelIds;
          if (v.removeLabelIds) body.removeLabelIds = v.removeLabelIds;

          const { successes, failures } = await processBatches(
            v.messageIds,
            v.batchSize || 50,
            async (batch) =>
              await Promise.all(
                batch.map(async (id) => {
                  await gmail.users.messages.modify({ userId: "me", id, requestBody: body });
                  return { messageId: id, success: true };
                })
              )
          );

          let text = `Batch label modification complete.\nSuccessfully processed: ${successes.length}`;
          if (failures.length) {
            text += `\nFailed: ${failures.length}\n` + failures.map(f => `- ${(f.item as string).slice(0,16)}... (${f.error.message})`).join("\n");
          }
          return { content: [{ type: "text", text }] };
        }

        case "batch_delete_emails": {
          const v = BatchDeleteEmailsSchema.parse(args);
          const gmail = await getGmailOnce();
          const { successes, failures } = await processBatches(
            v.messageIds,
            v.batchSize || 50,
            async (batch) =>
              await Promise.all(
                batch.map(async (id) => {
                  await gmail.users.messages.delete({ userId: "me", id });
                  return { messageId: id, success: true };
                })
              )
          );

          let text = `Batch delete operation complete.\nSuccessfully deleted: ${successes.length}`;
          if (failures.length) {
            text += `\nFailed: ${failures.length}\n` + failures.map(f => `- ${(f.item as string).slice(0,16)}... (${f.error.message})`).join("\n");
          }
          return { content: [{ type: "text", text }] };
        }

        case "create_label": {
          const v = CreateLabelSchema.parse(args);
          const gmail = await getGmailOnce();
          const res = await createLabel(gmail, v.name, {
            messageListVisibility: v.messageListVisibility,
            labelListVisibility: v.labelListVisibility,
          });
          return { content: [{ type: "text", text: `Label created:\nID: ${res.id}\nName: ${res.name}\nType: ${res.type}` }] };
        }

        case "update_label": {
          const v = UpdateLabelSchema.parse(args);
          const gmail = await getGmailOnce();
          const updates: any = {};
          if (v.name) updates.name = v.name;
          if (v.messageListVisibility) updates.messageListVisibility = v.messageListVisibility;
          if (v.labelListVisibility) updates.labelListVisibility = v.labelListVisibility;
          const res = await updateLabel(gmail, v.id, updates);
          return { content: [{ type: "text", text: `Label updated:\nID: ${res.id}\nName: ${res.name}\nType: ${res.type}` }] };
        }

        case "delete_label": {
          const v = DeleteLabelSchema.parse(args);
          const gmail = await getGmailOnce();
          const res = await deleteLabel(gmail, v.id);
          return { content: [{ type: "text", text: res.message }] };
        }

        case "get_or_create_label": {
          const v = GetOrCreateLabelSchema.parse(args);
          const gmail = await getGmailOnce();
          const res = await getOrCreateLabel(gmail, v.name, {
            messageListVisibility: v.messageListVisibility,
            labelListVisibility: v.labelListVisibility,
          });
          const action = res.type === "user" && res.name === v.name ? "found existing" : "created new";
          return { content: [{ type: "text", text: `Successfully ${action} label:\nID: ${res.id}\nName: ${res.name}\nType: ${res.type}` }] };
        }

        case "create_filter": {
          const v = CreateFilterSchema.parse(args);
          const gmail = await getGmailOnce();
          const res = await createFilter(gmail, v.criteria, v.action);
          const crit = Object.entries(v.criteria).filter(([,val]) => val !== undefined).map(([k,val]) => `${k}: ${val}`).join(", ");
          const act  = Object.entries(v.action).filter(([,val]) => val !== undefined && (Array.isArray(val)? val.length>0 : true)).map(([k,val]) => `${k}: ${Array.isArray(val)? val.join(", ") : val}`).join(", ");
          return { content: [{ type: "text", text: `Filter created:\nID: ${res.id}\nCriteria: ${crit}\nActions: ${act}` }] };
        }

        case "list_filters": {
          const gmail = await getGmailOnce();
          const res = await listFilters(gmail);
          if (!res.filters.length) return { content: [{ type: "text", text: "No filters found." }] };
          const text = res.filters.map((f: any) => {
            const crit = Object.entries(f.criteria || {}).filter(([,v]) => v !== undefined).map(([k,v]) => `${k}: ${v}`).join(", ");
            const act  = Object.entries(f.action || {}).filter(([,v]) => v !== undefined && (Array.isArray(v)? v.length>0 : true)).map(([k,v]) => `${k}: ${Array.isArray(v)? v.join(", ") : v}`).join(", ");
            return `ID: ${f.id}\nCriteria: ${crit}\nActions: ${act}\n`;
          }).join("\n");
          return { content: [{ type: "text", text: `Found ${res.count} filters:\n\n${text}` }] };
        }

        case "get_filter": {
          const v = GetFilterSchema.parse(args);
          const gmail = await getGmailOnce();
          const res = await getFilter(gmail, v.filterId);
          const crit = Object.entries(res.criteria || {}).filter(([,v]) => v !== undefined).map(([k,v]) => `${k}: ${v}`).join(", ");
          const act  = Object.entries(res.action || {}).filter(([,v]) => v !== undefined && (Array.isArray(v)? v.length>0 : true)).map(([k,v]) => `${k}: ${Array.isArray(v)? v.join(", ") : v}`).join(", ");
          return { content: [{ type: "text", text: `Filter details:\nID: ${res.id}\nCriteria: ${crit}\nActions: ${act}` }] };
        }

        case "delete_filter": {
          const v = DeleteFilterSchema.parse(args);
          const gmail = await getGmailOnce();
          const res = await deleteFilter(gmail, v.filterId);
          return { content: [{ type: "text", text: res.message }] };
        }

        case "create_filter_from_template": {
          const v = CreateFilterFromTemplateSchema.parse(args);
          const gmail = await getGmailOnce();
          let cfg: { criteria: any; action: any };
          switch (v.template) {
            case "fromSender":
              if (!v.parameters.senderEmail) throw new Error("senderEmail is required for fromSender");
              cfg = filterTemplates.fromSender(v.parameters.senderEmail, v.parameters.labelIds, v.parameters.archive);
              break;
            case "withSubject":
              if (!v.parameters.subjectText) throw new Error("subjectText is required for withSubject");
              cfg = filterTemplates.withSubject(v.parameters.subjectText, v.parameters.labelIds, v.parameters.markAsRead);
              break;
            case "withAttachments":
              cfg = filterTemplates.withAttachments(v.parameters.labelIds);
              break;
            case "largeEmails":
              if (!v.parameters.sizeInBytes) throw new Error("sizeInBytes is required for largeEmails");
              cfg = filterTemplates.largeEmails(v.parameters.sizeInBytes, v.parameters.labelIds);
              break;
            case "containingText":
              if (!v.parameters.searchText) throw new Error("searchText is required for containingText");
              cfg = filterTemplates.containingText(v.parameters.searchText, v.parameters.labelIds, v.parameters.markImportant);
              break;
            case "mailingList":
              if (!v.parameters.listIdentifier) throw new Error("listIdentifier is required for mailingList");
              cfg = filterTemplates.mailingList(v.parameters.listIdentifier, v.parameters.labelIds, v.parameters.archive);
              break;
            default:
              throw new Error(`Unknown template: ${v.template}`);
          }
          const res = await createFilter(gmail, cfg.criteria, cfg.action);
          return { content: [{ type: "text", text: `Filter created from template '${v.template}':\nID: ${res.id}` }] };
        }

        case "download_attachment": {
          const v = DownloadAttachmentSchema.parse(args);
          const gmail = await getGmailOnce();
          try {
            const a = await gmail.users.messages.attachments.get({
              userId: "me",
              messageId: v.messageId,
              id: v.attachmentId,
            });
            if (!a.data.data) throw new Error("No attachment data received");

            const buffer = Buffer.from(a.data.data, "base64url");
            const savePath = v.savePath || process.cwd();
            let filename = v.filename;

            if (!filename) {
              const m = await gmail.users.messages.get({
                userId: "me",
                id: v.messageId,
                format: "full",
              });
              const find = (p: any): string | null => {
                if (p.body && p.body.attachmentId === v.attachmentId)
                  return p.filename || `attachment-${v.attachmentId}`;
                if (p.parts) for (const sp of p.parts) {
                  const f = find(sp);
                  if (f) return f;
                }
                return null;
              };
              filename = find(m.data.payload) || `attachment-${v.attachmentId}`;
            }

            if (!fs.existsSync(savePath)) fs.mkdirSync(savePath, { recursive: true });
            const fullPath = path.join(savePath, filename);
            fs.writeFileSync(fullPath, buffer);

            return { content: [{ type: "text", text: `Attachment downloaded:\nFile: ${filename}\nSize: ${buffer.length} bytes\nSaved to: ${fullPath}` }] };
          } catch (err: any) {
            return { content: [{ type: "text", text: `Failed to download attachment: ${err.message}` }] };
          }
        }

        default:
          throw new Error(`Unknown tool: ${name}`);
      }
    } catch (err: any) {
      return { content: [{ type: "text", text: `Error: ${err.message}` }] };
    }
  });
}

// ---- STDIO entrypoint (kept for clients that launch via stdio) ----
async function main() {
  const { gmail } = await createOauthAndGmail();
  const server = new Server({ name: "gmail", version: "1.0.0" });
  registerAll(server);
  const transport = new StdioServerTransport();
  server.connect(transport);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => {
    console.error("Server error:", e);
    process.exit(1);
  });
}
