/**
 * surface/server.ts — the authenticated controller↔surface boundary (R21/R28): a loopback WS
 * server speaking surface/protocol.ts.
 *
 * Attach = authenticate (file-permission token, first frame) → declare capabilities → name the
 * runtime → receive the journal tail from the surface's cursor + live events. The cursor is
 * the journal row id, so replay is gapless and duplicate-free BY CONSTRUCTION — the same rows,
 * in the same order, exactly once. Send = durable hand-over; the receipt is the
 * client_message_id and delivery is C4's inspectable problem from then on.
 */

import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { type Server as HttpServer, createServer } from "node:http";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { ApprovalArbiter, ApprovalDecision, PendingApproval } from "../approvals.js";
import type { TurnEventRow, TurnJournal } from "../journal.js";
import type { RuntimeRef } from "../registry.js";
import type { AwarenessManager } from "../routing/awareness.js";
import { RouteMissError, type RouteTable } from "../routing/routes.js";
import type { TurnPipeline } from "../turns.js";
import { verifySurfaceToken } from "./auth.js";
import {
  CAPABILITIES,
  type Capability,
  SURFACE_PROTOCOL_VERSION,
  type SurfaceEvent,
  SurfaceProtocolError,
  parseSurfaceCommand,
} from "./protocol.js";

const require = createRequire(import.meta.url);
const { WebSocketServer, WebSocket } = require("ws") as typeof import("ws");

/**
 * The minimal web slice (2026-08-17 handoff, session 2): the surface's own HTTP handler
 * serves ONE static page so a single tailnet path mount covers page + WS together. Read
 * per-request (no restart to iterate on the page; it is operator-tooling, not a hot path).
 */
const STATIC_PAGE_PATH = join(dirname(fileURLToPath(import.meta.url)), "../../static/index.html");

/**
 * `tailscale serve --set-path` prefix behaviour differs across versions (stripped vs
 * passed through), so the WS endpoint accepts `/surface` under ANY mount prefix rather
 * than betting on one. Suffix matching cannot collide: the surface serves exactly one page
 * and one WS endpoint.
 */
function isSurfacePath(rawUrl: string | undefined): boolean {
  const pathname = (rawUrl ?? "").split("?")[0] ?? "";
  return pathname === "/surface" || pathname.endsWith("/surface");
}

/** The page answers on `/`, any directory-style path, or an explicit index.html. */
function isPagePath(rawUrl: string | undefined): boolean {
  const pathname = (rawUrl ?? "").split("?")[0] ?? "";
  return pathname === "/" || pathname.endsWith("/") || pathname.endsWith("/index.html");
}

/** Mount-prefix-tolerant like the WS path (see isSurfacePath). */
function isAgentInfoPath(rawUrl: string | undefined): boolean {
  const pathname = (rawUrl ?? "").split("?")[0] ?? "";
  return pathname === "/agent-info" || pathname.endsWith("/agent-info");
}

/** Models change rarely; a short TTL keeps footer fetches off the WS. */
const AGENT_INFO_CACHE_TTL_MS = 60_000;

interface Session {
  id: string;
  socket: import("ws").WebSocket;
  runtime: RuntimeRef;
  capabilities: Set<Capability>;
  presence: "focused" | "background" | "gone";
  cursor: number;
}

export interface SurfaceServerOptions {
  token: string;
  journal: TurnJournal;
  pipeline: TurnPipeline;
  approvals: ApprovalArbiter;
  /** C7's unseen/awareness layer. Optional so C5-era callers keep working. */
  awareness?: AwarenessManager;
  /** C8's direct-lane route table. Optional so earlier callers keep working. */
  routes?: RouteTable;
  /**
   * Read-only agent-record lookup (worker-provided, rides the worker's own WS connection).
   * Serves the web slice's `GET …/agent-info` model footer. Optional: absent → 501.
   */
  agentInfo?: (agentId: string) => Promise<Record<string, unknown>>;
  onWarn?: (msg: string) => void;
}

const key = (r: RuntimeRef): string => `${r.agent_id}:${r.conversation_id}`;

export class SurfaceServer {
  private wss: import("ws").WebSocketServer | null = null;
  private http: HttpServer | null = null;
  private readonly sessions = new Map<string, Session>();
  private unsubscribeJournal: (() => void) | null = null;

  constructor(private readonly opts: SurfaceServerOptions) {}

  /** Loopback only. Port 0 = ephemeral (tests). Returns the bound port. */
  async start(port: number): Promise<number> {
    this.http = createServer((req, res) => {
      if (req.method === "GET" && isAgentInfoPath(req.url)) {
        this.serveAgentInfo(req.url ?? "", res);
        return;
      }
      if ((req.method === "GET" || req.method === "HEAD") && isPagePath(req.url)) {
        readFile(STATIC_PAGE_PATH).then(
          (html) => {
            res.statusCode = 200;
            res.setHeader("content-type", "text/html; charset=utf-8");
            res.setHeader("cache-control", "no-cache");
            res.end(req.method === "HEAD" ? undefined : html);
          },
          () => {
            res.statusCode = 500;
            res.end("continuity-controller surface: static/index.html missing\n");
          },
        );
        return;
      }
      // The ticket-mint endpoint is a C9 deliverable; refusing loudly beats a silent 404.
      res.statusCode = 501;
      res.end("continuity-controller surface: page at /, WS at /surface; tickets land with C9\n");
    });
    this.wss = new WebSocketServer({ noServer: true });
    this.wss.on("connection", (socket) => this.onConnection(socket));
    this.http.on("upgrade", (req, socket, head) => {
      if (!isSurfacePath(req.url)) {
        socket.destroy();
        return;
      }
      this.wss?.handleUpgrade(req, socket, head, (ws) => this.wss?.emit("connection", ws, req));
    });
    await new Promise<void>((resolve) => this.http?.listen(port, "127.0.0.1", resolve));
    this.unsubscribeJournal = this.opts.journal.onRecord((row) => this.fanOutEvent(row));
    const address = this.http.address();
    return typeof address === "object" && address !== null ? address.port : port;
  }

  private readonly agentInfoCache = new Map<string, { at: number; body: string }>();

  /** `GET …/agent-info?agent=<id>` → `{agent_id, name, model}` (60s cache). */
  private serveAgentInfo(rawUrl: string, res: import("node:http").ServerResponse): void {
    const json = (code: number, body: string) => {
      res.statusCode = code;
      res.setHeader("content-type", "application/json; charset=utf-8");
      res.end(body);
    };
    if (!this.opts.agentInfo) {
      json(501, JSON.stringify({ error: "agent-info not wired" }));
      return;
    }
    const agentId = new URLSearchParams(rawUrl.split("?")[1] ?? "").get("agent") ?? "";
    if (!agentId) {
      json(400, JSON.stringify({ error: "missing ?agent=<id>" }));
      return;
    }
    const cached = this.agentInfoCache.get(agentId);
    if (cached && Date.now() - cached.at < AGENT_INFO_CACHE_TTL_MS) {
      json(200, cached.body);
      return;
    }
    this.opts.agentInfo(agentId).then(
      (agent) => {
        const body = JSON.stringify({
          agent_id: agentId,
          name: typeof agent.name === "string" ? agent.name : null,
          model: typeof agent.model === "string" ? agent.model : null,
        });
        this.agentInfoCache.set(agentId, { at: Date.now(), body });
        json(200, body);
      },
      (err: unknown) => {
        json(503, JSON.stringify({ error: err instanceof Error ? err.message : String(err) }));
      },
    );
  }

  async stop(): Promise<void> {
    this.unsubscribeJournal?.();
    this.unsubscribeJournal = null;
    for (const [, s] of this.sessions) s.socket.close();
    this.sessions.clear();
    await new Promise<void>((resolve) => {
      this.wss?.close(() => resolve());
      if (!this.wss) resolve();
    });
    await new Promise<void>((resolve) => {
      this.http?.close(() => resolve());
      if (!this.http) resolve();
    });
    this.wss = null;
    this.http = null;
  }

  get sessionCount(): number {
    return this.sessions.size;
  }

  /** Presence per runtime, for C7's awareness routing. */
  presenceFor(runtime: RuntimeRef): Array<{ session: string; presence: string }> {
    return [...this.sessions.values()]
      .filter((s) => key(s.runtime) === key(runtime))
      .map((s) => ({ session: s.id, presence: s.presence }));
  }

  /** ApprovalArbiter's broadcast hook: deliver to every approvals-capable session. */
  broadcastApproval(approval: PendingApproval): number {
    let reached = 0;
    for (const [, s] of this.sessions) {
      if (!s.capabilities.has("approvals")) continue;
      this.sendTo(s, {
        type: "approval_request",
        approval_id: approval.approvalId,
        runtime: approval.runtime,
        request: approval.request,
      });
      reached += 1;
    }
    return reached;
  }

  /** Awareness fan-out (C7): notify-capable sessions of the runtime. Returns how many. */
  broadcastAwareness(runtime: RuntimeRef, level: string, ref: string): number {
    let reached = 0;
    for (const [, s] of this.sessions) {
      if (key(s.runtime) !== key(runtime)) continue;
      if (!s.capabilities.has("notify")) continue;
      if (s.presence === "gone") continue;
      this.sendTo(s, { type: "awareness", level, runtime, ref });
      reached += 1;
    }
    return reached;
  }

  broadcastApprovalResolution(approvalId: string, decision: ApprovalDecision, by: string): void {
    for (const [, s] of this.sessions) {
      if (!s.capabilities.has("approvals")) continue;
      this.sendTo(s, {
        type: "approval_resolved",
        approval_id: approvalId,
        decision: { behavior: decision.behavior },
        by,
      });
    }
  }

  private onConnection(socket: import("ws").WebSocket): void {
    let session: Session | null = null;
    socket.on("message", (data) => {
      let command: ReturnType<typeof parseSurfaceCommand>;
      try {
        command = parseSurfaceCommand(data.toString());
      } catch (e) {
        socket.send(
          JSON.stringify({
            type: "error",
            message: e instanceof SurfaceProtocolError ? e.message : "bad frame",
          }),
        );
        return;
      }

      if (command.type === "attach") {
        if (!verifySurfaceToken(this.opts.token, command.token)) {
          socket.send(JSON.stringify({ type: "attach_denied", reason: "bad token" }));
          socket.close();
          return;
        }
        if (command.protocol_version !== SURFACE_PROTOCOL_VERSION) {
          socket.send(
            JSON.stringify({
              type: "attach_denied",
              reason: `protocol_version ${command.protocol_version} unsupported (controller speaks ${SURFACE_PROTOCOL_VERSION})`,
            }),
          );
          socket.close();
          return;
        }
        const warnings: string[] = [];
        const declared = new Set<Capability>();
        declared.add("core"); // mandatory tier — declared or not
        for (const cap of command.capabilities) {
          if ((CAPABILITIES as readonly string[]).includes(cap)) declared.add(cap as Capability);
          else warnings.push(`unknown capability "${cap}" ignored (R28: degrade, never drop)`);
        }
        const replayRows = this.opts.journal.rowsSince(command.runtime, command.cursor);
        const replay = replayRows.map((row) => this.toEvent(row));
        const cursor = replayRows.length > 0 ? (replayRows.at(-1)?.id ?? 0) : (command.cursor ?? 0);
        session = {
          id: randomUUID().slice(0, 8),
          socket,
          runtime: command.runtime,
          capabilities: declared,
          presence: "focused",
          cursor,
        };
        this.sessions.set(session.id, session);
        // What arrived while nobody watched (C7): presented on attach, then CONSUMED — the
        // replay the surface just received is the content those markers pointed at.
        const unseen = this.opts.awareness?.unseenFor(command.runtime) ?? [];
        socket.send(
          JSON.stringify({
            type: "attach_ok",
            session_id: session.id,
            protocol_version: SURFACE_PROTOCOL_VERSION,
            runtime: command.runtime,
            replay,
            cursor,
            unseen,
            warnings,
          }),
        );
        if (unseen.length > 0) this.opts.awareness?.markSeen(command.runtime);
        // Held-pending approvals reach a newly-attached capable surface immediately.
        if (session.capabilities.has("approvals")) {
          for (const approval of this.opts.approvals.pendingApprovals()) {
            if (key(approval.runtime) === key(command.runtime)) {
              this.sendTo(session, {
                type: "approval_request",
                approval_id: approval.approvalId,
                runtime: approval.runtime,
                request: approval.request,
              });
            }
          }
        }
        return;
      }

      if (!session) {
        socket.send(JSON.stringify({ type: "error", message: "attach first" }));
        return;
      }

      if (command.type === "send") {
        // C8: the route resolves BEFORE any model call. Explicit @address beats a binding
        // beats the ordinary lane; an address that matches nothing is a visible error, not a
        // model call.
        let resolved: ReturnType<NonNullable<typeof this.opts.routes>["resolveSend"]> = null;
        if (this.opts.routes) {
          try {
            resolved = this.opts.routes.resolveSend(session.runtime, command.text);
          } catch (e) {
            this.sendTo(session, {
              type: "error",
              request_id: command.request_id,
              message: e instanceof RouteMissError ? e.message : "route resolution failed",
            });
            return;
          }
        }
        const target = resolved?.target ?? session.runtime;
        const clientMessageId = this.opts.pipeline.accept(target, resolved?.text ?? command.text, {
          via: resolved ? "direct" : "surface",
          session: session.id,
          ...(resolved
            ? {
                route: resolved.alias ?? "binding",
                origin_runtime: session.runtime,
              }
            : {}),
        });
        this.sendTo(session, {
          type: "send_ok",
          request_id: command.request_id,
          client_message_id: clientMessageId,
          ...(resolved ? { routed_to: target, route: resolved.alias ?? "binding" } : {}),
        });
        return;
      }

      if (command.type === "bind") {
        if (!this.opts.routes) {
          this.sendTo(session, {
            type: "error",
            request_id: command.request_id,
            message: "routing unavailable",
          });
          return;
        }
        try {
          const route = this.opts.routes.bind(
            session.runtime,
            command.alias,
            `surface:${session.id}`,
          );
          this.sendTo(session, {
            type: "bind_ok",
            request_id: command.request_id,
            alias: command.alias,
            target: { agent_id: route.agent_id, conversation_id: route.conversation_id },
          });
        } catch (e) {
          this.sendTo(session, {
            type: "error",
            request_id: command.request_id,
            message: e instanceof Error ? e.message : String(e),
          });
        }
        return;
      }

      if (command.type === "unbind") {
        const removed = this.opts.routes?.unbind(session.runtime, `surface:${session.id}`) ?? false;
        this.sendTo(session, { type: "unbind_ok", request_id: command.request_id, removed });
        return;
      }

      if (command.type === "presence") {
        session.presence = command.state;
        return;
      }

      if (command.type === "abort") {
        if (!session.capabilities.has("abort")) {
          this.sendTo(session, {
            type: "error",
            request_id: command.request_id,
            message: "abort capability not declared",
          });
          return;
        }
        const target = session;
        void this.opts.pipeline
          .abortActive(target.runtime, target.id)
          .then((aborted) =>
            this.sendTo(target, { type: "abort_ok", request_id: command.request_id, aborted }),
          )
          .catch((e) =>
            this.sendTo(target, {
              type: "error",
              request_id: command.request_id,
              message: e instanceof Error ? e.message : String(e),
            }),
          );
        return;
      }

      if (command.type === "approval_answer") {
        if (!session.capabilities.has("approvals")) {
          this.sendTo(session, { type: "error", message: "approvals capability not declared" });
          return;
        }
        const won = this.opts.approvals.answer(command.approval_id, command.decision, session.id);
        if (!won) {
          // Already settled (or unanswerable right now) — the surface sees the resolution
          // shape, not an error: losing the race is normal.
          this.sendTo(session, {
            type: "approval_resolved",
            approval_id: command.approval_id,
            decision: { behavior: command.decision.behavior },
            by: "already-settled",
          });
        }
        return;
      }
    });
    socket.on("close", () => {
      if (session) this.sessions.delete(session.id);
    });
    socket.on("error", () => {
      if (session) this.sessions.delete(session.id);
    });
  }

  private fanOutEvent(row: TurnEventRow): void {
    for (const [, s] of this.sessions) {
      if (s.runtime.agent_id !== row.agent_id || s.runtime.conversation_id !== row.conversation_id)
        continue;
      // Core tier gets journal events; approval frames ride their own capability-gated channel.
      this.sendTo(s, this.toEvent(row));
      s.cursor = row.id;
    }
    // C8 inline rendering (R12/R24): a direct-lane exchange journals in the SPECIALIST's
    // thread, and the surfaces attached to its ROUTE-ORIGIN thread see it inline as a
    // clearly-attributed foreign-thread event (capability `direct`).
    if (!row.client_message_id) return;
    const queueRow = this.opts.pipeline.rowFor(row.client_message_id);
    const origin = queueRow?.origin as
      | { via?: string; origin_runtime?: RuntimeRef; route?: string }
      | undefined;
    if (origin?.via !== "direct" || !origin.origin_runtime) return;
    for (const [, s] of this.sessions) {
      if (key(s.runtime) !== key(origin.origin_runtime)) continue;
      if (!s.capabilities.has("direct")) continue;
      this.sendTo(s, {
        type: "foreign_event",
        route: origin.route ?? "direct",
        origin_runtime: origin.origin_runtime,
        specialist: { agent_id: row.agent_id, conversation_id: row.conversation_id },
        event: this.toEvent(row),
      });
    }
  }

  private toEvent(row: TurnEventRow): SurfaceEvent {
    return {
      type: "event",
      id: row.id,
      kind: row.kind,
      client_message_id: row.client_message_id,
      payload: row.payload,
      at: row.at,
    };
  }

  private sendTo(session: Session, frame: unknown): void {
    if (session.socket.readyState !== WebSocket.OPEN) return;
    try {
      session.socket.send(JSON.stringify(frame));
    } catch (e) {
      this.opts.onWarn?.(
        `surface send failed for ${session.id}: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
  }
}
