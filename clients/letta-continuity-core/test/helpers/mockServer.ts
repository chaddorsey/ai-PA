/**
 * In-process mock of the sole-owner Letta App Server `/ws` surface.
 *
 * Emits the EXACT empirical frame shapes captured from `letta 0.30.19` (see Unit 4 captures):
 *   app_server_info_response · runtime_start_response · update_loop_status · stream_delta · turn_finished ·
 *   update_subagent_state · update_queue · conversation_list_response ·
 *   conversation_create_response · conversation_messages_list_response · approval_request_message.
 *
 * Per-connection `event_seq` (as the real server does). Lets tests drive foreign turns,
 * concurrency serialization, approvals, and mid-turn socket drops — all deterministic, offline.
 */

import type { AddressInfo } from "node:net";
import { type RawData, type WebSocket, WebSocketServer } from "ws";
import { PINNED_PROTOCOL_VERSION, PINNED_SERVER_VERSION } from "../../src/protocol.js";

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
  /** `letta_code_version` reported by app_server_info (default: the pinned version). */
  serverVersion?: string;
  /** `protocol_version` reported by app_server_info (default: the pinned protocol version). */
  protocolVersion?: number;
  /** Capability overrides merged over the real 0.30.19 capability map. */
  capabilities?: Record<string, boolean>;
  /** If true, the server does not answer `app_server_info` at all (an older build). */
  omitAppServerInfo?: boolean;
  /**
   * If true, answer `app_server_info` with a frame that fails validation (drift), rather than not
   * answering at all. These are different failure classes and the version gate must tell them apart.
   */
  driftAppServerInfo?: boolean;
  /** Snapshot returned by conversation_messages_list. */
  messagesSnapshot?: Array<{ id?: string; [k: string]: unknown }>;
  /** conversation_messages_list_response.success (default true). */
  messagesSuccess?: boolean;
  messagesError?: string;
  /** conversation_list_response payload. */
  conversations?: Array<Record<string, unknown>>;
  /** If true, an `input` triggers an approval_request_message instead of completing a turn. */
  approvalMode?: boolean;
  /**
   * Emit the dequeue notice AFTER the run starts — the inverse of the captured live ordering.
   * ownership.ts hardens against this defensively, so it is worth being able to drive it.
   */
  dequeueAfterRunStart?: boolean;
  /** If false, the server never auto-responds to `input` (tests drive turns manually). */
  autoTurnOnInput?: boolean;
  /**
   * Command types the server accepts but never answers, so a test can supply the response itself
   * via sendRaw (e.g. to inject a drifted frame as the ONLY answer to a live RPC).
   */
  suppressResponsesFor?: string[];
  /**
   * Force the `input_accepted` disposition, simulating this client sitting behind a peer's
   * in-flight turn without having to script the peer's whole turn.
   */
  inputDisposition?: "started" | "queued";
}

/** Split a message body into per-chunk deltas the way a streaming provider does. */
function splitIntoChunks(text: string): string[] {
  if (text.length <= 1) return [text];
  const mid = Math.ceil(text.length / 2);
  return [text.slice(0, mid), text.slice(mid)];
}

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
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
  /** Frames received from clients, for assertions (e.g. the approval-deny `input`). */
  readonly received: Array<Record<string, unknown>> = [];
  /** Count of frames dropped by a command guard (malformed envelope). */
  rejected = 0;
  /** control_request ids already answered — the server's own at-most-once guard. */
  private readonly settledApprovals = new Set<string>();
  options: MockServerOptions;
  /** Simple per-runtime serialization flag for the concurrency test. */
  private busy = new Map<string, boolean>();
  private queued = new Map<
    string,
    Array<{ conn: ConnState; text: string; clientMessageId: string }>
  >();

  constructor(options: MockServerOptions = {}) {
    this.options = { autoTurnOnInput: true, ...options };
  }

  private bump(): number {
    this.runCounter += 1;
    return this.runCounter;
  }

  /** `port` lets a test restart the server on the SAME port, as a supervisor would. */
  async start(port = 0): Promise<string> {
    this.wss = new WebSocketServer({ host: "127.0.0.1", port });
    await new Promise<void>((resolve) => this.wss?.once("listening", () => resolve()));
    const bound = (this.wss.address() as AddressInfo).port;
    this.wss.on("connection", (socket) => this.onConnection(socket));
    return `ws://127.0.0.1:${bound}/ws`;
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

  /**
   * Send an arbitrary payload to every connected client, bypassing every builder. The only way to
   * exercise what the client does with a frame it considers malformed or drifted.
   */
  sendRaw(payload: unknown): void {
    const text = typeof payload === "string" ? payload : JSON.stringify(payload);
    for (const c of this.conns) c.socket.send(text);
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
    if (this.options.suppressResponsesFor?.includes(type)) return;
    if (type === "app_server_info") this.handleAppServerInfo(conn, msg);
    else if (type === "runtime_start") {
      // isRuntimeStartCommand: both ids must be present strings. Previously this was the one
      // command with no guard, and it cast them instead — so a builder that nested the runtime
      // would produce {agent_id: undefined} and fail downstream on `missing runtime`, pointing
      // the blame anywhere but at the builder that regressed.
      if (this.guard(typeof msg.agent_id === "string" && typeof msg.conversation_id === "string")) {
        this.handleRuntimeStart(conn, msg);
      }
    } else if (type === "input") {
      // isInputCommand: payload object, and for create_message a messages ARRAY. For
      // approval_response the server additionally requires payload.request_id and a decision.
      const p = isObj(msg.payload) ? msg.payload : null;
      const okCreate =
        p?.kind === "create_message" && Array.isArray((p as { messages?: unknown }).messages);
      const okApproval =
        p?.kind === "approval_response" &&
        typeof (p as { request_id?: unknown }).request_id === "string" &&
        (isObj((p as { decision?: unknown }).decision) ||
          typeof (p as { error?: unknown }).error === "string");
      if (this.guard(Boolean(okCreate || okApproval))) this.handleInput(conn, msg);
    } else if (type === "conversation_list") {
      if (this.guard(isObj(msg.query) || msg.query === undefined)) {
        this.handleConversationList(conn, msg);
      }
    } else if (type === "conversation_create") {
      if (this.guard(isObj(msg.body))) this.handleConversationCreate(conn, msg);
    } else if (type === "conversation_messages_list") {
      if (this.guard(typeof msg.conversation_id === "string")) this.handleMessagesList(conn, msg);
    }
  }

  /**
   * Reproduce the real server's command guards. A frame that fails a guard is DROPPED
   * SILENTLY — no error response, the client's RPC just times out. Mirroring this is the
   * whole point: a mock that answers any shape will rubber-stamp a malformed builder, which
   * is exactly how `conversation_create` shipped with the wrong envelope in Unit 4.
   */
  private guard(ok: boolean): boolean {
    if (!ok) this.rejected += 1;
    return ok;
  }

  /** Mirrors the live 0.30.19 `app_server_info_response` (captured verbatim from :4577). */
  private handleAppServerInfo(conn: ConnState, msg: Record<string, unknown>): void {
    if (this.options.omitAppServerInfo) return; // an older server: never answers
    if (this.options.driftAppServerInfo) {
      // Correct type + request_id so it routes to the pending RPC, but `success` is gone —
      // exactly the shape a field rename produces.
      conn.socket.send(
        JSON.stringify({ type: "app_server_info_response", request_id: msg.request_id }),
      );
      return;
    }
    conn.socket.send(
      JSON.stringify({
        type: "app_server_info_response",
        request_id: msg.request_id,
        success: true,
        backend: "local",
        letta_code_version: this.options.serverVersion ?? PINNED_SERVER_VERSION,
        protocol_version: this.options.protocolVersion ?? PINNED_PROTOCOL_VERSION,
        capabilities: {
          agent_management: true,
          conversation_management: true,
          memory_management: true,
          runtime_start: true,
          runtime_external_tools_update: true,
          split_channels: false,
          ...this.options.capabilities,
        },
      }),
    );
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
    // NOTE: no version field here — the real hello carries none. Version lives in app_server_info.
    conn.socket.send(JSON.stringify(hello));
    // initial loop status like the real server
    this.sendBroadcast(conn, "update_loop_status", {
      loop_status: { status: "WAITING_ON_INPUT", active_run_ids: [], executing_tool_call_ids: [] },
    });
  }

  /**
   * Mirrors the real input path, including the correlation handles ownership.ts depends on:
   * an `input_accepted` ack (emitted ONLY when the input carried a request_id) whose
   * `disposition` is `started` or `queued`, and `update_queue` entries keyed by the client's
   * own `client_message_id`.
   */
  private handleInput(conn: ConnState, msg: Record<string, unknown>): void {
    if (!conn.runtime) return;
    const payload = isObj(msg.payload) ? msg.payload : {};
    if (payload.kind === "approval_response") {
      // Server-side at-most-once: the first response wins; later ones are told it is settled.
      const settledId = String(payload.request_id);
      const first = !this.settledApprovals.has(settledId);
      this.settledApprovals.add(settledId);
      if (typeof msg.request_id === "string") {
        conn.socket.send(
          JSON.stringify({
            type: "input_accepted",
            request_id: msg.request_id,
            runtime: conn.runtime,
            accepted: first,
            ...(first ? {} : { error: "Approval request is no longer pending" }),
          }),
        );
      }
      return;
    }
    const clientMessageId =
      typeof payload.client_message_id === "string" ? payload.client_message_id : `cm-${uid}`;
    const key = `${conn.runtime.agent_id}/${conn.runtime.conversation_id}`;
    const willQueue = this.options.inputDisposition
      ? this.options.inputDisposition === "queued"
      : this.busy.get(key) === true;

    if (typeof msg.request_id === "string") {
      conn.socket.send(
        JSON.stringify({
          type: "input_accepted",
          request_id: msg.request_id,
          runtime: conn.runtime,
          accepted: true,
          disposition: willQueue ? "queued" : "started",
        }),
      );
    }

    if (this.options.approvalMode) {
      // The REAL shape (0.30.20 requestApprovalOverWS): announce the run so clients can attribute
      // it, then broadcast a top-level control_request to EVERY subscriber — not just the
      // initiator. The server settles the race itself, so every subscriber answering is expected.
      const runId = `local-run-${this.bump()}`;
      this.sendBroadcastAll(conn.runtime, "update_loop_status", {
        loop_status: {
          status: "SENDING_API_REQUEST",
          active_run_ids: [runId],
          executing_tool_call_ids: [],
        },
      });
      const toolCallId = `toolu_${runId}`;
      for (const sub of this.subscribers(conn.runtime)) {
        sub.socket.send(
          JSON.stringify({
            type: "control_request",
            request_id: `perm-${toolCallId}`,
            request: {
              subtype: "can_use_tool",
              tool_name: "Bash",
              input: { command: "echo hi" },
              tool_call_id: toolCallId,
              permission_suggestions: [],
              blocked_path: null,
            },
            agent_id: conn.runtime.agent_id,
            conversation_id: conn.runtime.conversation_id,
          }),
        );
      }
      return;
    }
    if (!this.options.autoTurnOnInput) return;
    this.enqueueTurn(conn, clientMessageId);
  }

  /** Serialize concurrent inputs on one runtime, emitting update_queue like the real server. */
  private enqueueTurn(conn: ConnState, clientMessageId: string): void {
    const key = `${conn.runtime?.agent_id}/${conn.runtime?.conversation_id}`;
    const q = this.queued.get(key) ?? [];
    q.push({ conn, text: "", clientMessageId });
    this.queued.set(key, q);
    if (this.busy.get(key)) {
      // Queue frames are broadcast to EVERY subscriber — each client matches only its own id.
      this.sendBroadcastAll(conn.runtime, "update_queue", {
        queue: q.map((item, i) => ({
          id: `q-${i + 1}`,
          client_message_id: item.clientMessageId,
          kind: "message",
          source: "user",
        })),
        removed: [],
      });
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
    const item = q.shift() as { conn: ConnState; text: string; clientMessageId: string };
    const runId = `local-run-${this.bump()}`;
    const messages: TurnMessage[] = [
      { id: `letta-msg-${1000 + this.runCounter}`, messageType: "assistant_message", text: "OK" },
    ];
    // Announce the dequeue by the client's own id BEFORE the run starts — this is the order the
    // live server was captured using, and it is how a QUEUED client learns which run to claim.
    //
    // This used to run AFTER broadcastTurn, i.e. the inverse. The consequence was not a cosmetic
    // mismatch: the ordering a real client will actually meet was never exercised through the
    // wire at all, so the queued→armed→owned chain — the whole reason ownership.ts exists — had
    // no end-to-end coverage. `dequeueAfterRunStart` keeps the inverse available on purpose,
    // because ownership.ts hardens against it defensively and that hardening deserves a test too.
    const announceDequeue = (): void => {
      this.sendBroadcastAll(item.conn.runtime, "update_queue", {
        queue: q.map((qi, i) => ({
          id: `q-${i + 1}`,
          client_message_id: qi.clientMessageId,
          kind: "message",
          source: "user",
        })),
        removed: [{ client_message_id: item.clientMessageId, disposition: "dequeued" }],
      });
    };

    if (this.options.dequeueAfterRunStart) {
      this.broadcastTurn(item.conn.runtime as ConnState["runtime"], runId, messages);
      announceDequeue();
    } else {
      announceDequeue();
      this.broadcastTurn(item.conn.runtime as ConnState["runtime"], runId, messages);
    }
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
        // The live server splits one message across MANY deltas, each with its OWN delta.id
        // (letta-msg-26735, -26736, …) while `otid` stays constant for the message. A double that
        // emits one delta per message hides both the per-chunk id reality AND any line-breaking
        // bug that depends on it — which is exactly how the "agent › HE / LL / O" defect shipped.
        const chunks = splitIntoChunks(m.text);
        for (const [i, chunk] of chunks.entries()) {
          this.sendBroadcast(conn, "stream_delta", {
            delta: {
              id: `${m.id}-${i}`,
              date: "2026-08-13T00:00:00.000Z",
              agent_id: runtime.agent_id,
              conversation_id: runtime.conversation_id,
              message_type: m.messageType,
              otid: `otid-${m.id}`,
              content: chunk,
              run_id: runId,
              seq_id: i + 1,
              type: "message",
            },
          });
        }
      }
      // Every real turn ends with these two control deltas. `stop_reason` carries NO delta.id —
      // the frame that used to be rejected by the watermark guard on every single turn.
      this.sendBroadcast(conn, "stream_delta", {
        delta: {
          id: `${runId}-usage`,
          message_type: "usage_statistics",
          run_id: runId,
          seq_id: 900,
          type: "message",
        },
      });
      this.sendBroadcast(conn, "stream_delta", {
        delta: {
          message_type: "stop_reason",
          stop_reason: stopReason,
          run_id: runId,
          seq_id: 901,
          type: "message",
        },
      });
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
    const query = isObj(msg.query) ? msg.query : {};
    conn.socket.send(
      JSON.stringify({
        type: "conversation_list_response",
        request_id: msg.request_id,
        success: true,
        conversations: this.options.conversations ?? [
          {
            id: "local-conv-1",
            agent_id: query.agent_id,
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
    const body = isObj(msg.body) ? msg.body : {};
    conn.socket.send(
      JSON.stringify({
        type: "conversation_create_response",
        request_id: msg.request_id,
        success: true,
        conversation: { id: `local-conv-new-${this.bump()}`, agent_id: body.agent_id },
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
