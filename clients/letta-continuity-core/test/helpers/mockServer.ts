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
import {
  Backends,
  ControlRequestSubtypes,
  DeltaMessageTypes,
  Inbound,
  InputDispositions,
  InputKinds,
  LoopStatuses,
  Outbound,
  PINNED_PROTOCOL_VERSION,
  PINNED_SERVER_VERSION,
  QueueDispositions,
  QueueSources,
  type ServerFrame,
  StopReasons,
  WireEnvelope,
} from "../../src/protocol.js";
import { WsConnection, type WsConnectionOptions } from "../../src/ws.js";

/**
 * A real `WsConnection` whose WRITES can be made to fail on cue.
 *
 * Everything else — the socket, the hello, the version gate, frame routing — is the production
 * class. Only `send` is faultable, because that is the one condition a mock SERVER cannot produce:
 * the frame that triggers a send and the send itself run in the same tick, so nothing the server
 * does can put the socket into a non-writable state in between. Pass the factory to
 * `ContinuityCore({ createConnection })`.
 */
export class FaultyWsConnection extends WsConnection {
  /** Set to a message to make every subsequent `send` throw; null to write normally again. */
  static failSendsWith: string | null = null;
  /** Frames whose send was rejected, for assertions. */
  static readonly refused: ServerFrame[] = [];

  override send(frame: ServerFrame): void {
    if (FaultyWsConnection.failSendsWith !== null) {
      FaultyWsConnection.refused.push(frame);
      throw new Error(FaultyWsConnection.failSendsWith);
    }
    super.send(frame);
  }

  /** Restore normal writes and forget what was refused. Call in `afterEach`. */
  static reset(): void {
    FaultyWsConnection.failSendsWith = null;
    FaultyWsConnection.refused.length = 0;
  }

  static factory(options: WsConnectionOptions): WsConnection {
    return new FaultyWsConnection(options);
  }
}

interface ConnState {
  socket: WebSocket;
  seq: number;
  runtime: { agent_id: string; conversation_id: string } | null;
  /** True while this connection is refusing to answer a close handshake. */
  held: boolean;
  /** 0-based order of acceptance, so a test can single out the FIRST attach. */
  index: number;
}

/**
 * Stop reading from a client socket without closing it.
 *
 * `ws.pause()` pauses the receiver, so an inbound close frame is never parsed and therefore never
 * answered. The `_socket` fallback covers builds without the public method; both do the same job
 * at the level that matters, which is "the peer's close frame is not processed".
 */
function pauseSocket(socket: WebSocket): void {
  if (typeof socket.pause === "function") socket.pause();
  else (socket as unknown as { _socket?: { pause(): void } })._socket?.pause();
}

function resumeSocket(socket: WebSocket): void {
  if (typeof socket.resume === "function") socket.resume();
  else (socket as unknown as { _socket?: { resume(): void } })._socket?.resume();
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
  inputDisposition?: typeof InputDispositions.started | typeof InputDispositions.queued;
  /**
   * Answer an `input` with the captured MULTI-RUN shape of a tool-using reply rather than the
   * single-run shape.
   *
   * Captured live on 0.30.20: the run our send starts is never closed. A tool call suspends it,
   * a NEW run carries the reply, and only that second run emits `turn_finished`. A double that
   * always closes the run it started cannot produce that, so every property that depends on it —
   * one-shot termination, continuation-run attribution, the idle reaper being load-bearing rather
   * than a nicety — was asserted against a shape the client never meets.
   */
  toolUse?: boolean;
  /**
   * Like `suppressResponsesFor`, but only on the FIRST connection this server accepts.
   *
   * Lets one test drive "the attach failed, then the retry succeeded" against one server, which is
   * the only way to get a client into the state the identity guards exist for: a first connection
   * that was closed by us and a second, healthy one that is current.
   */
  suppressFirstResponseFor?: string[];
  /**
   * On the FIRST connection, stop reading once a frame of this type arrives — so the close
   * handshake the client subsequently starts is never answered and its `close` event is deferred
   * until `releaseCloseHandshakes()`.
   */
  holdFirstConnectionCloseAfter?: string;
  /** On the FIRST connection, terminate abruptly once a frame of this type arrives. */
  dropFirstConnectionAfter?: string;
  /**
   * Refuse every `input` with `accepted:false` and this error, the way the server answers a send
   * against a runtime that is no longer active.
   */
  rejectInputWith?: string;
  /**
   * Answer an `input` with one of the two shapes an ERRORED turn actually takes.
   *
   * There was no way to produce either before, which is why B1 and B4 — a silent blackout and a
   * three-minute hang on the commonest real fault, a provider outage — shipped green. The error
   * path had no fixture at all, so "the suite passes" only ever meant "the happy path passes".
   *
   * - `"deltas"`: the shape captured live against a 404-model agent. A `loop_error` and a
   *   human-readable `error_message` delta, then `WAITING_ON_INPUT` — and **no `turn_finished`,
   *   ever**. A client that renders neither delta and waits for a stop reason shows an empty
   *   successful turn and exits 0.
   * - `"turn-finished"`: the other server path. The turn ends on `turn_finished{stop_reason:error}`
   *   with **no following idle**, so a client that terminates only on idle waits out its whole
   *   timeout and then blames the server for being slow.
   */
  erroredTurn?: "deltas" | "turn-finished";
  /** Text carried by the `error_message` delta. */
  errorText?: string;
}

/** Default `error_message` body — recognisable in assertions, and shaped like the real one. */
const DEFAULT_ERROR_TEXT =
  "Error code: 404 - model `openai/gpt-slop-1` not found or not accessible";

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
  /** How many connections this server has ever accepted — the source of ConnState.index. */
  private acceptedCount = 0;
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

  /** Simulate a watchdog stall-restart: drop every client socket at once (abrupt, no handshake). */
  dropAllConnections(): void {
    for (const c of this.conns) c.socket.terminate();
    this.conns.clear();
  }

  /**
   * Close every client socket GRACEFULLY — a close frame and a handshake, not a TCP reset.
   *
   * `dropAllConnections` uses `terminate()`, which makes the client's `close` event arrive
   * immediately and in lockstep with the drop. That is one real shape (a killed process) but not
   * the one three of this client's fixes guard against: a socket that is closed politely and whose
   * `close` event therefore lands whenever the handshake completes — which the `ws` package will
   * wait up to 30s for. Combined with `holdCloseHandshakes`, this is how a test produces a
   * SUPERSEDED-but-not-yet-closed connection deterministically.
   */
  closeAllConnections(code = 1001, reason = "server going away"): void {
    for (const c of this.conns) c.socket.close(code, reason);
  }

  /**
   * Stop answering close handshakes on every CURRENT connection.
   *
   * A client that calls `close()` sends a close frame and then waits for the peer's reply before
   * emitting `close`. Pausing the server's receiver means that reply never comes, so the client's
   * socket sits in CLOSING — open enough to keep receiving, not open enough to send. That is
   * exactly the lingering superseded socket the identity guards exist for, and the only state in
   * which a client-side `ws.send` can throw while frames are still arriving.
   *
   * Release it with `releaseCloseHandshakes()` to let the pending closes complete on cue.
   */
  holdCloseHandshakes(): void {
    for (const c of this.conns) {
      c.held = true;
      pauseSocket(c.socket);
    }
  }

  /** Let every held close handshake complete now, so the client's `close` events fire on cue. */
  releaseCloseHandshakes(): void {
    for (const c of this.conns) {
      if (!c.held) continue;
      c.held = false;
      resumeSocket(c.socket);
    }
  }

  get connectionCount(): number {
    return this.conns.size;
  }

  private onConnection(socket: WebSocket): void {
    const conn: ConnState = {
      socket,
      seq: 0,
      runtime: null,
      held: false,
      index: this.acceptedCount,
    };
    this.acceptedCount += 1;
    this.conns.add(conn);
    socket.on("message", (data: RawData) => this.onMessage(conn, data));
    socket.on("close", () => this.conns.delete(conn));
    socket.on("error", () => {});
  }

  /** Deliver a raw payload to ONE connection, so a test can address a superseded socket alone. */
  sendRawTo(index: number, payload: unknown): void {
    const text = typeof payload === "string" ? payload : JSON.stringify(payload);
    for (const c of this.conns) if (c.index === index) c.socket.send(text);
  }

  private onMessage(conn: ConnState, data: RawData): void {
    const msg = JSON.parse(data.toString()) as Record<string, unknown>;
    this.received.push(msg);
    const type = msg.type as string;
    const first = conn.index === 0;
    if (first && this.options.dropFirstConnectionAfter === type) {
      this.conns.delete(conn);
      conn.socket.terminate();
      return;
    }
    if (first && this.options.holdFirstConnectionCloseAfter === type) {
      conn.held = true;
      // Answer first, THEN stop reading: the point is to defer the client's close event, not to
      // withhold the response the client is waiting on.
      queueMicrotask(() => pauseSocket(conn.socket));
    }
    if (first && this.options.suppressFirstResponseFor?.includes(type)) return;
    if (this.options.suppressResponsesFor?.includes(type)) return;
    if (type === Outbound.appServerInfo) this.handleAppServerInfo(conn, msg);
    else if (type === Outbound.runtimeStart) {
      // isRuntimeStartCommand: both ids must be present strings. Previously this was the one
      // command with no guard, and it cast them instead — so a builder that nested the runtime
      // would produce {agent_id: undefined} and fail downstream on `missing runtime`, pointing
      // the blame anywhere but at the builder that regressed.
      if (this.guard(typeof msg.agent_id === "string" && typeof msg.conversation_id === "string")) {
        this.handleRuntimeStart(conn, msg);
      }
    } else if (type === Outbound.input) {
      // isInputCommand: payload object, and for create_message a messages ARRAY. For
      // approval_response the server additionally requires payload.request_id and a decision.
      const p = isObj(msg.payload) ? msg.payload : null;
      const okCreate =
        p?.kind === InputKinds.createMessage && Array.isArray((p as { messages?: unknown }).messages);
      const okApproval =
        p?.kind === InputKinds.approvalResponse &&
        typeof (p as { request_id?: unknown }).request_id === "string" &&
        (isObj((p as { decision?: unknown }).decision) ||
          typeof (p as { error?: unknown }).error === "string");
      if (this.guard(Boolean(okCreate || okApproval))) this.handleInput(conn, msg);
    } else if (type === Outbound.conversationList) {
      if (this.guard(isObj(msg.query) || msg.query === undefined)) {
        this.handleConversationList(conn, msg);
      }
    } else if (type === Outbound.conversationCreate) {
      if (this.guard(isObj(msg.body))) this.handleConversationCreate(conn, msg);
    } else if (type === Outbound.conversationMessagesList) {
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
        JSON.stringify({ type: Inbound.appServerInfoResponse, request_id: msg.request_id }),
      );
      return;
    }
    conn.socket.send(
      JSON.stringify({
        type: Inbound.appServerInfoResponse,
        request_id: msg.request_id,
        success: true,
        backend: Backends.local,
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
      type: Inbound.runtimeStartResponse,
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
    this.sendBroadcast(conn, Inbound.updateLoopStatus, {
      loop_status: { status: LoopStatuses.waitingOnInput, active_run_ids: [], executing_tool_call_ids: [] },
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
    if (payload.kind === InputKinds.approvalResponse) {
      // Server-side at-most-once: the first response wins; later ones are told it is settled.
      const settledId = String(payload.request_id);
      const first = !this.settledApprovals.has(settledId);
      this.settledApprovals.add(settledId);
      if (typeof msg.request_id === "string") {
        conn.socket.send(
          JSON.stringify({
            type: Inbound.inputAccepted,
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
      ? this.options.inputDisposition === InputDispositions.queued
      : this.busy.get(key) === true;

    if (this.options.rejectInputWith !== undefined) {
      if (typeof msg.request_id === "string") {
        conn.socket.send(
          JSON.stringify({
            type: Inbound.inputAccepted,
            request_id: msg.request_id,
            runtime: conn.runtime,
            accepted: false,
            error: this.options.rejectInputWith,
          }),
        );
      }
      return;
    }

    if (typeof msg.request_id === "string") {
      conn.socket.send(
        JSON.stringify({
          type: Inbound.inputAccepted,
          request_id: msg.request_id,
          runtime: conn.runtime,
          accepted: true,
          disposition: willQueue ? InputDispositions.queued : InputDispositions.started,
        }),
      );
    }

    if (this.options.approvalMode) {
      // The REAL shape (0.30.20 requestApprovalOverWS): announce the run so clients can attribute
      // it, then broadcast a top-level control_request to EVERY subscriber — not just the
      // initiator. The server settles the race itself, so every subscriber answering is expected.
      const runId = `local-run-${this.bump()}`;
      this.sendBroadcastAll(conn.runtime, Inbound.updateLoopStatus, {
        loop_status: {
          status: LoopStatuses.sendingApiRequest,
          active_run_ids: [runId],
          executing_tool_call_ids: [],
        },
      });
      const toolCallId = `toolu_${runId}`;
      for (const sub of this.subscribers(conn.runtime)) {
        sub.socket.send(
          JSON.stringify({
            type: Inbound.controlRequest,
            request_id: `perm-${toolCallId}`,
            request: {
              subtype: ControlRequestSubtypes.canUseTool,
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
      this.sendBroadcastAll(conn.runtime, Inbound.updateQueue, {
        queue: q.map((item, i) => ({
          id: `q-${i + 1}`,
          client_message_id: item.clientMessageId,
          kind: WireEnvelope.message,
          source: QueueSources.user,
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
      { id: `letta-msg-${1000 + this.runCounter}`, messageType: DeltaMessageTypes.assistant, text: "OK" },
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
      this.sendBroadcastAll(item.conn.runtime, Inbound.updateQueue, {
        queue: q.map((qi, i) => ({
          id: `q-${i + 1}`,
          client_message_id: qi.clientMessageId,
          kind: WireEnvelope.message,
          source: QueueSources.user,
        })),
        removed: [{ client_message_id: item.clientMessageId, disposition: QueueDispositions.dequeued }],
      });
    };

    const runTurn = (): void => {
      if (this.options.erroredTurn === "deltas") {
        this.broadcastErroredTurn(item.conn.runtime as ConnState["runtime"], runId);
        return;
      }
      if (this.options.erroredTurn === "turn-finished") {
        this.broadcastErrorFinishedTurn(item.conn.runtime as ConnState["runtime"], runId);
        return;
      }
      if (this.options.toolUse) {
        this.broadcastToolUsingTurn(
          item.conn.runtime as ConnState["runtime"],
          runId,
          `local-run-${this.bump()}`,
          messages,
        );
        return;
      }
      this.broadcastTurn(item.conn.runtime as ConnState["runtime"], runId, messages);
    };

    if (this.options.dequeueAfterRunStart) {
      runTurn();
      announceDequeue();
    } else {
      announceDequeue();
      runTurn();
    }
    setImmediate(() => this.drain(key));
  }

  /** Broadcast a full turn (own or FOREIGN) to every socket subscribed to the runtime. */
  broadcastTurn(
    runtime: ConnState["runtime"],
    runId: string,
    messages: TurnMessage[],
    stopReason = StopReasons.endTurn,
  ): void {
    if (!runtime) return;
    for (const conn of this.subscribers(runtime)) {
      this.sendBroadcast(conn, Inbound.updateLoopStatus, {
        loop_status: {
          status: LoopStatuses.sendingApiRequest,
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
          this.sendBroadcast(conn, Inbound.streamDelta, {
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
              type: WireEnvelope.message,
            },
          });
        }
      }
      // Every real turn ends with these two control deltas. `stop_reason` carries NO delta.id —
      // the frame that used to be rejected by the watermark guard on every single turn.
      this.sendBroadcast(conn, Inbound.streamDelta, {
        delta: {
          id: `${runId}-usage`,
          message_type: DeltaMessageTypes.usage,
          run_id: runId,
          seq_id: 900,
          type: WireEnvelope.message,
        },
      });
      this.sendBroadcast(conn, Inbound.streamDelta, {
        delta: {
          message_type: DeltaMessageTypes.stopReason,
          stop_reason: stopReason,
          run_id: runId,
          seq_id: 901,
          type: WireEnvelope.message,
        },
      });
      this.sendBroadcast(conn, Inbound.turnFinished, {
        turn_id: `batch-${runId}`,
        stop_reason: stopReason,
        run_id: runId,
      });
      this.sendBroadcast(conn, Inbound.updateLoopStatus, {
        loop_status: {
          status: LoopStatuses.waitingOnInput,
          active_run_ids: [],
          executing_tool_call_ids: [],
        },
      });
    }
  }

  /**
   * A TOOL-USING reply, in the shape captured live on 0.30.20.
   *
   * ```
   * turn_start    local-run-320  owns=true     ← the run our send starts
   * loop_status   EXECUTING_CLIENT_SIDE_TOOL
   * turn_start    local-run-321  owns=false    ← a NEW run carries the answer
   * loop_status   WAITING_ON_INPUT
   * turn_finished local-run-321  end_turn      ← only 321 ever finishes
   * ```
   *
   * `firstRunId` is deliberately ORPHANED: no `turn_finished` is ever emitted for it, on this
   * turn or any later one. Three consequences the single-run shape hid — a wait keyed on "our run
   * finished" never returns; the run is never released from ownership, so the idle reaper is the
   * only thing that stops attribution degrading permanently; and the reply arrives on a run no
   * claim can bind.
   */
  broadcastToolUsingTurn(
    runtime: ConnState["runtime"],
    firstRunId: string,
    continuationRunId: string,
    messages: TurnMessage[],
    stopReason = StopReasons.endTurn,
  ): void {
    if (!runtime) return;
    for (const conn of this.subscribers(runtime)) {
      const toolCallId = `toolu_${firstRunId}`;
      this.sendBroadcast(conn, Inbound.updateLoopStatus, {
        loop_status: {
          status: LoopStatuses.sendingApiRequest,
          active_run_ids: [firstRunId],
          executing_tool_call_ids: [],
        },
      });
      this.sendBroadcast(conn, Inbound.streamDelta, {
        delta: {
          id: `${firstRunId}-toolcall`,
          date: "2026-08-13T00:00:00.000Z",
          agent_id: runtime.agent_id,
          conversation_id: runtime.conversation_id,
          message_type: DeltaMessageTypes.toolCall,
          otid: `otid-${firstRunId}`,
          run_id: firstRunId,
          seq_id: 1,
          type: WireEnvelope.message,
        },
      });
      this.sendBroadcast(conn, Inbound.updateLoopStatus, {
        loop_status: {
          status: LoopStatuses.executingClientSideTool,
          active_run_ids: [firstRunId],
          executing_tool_call_ids: [toolCallId],
        },
      });
      // The continuation. Note there is NO turn_finished for firstRunId — not here, not later.
      this.sendBroadcast(conn, Inbound.updateLoopStatus, {
        loop_status: {
          status: LoopStatuses.sendingApiRequest,
          active_run_ids: [continuationRunId],
          executing_tool_call_ids: [],
        },
      });
      for (const m of messages) {
        for (const [i, chunk] of splitIntoChunks(m.text).entries()) {
          this.sendBroadcast(conn, Inbound.streamDelta, {
            delta: {
              id: `${m.id}-${i}`,
              date: "2026-08-13T00:00:00.000Z",
              agent_id: runtime.agent_id,
              conversation_id: runtime.conversation_id,
              message_type: m.messageType,
              otid: `otid-${m.id}`,
              content: chunk,
              run_id: continuationRunId,
              seq_id: i + 1,
              type: WireEnvelope.message,
            },
          });
        }
      }
      this.sendBroadcast(conn, Inbound.streamDelta, {
        delta: {
          message_type: DeltaMessageTypes.stopReason,
          stop_reason: stopReason,
          run_id: continuationRunId,
          seq_id: 901,
          type: WireEnvelope.message,
        },
      });
      // IDLE BEFORE FINISHED, as captured. The ordering is not cosmetic: it is why a one-shot
      // that waits for its own run's `turn_finished` hangs, and why the client terminates on the
      // runtime going idle instead.
      this.sendBroadcast(conn, Inbound.updateLoopStatus, {
        loop_status: {
          status: LoopStatuses.waitingOnInput,
          active_run_ids: [],
          executing_tool_call_ids: [],
        },
      });
      this.sendBroadcast(conn, Inbound.turnFinished, {
        turn_id: `batch-${continuationRunId}`,
        stop_reason: stopReason,
        run_id: continuationRunId,
      });
    }
  }

  /**
   * An ERRORED turn, in the shape captured live against an agent whose model 404s.
   *
   * ```
   * loop_status   SENDING_API_REQUEST
   * stream_delta  loop_error      ← machine-readable; carries NO delta.id
   * stream_delta  error_message   ← the human-readable body
   * loop_status   WAITING_ON_INPUT
   * (nothing else — turn_finished never arrives, on this turn or any later one)
   * ```
   *
   * The absent `turn_finished` is the whole point. `render.ts` shows a failure only via the stop
   * reason on that frame, so with no frame there is no failure notice; and both error deltas were
   * dropped by `renderDelta` for not being `assistant`/reasoning. The turn therefore rendered as
   * an empty SUCCESSFUL one and the process exited 0 — measured against the live server.
   *
   * `loop_error` deliberately carries no `delta.id`: content deltas must have one (it is the
   * catch-up watermark) but this is a control delta, and emitting it with an id would let a client
   * pass this fixture while still rejecting the real frame as drift.
   */
  broadcastErroredTurn(
    runtime: ConnState["runtime"],
    runId: string,
    errorText: string = this.options.errorText ?? DEFAULT_ERROR_TEXT,
  ): void {
    if (!runtime) return;
    for (const conn of this.subscribers(runtime)) {
      this.sendBroadcast(conn, Inbound.updateLoopStatus, {
        loop_status: {
          status: LoopStatuses.sendingApiRequest,
          active_run_ids: [runId],
          executing_tool_call_ids: [],
        },
      });
      this.sendBroadcast(conn, Inbound.streamDelta, {
        delta: {
          message_type: DeltaMessageTypes.loopError,
          run_id: runId,
          seq_id: 1,
          type: WireEnvelope.message,
          error: errorText,
        },
      });
      this.sendBroadcast(conn, Inbound.streamDelta, {
        delta: {
          id: `${runId}-error`,
          date: "2026-08-13T00:00:00.000Z",
          agent_id: runtime.agent_id,
          conversation_id: runtime.conversation_id,
          message_type: DeltaMessageTypes.errorMessage,
          otid: `otid-${runId}-error`,
          content: errorText,
          run_id: runId,
          seq_id: 2,
          type: WireEnvelope.message,
        },
      });
      // Idle, and then nothing. No turn_finished is emitted for this run, ever.
      this.sendBroadcast(conn, Inbound.updateLoopStatus, {
        loop_status: {
          status: LoopStatuses.waitingOnInput,
          active_run_ids: [],
          executing_tool_call_ids: [],
        },
      });
    }
  }

  /**
   * The OTHER errored shape: the turn ends on `turn_finished{stop_reason:error}` and the runtime
   * never reports idle afterwards.
   *
   * A one-shot keyed only on the shared `WAITING_ON_INPUT` idle has nothing to wake it here, so it
   * waits out the full `--timeout` (180s by default; measured at 20.32s against `--timeout 20`)
   * and then reports a timeout — blaming a server that answered immediately.
   */
  broadcastErrorFinishedTurn(
    runtime: ConnState["runtime"],
    runId: string,
    errorText: string = this.options.errorText ?? DEFAULT_ERROR_TEXT,
  ): void {
    if (!runtime) return;
    for (const conn of this.subscribers(runtime)) {
      this.sendBroadcast(conn, Inbound.updateLoopStatus, {
        loop_status: {
          status: LoopStatuses.sendingApiRequest,
          active_run_ids: [runId],
          executing_tool_call_ids: [],
        },
      });
      this.sendBroadcast(conn, Inbound.streamDelta, {
        delta: {
          id: `${runId}-error`,
          date: "2026-08-13T00:00:00.000Z",
          agent_id: runtime.agent_id,
          conversation_id: runtime.conversation_id,
          message_type: DeltaMessageTypes.errorMessage,
          otid: `otid-${runId}-error`,
          content: errorText,
          run_id: runId,
          seq_id: 1,
          type: WireEnvelope.message,
        },
      });
      this.sendBroadcast(conn, Inbound.turnFinished, {
        turn_id: `batch-${runId}`,
        stop_reason: StopReasons.error,
        run_id: runId,
      });
      // NOTE: no update_loop_status follows. That absence is the fixture.
    }
  }

  /** Public helper for tests: inject an errored turn addressed to a runtime. */
  injectErroredTurn(
    runtime: { agent_id: string; conversation_id: string },
    runId: string,
    errorText?: string,
  ): void {
    this.broadcastErroredTurn(runtime, runId, errorText);
  }

  /** Public helper for tests: inject a turn that ends on `error` with no following idle. */
  injectErrorFinishedTurn(
    runtime: { agent_id: string; conversation_id: string },
    runId: string,
    errorText?: string,
  ): void {
    this.broadcastErrorFinishedTurn(runtime, runId, errorText);
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
        type: Inbound.conversationListResponse,
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
        type: Inbound.conversationCreateResponse,
        request_id: msg.request_id,
        success: true,
        conversation: { id: `local-conv-new-${this.bump()}`, agent_id: body.agent_id },
      }),
    );
  }

  private handleMessagesList(conn: ConnState, msg: Record<string, unknown>): void {
    conn.socket.send(
      JSON.stringify({
        type: Inbound.conversationMessagesListResponse,
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
