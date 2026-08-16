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
import { type Server as HttpServer, createServer } from "node:http";
import { createRequire } from "node:module";
import type { ApprovalArbiter, ApprovalDecision, PendingApproval } from "../approvals.js";
import type { TurnEventRow, TurnJournal } from "../journal.js";
import type { RuntimeRef } from "../registry.js";
import type { AwarenessManager } from "../routing/awareness.js";
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
      // The ticket-mint endpoint is a C9 deliverable; refusing loudly beats a silent 404.
      res.statusCode = 501;
      res.end("continuity-controller surface: WS only; browser tickets land with C9\n");
      void req;
    });
    this.wss = new WebSocketServer({ server: this.http, path: "/surface" });
    this.wss.on("connection", (socket) => this.onConnection(socket));
    await new Promise<void>((resolve) => this.http?.listen(port, "127.0.0.1", resolve));
    this.unsubscribeJournal = this.opts.journal.onRecord((row) => this.fanOutEvent(row));
    const address = this.http.address();
    return typeof address === "object" && address !== null ? address.port : port;
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
        const clientMessageId = this.opts.pipeline.accept(session.runtime, command.text, {
          via: "surface",
          session: session.id,
        });
        this.sendTo(session, {
          type: "send_ok",
          request_id: command.request_id,
          client_message_id: clientMessageId,
        });
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
