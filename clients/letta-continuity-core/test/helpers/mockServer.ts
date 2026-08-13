/**
 * In-process mock of the sole-owner Letta App Server `/ws` surface.
 *
 * Emits the EXACT empirical frame shapes captured from `letta 0.30.19` (see Unit 4 captures):
 *   runtime_start_response · update_loop_status · stream_delta · turn_finished ·
 *   update_subagent_state · update_queue · conversation_list_response ·
 *   conversation_create_response · conversation_messages_list_response · approval_request_message.
 *
 * Per-connection `event_seq` (as the real server does). Lets tests drive foreign turns,
 * concurrency serialization, approvals, and mid-turn socket drops — all deterministic, offline.
 */

import type { AddressInfo } from "node:net";
import { type RawData, type WebSocket, WebSocketServer } from "ws";

interface ConnState {
  socket: WebSocket;
  seq: number;
  runtime: { agent_id: string; conversation_id: string } | null;
}

export interface TurnMessage {
  id: string;
  messageType: string;
  text: string;
}

export interface MockServerOptions {
  /** If set, added to runtime_start_response as `server_version` (to exercise version assertion). */
  serverVersion?: string;
  /** Snapshot returned by conversation_messages_list. */
  messagesSnapshot?: Array<{ id?: string; [k: string]: unknown }>;
  /** conversation_messages_list_response.success (default true). */
  messagesSuccess?: boolean;
  messagesError?: string;
  /** conversation_list_response payload. */
  conversations?: Array<Record<string, unknown>>;
  /** If true, an `input` triggers an approval_request_message instead of completing a turn. */
  approvalMode?: boolean;
  /** If false, the server never auto-responds to `input` (tests drive turns manually). */
  autoTurnOnInput?: boolean;
}

let uid = 0;
function idem(type: string, seq: number): string {
  uid += 1;
  return `${type}:${seq}:mock-${uid}`;
}

export class MockAppServer {
  private wss: WebSocketServer | null = null;
  private readonly conns = new Set<ConnState>();
  private runCounter = 0;
  /** Frames received from clients, for assertions (e.g. approval_send). */
  readonly received: Array<Record<string, unknown>> = [];
  options: MockServerOptions;
  /** Simple per-runtime serialization flag for the concurrency test. */
  private busy = new Map<string, boolean>();
  private queued = new Map<string, Array<{ conn: ConnState; text: string }>>();

  constructor(options: MockServerOptions = {}) {
    this.options = { autoTurnOnInput: true, ...options };
  }

  private bump(): number {
    this.runCounter += 1;
    return this.runCounter;
  }

  async start(): Promise<string> {
    this.wss = new WebSocketServer({ host: "127.0.0.1", port: 0 });
    await new Promise<void>((resolve) => this.wss?.once("listening", () => resolve()));
    const port = (this.wss.address() as AddressInfo).port;
    this.wss.on("connection", (socket) => this.onConnection(socket));
    return `ws://127.0.0.1:${port}/ws`;
  }

  async stop(): Promise<void> {
    for (const c of this.conns) c.socket.terminate();
    this.conns.clear();
    await new Promise<void>((resolve) => {
      if (!this.wss) return resolve();
      this.wss.close(() => resolve());
    });
    this.wss = null;
  }

  /** Simulate a watchdog stall-restart: drop every client socket at once. */
  dropAllConnections(): void {
    for (const c of this.conns) c.socket.terminate();
    this.conns.clear();
  }

  get connectionCount(): number {
    return this.conns.size;
  }

  private onConnection(socket: WebSocket): void {
    const conn: ConnState = { socket, seq: 0, runtime: null };
    this.conns.add(conn);
    socket.on("message", (data: RawData) => this.onMessage(conn, data));
    socket.on("close", () => this.conns.delete(conn));
    socket.on("error", () => {});
  }

  private onMessage(conn: ConnState, data: RawData): void {
    const msg = JSON.parse(data.toString()) as Record<string, unknown>;
    this.received.push(msg);
    const type = msg.type as string;
    if (type === "runtime_start") this.handleRuntimeStart(conn, msg);
    else if (type === "input") this.handleInput(conn, msg);
    else if (type === "conversation_list") this.handleConversationList(conn, msg);
    else if (type === "conversation_create") this.handleConversationCreate(conn, msg);
    else if (type === "conversation_messages_list") this.handleMessagesList(conn, msg);
    else if (type === "approval_send") this.handleApprovalSend(conn, msg);
  }

  private handleRuntimeStart(conn: ConnState, msg: Record<string, unknown>): void {
    conn.runtime = {
      agent_id: msg.agent_id as string,
      conversation_id: msg.conversation_id as string,
    };
    const hello: Record<string, unknown> = {
      type: "runtime_start_response",
      request_id: msg.request_id,
      success: true,
      runtime: conn.runtime,
      agent: { id: conn.runtime.agent_id, name: "mock-agent" },
      conversation: conn.runtime.conversation_id,
      created: { agent: false, conversation: false },
    };
    if (this.options.serverVersion) hello.server_version = this.options.serverVersion;
    conn.socket.send(JSON.stringify(hello));
    // initial loop status like the real server
    this.sendBroadcast(conn, "update_loop_status", {
      loop_status: { status: "WAITING_ON_INPUT", active_run_ids: [], executing_tool_call_ids: [] },
    });
  }

  private handleInput(conn: ConnState, _msg: Record<string, unknown>): void {
    if (!conn.runtime) return;
    if (this.options.approvalMode) {
      const n = this.bump();
      this.sendBroadcast(conn, "approval_request_message", {
        approval_request_id: `appr-${n}`,
        run_id: `local-run-${n}`,
      });
      return;
    }
    if (!this.options.autoTurnOnInput) return;
    this.enqueueTurn(conn);
  }

  /** Serialize concurrent inputs on one runtime, emitting update_queue like the real server. */
  private enqueueTurn(conn: ConnState): void {
    const key = `${conn.runtime?.agent_id}/${conn.runtime?.conversation_id}`;
    const q = this.queued.get(key) ?? [];
    q.push({ conn, text: "" });
    this.queued.set(key, q);
    if (this.busy.get(key)) {
      this.sendBroadcast(conn, "update_queue", { queue: [{ id: `q-${q.length}` }], removed: [] });
      return;
    }
    this.drain(key);
  }

  private drain(key: string): void {
    const q = this.queued.get(key);
    if (!q || q.length === 0) {
      this.busy.set(key, false);
      return;
    }
    this.busy.set(key, true);
    const item = q.shift() as { conn: ConnState; text: string };
    const runId = `local-run-${this.bump()}`;
    const messages: TurnMessage[] = [
      { id: `letta-msg-${1000 + this.runCounter}`, messageType: "assistant_message", text: "OK" },
    ];
    this.broadcastTurn(item.conn.runtime as ConnState["runtime"], runId, messages);
    // remove from queue indicator, then process the next one
    this.sendBroadcastAll(item.conn.runtime, "update_queue", {
      queue: [],
      removed: [{ id: "q-1" }],
    });
    setImmediate(() => this.drain(key));
  }

  /** Broadcast a full turn (own or FOREIGN) to every socket subscribed to the runtime. */
  broadcastTurn(
    runtime: ConnState["runtime"],
    runId: string,
    messages: TurnMessage[],
    stopReason = "end_turn",
  ): void {
    if (!runtime) return;
    for (const conn of this.subscribers(runtime)) {
      this.sendBroadcast(conn, "update_loop_status", {
        loop_status: {
          status: "SENDING_API_REQUEST",
          active_run_ids: [runId],
          executing_tool_call_ids: [],
        },
      });
      for (const m of messages) {
        this.sendBroadcast(conn, "stream_delta", {
          delta: {
            id: m.id,
            date: "2026-08-13T00:00:00.000Z",
            agent_id: runtime.agent_id,
            conversation_id: runtime.conversation_id,
            message_type: m.messageType,
            otid: `otid-${m.id}`,
            content: m.text,
            run_id: runId,
            seq_id: 1,
            type: "message",
          },
        });
      }
      this.sendBroadcast(conn, "turn_finished", {
        turn_id: `batch-${runId}`,
        stop_reason: stopReason,
        run_id: runId,
      });
      this.sendBroadcast(conn, "update_loop_status", {
        loop_status: {
          status: "WAITING_ON_INPUT",
          active_run_ids: [],
          executing_tool_call_ids: [],
        },
      });
    }
  }

  /** Public helper for tests: inject a foreign turn addressed to a runtime. */
  injectForeignTurn(
    runtime: { agent_id: string; conversation_id: string },
    runId: string,
    messages: TurnMessage[],
  ): void {
    this.broadcastTurn(runtime, runId, messages);
  }

  private handleConversationList(conn: ConnState, msg: Record<string, unknown>): void {
    conn.socket.send(
      JSON.stringify({
        type: "conversation_list_response",
        request_id: msg.request_id,
        success: true,
        conversations: this.options.conversations ?? [
          {
            id: "local-conv-1",
            agent_id: msg.agent_id,
            archived: false,
            archived_at: null,
            created_at: "2026-08-12T00:00:00.000Z",
            updated_at: "2026-08-12T00:00:00.000Z",
          },
        ],
      }),
    );
  }

  private handleConversationCreate(conn: ConnState, msg: Record<string, unknown>): void {
    conn.socket.send(
      JSON.stringify({
        type: "conversation_create_response",
        request_id: msg.request_id,
        success: true,
        conversation: { id: `local-conv-new-${this.bump()}`, agent_id: msg.agent_id },
      }),
    );
  }

  private handleMessagesList(conn: ConnState, msg: Record<string, unknown>): void {
    conn.socket.send(
      JSON.stringify({
        type: "conversation_messages_list_response",
        request_id: msg.request_id,
        success: this.options.messagesSuccess ?? true,
        messages: this.options.messagesSnapshot ?? [],
        next_before: null,
        has_more: false,
        error: this.options.messagesError ?? null,
      }),
    );
  }

  private handleApprovalSend(conn: ConnState, msg: Record<string, unknown>): void {
    // Resolve the approval as a bounded, cancelled turn (fail-closed path).
    if (!conn.runtime) return;
    const runId = `local-run-appr-${this.bump()}`;
    this.broadcastTurn(conn.runtime, runId, [], msg.decision === "deny" ? "cancelled" : "end_turn");
  }

  private subscribers(runtime: { agent_id: string; conversation_id: string }): ConnState[] {
    return [...this.conns].filter(
      (c) =>
        c.runtime?.agent_id === runtime.agent_id &&
        c.runtime?.conversation_id === runtime.conversation_id,
    );
  }

  private sendBroadcast(conn: ConnState, type: string, payload: Record<string, unknown>): void {
    conn.seq += 1;
    conn.socket.send(
      JSON.stringify({
        type,
        ...payload,
        runtime: conn.runtime,
        event_seq: conn.seq,
        emitted_at: "2026-08-13T00:00:00.000Z",
        idempotency_key: idem(type, conn.seq),
      }),
    );
  }

  private sendBroadcastAll(
    runtime: ConnState["runtime"],
    type: string,
    payload: Record<string, unknown>,
  ): void {
    if (!runtime) return;
    for (const conn of this.subscribers(runtime)) this.sendBroadcast(conn, type, payload);
  }
}
