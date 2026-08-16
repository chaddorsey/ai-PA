/**
 * index.ts — ContinuityCore: the reusable client-core both M1 clients import.
 *
 * One raw-WS ordered connection to the sole-owner App Server for a single `{agent, conversation}`:
 *   • live render of own AND foreign turns off one `event_seq`-ordered stream (stream.ts)
 *   • `conversation_*` management RPCs (for later rail reuse)
 *   • approvals answered UNCONDITIONALLY and always denied (M1) — the server broadcasts each
 *     request to every subscriber and settles the race itself, so the only dangerous outcome is
 *     nobody answering. Do NOT gate this on run ownership (see routeFrame).
 *   • bounded reconnect + `conversation_messages_list` catch-up with message-id dedup (catchup.ts)
 *
 * No SDK dep, no second observer connection, no arbitration/flock — the server queue-serializes
 * concurrent sends (Unit 1), so the core just submits and renders.
 */

import { type CatchupSnapshot, LiveDedup, snapshotFromResponse } from "./catchup.js";
import {
  type ConnectionListener,
  type ConnectionState,
  ConnectionStateMachine,
} from "./connection.js";
import { evictOldest } from "./evict.js";
import { fanOut } from "./fanout.js";
import { type Attribution, type OwnershipSnapshot, RunOwnership } from "./ownership.js";
import { type ContinuityPointer, readPointer } from "./pointer.js";
import {
  type ControlRequestFrame,
  type ConversationCreateResponseFrame,
  type ConversationListResponseFrame,
  type ConversationSummary,
  LoopStatuses,
  type MessagesListResponseFrame,
  Outbound,
  ProtocolError,
  type Runtime,
  type ServerFrame,
  type VersionPolicy,
  buildApprovalDeny,
  buildConversationCreate,
  buildConversationList,
  buildConversationMessagesList,
  buildInput,
  controlRequestToolName,
  frameRunId,
  isControlRequest,
  isInputAccepted,
  isLoopStatus,
  isQueue,
  isStreamDelta,
  isTurnFinished,
  newClientNonce,
  nextRequestId,
  queueRemovals,
  queuedClientMessageIds,
} from "./protocol.js";
import { type RenderListener, StreamAssembler } from "./stream.js";
import { assertLoopbackUrl } from "./trust.js";
import { type ContinuityTransport, WsConnection, type WsConnectionOptions } from "./ws.js";

const WS_URL = "ws://127.0.0.1:4577/ws";

/**
 * How often to sweep for claims and owned runs the stream stopped resolving, and how much
 * observed inactivity counts as stuck.
 *
 * RunOwnership.reapIdle existed, was documented as the bound on that state, was covered by unit
 * tests — and was called by nothing. So a single lost `input_accepted` or `turn_finished` (the
 * ordinary watchdog-restart path) stranded a claim for the life of the process, which pinned
 * hasOutstanding() true, which permanently disabled the positivelyForeign branch, after which
 * EVERY peer turn attributed as "unknown" and a solo user's own turns rendered as `peer ›`.
 *
 * The idle budget is generous on purpose: turns here run 51s-600s, so anything short enough to
 * bound a stuck claim quickly is short enough to reap a live one.
 */
/** Far beyond any redelivery window; the set is per-connection, so this is a backstop. */
const MAX_ANSWERED_APPROVALS = 512;

const REAP_INTERVAL_MS = 60_000;
const REAP_IDLE_MS = 900_000;

/**
 * The first field of `ConversationSummary` that `entry` does not actually supply, or null.
 *
 * Returning the field NAME rather than a boolean is the whole point: every caller of this needs to
 * tell the operator which part of the contract the server broke, and a `false` cannot.
 */
function missingSummaryField(entry: unknown): string | null {
  const c = entry as Record<string, unknown> | null | undefined;
  if (c === null || typeof c !== "object") return "id";
  for (const field of ["id", "agent_id", "created_at", "updated_at"] as const) {
    if (typeof c[field] !== "string") return field;
  }
  if (typeof c.archived !== "boolean") return "archived";
  // Nullable by contract, so `null` is a valid value rather than a missing one.
  if (c.archived_at !== null && typeof c.archived_at !== "string") return "archived_at";
  return null;
}

/**
 * The reason attached to every M1 auto-deny. The server requires a string message on a deny, and
 * this one is written for the human who finds it in a transcript, not for a log parser.
 */
const APPROVAL_DENY_MESSAGE =
  "Auto-denied: this conversation is shared across surfaces and has no interactive approval UI yet (milestone 1).";

/**
 * A condition the session cannot recover from.
 *
 * Distinct from the ordinary `onError` channel because consumers must be able to tell "something
 * went wrong" from "stop waiting". Both used to arrive as a bare Error on the same channel, whose
 * only consumer printed prose — so a client that had permanently lost the App Server still exited
 * 0, and a library consumer could only tell dead from closed-on-purpose by string-matching.
 */
export class ContinuityFatalError extends Error {
  /**
   * Which send this is about, when the cause is one. A bridge fanning out to N consumers has to
   * fail the one that asked — telling all of them, or none, are both wrong — and neither the
   * message text nor the reason code identifies a submitter.
   */
  readonly requestId?: string;
  readonly origin?: string;

  constructor(
    message: string,
    readonly reason: "reconnect-exhausted" | "input-rejected",
    context: { requestId?: string; origin?: string } = {},
  ) {
    super(message);
    this.name = "ContinuityFatalError";
    this.requestId = context.requestId;
    this.origin = context.origin;
  }
}

export interface SendOptions {
  /**
   * Who is submitting this turn. Omit for a single-surface client; supply a stable per-consumer
   * value (a browser session id, say) when one core serves several.
   */
  origin?: string;
}

export interface SendHandle {
  requestId: string;
  clientMessageId: string;
  origin?: string;
}

export interface ContinuityCoreConfig {
  /** Path to the durable `{agent, conversation}` pointer file (pointer.ts). */
  /**
   * Where to read the {agent, conversation} from. Optional now: pass `pointer` instead when the
   * caller already knows its target. Requiring a FILE meant a bridge serving a conversation per
   * request had to materialise a temp file and delete it, on a code path with no other disk
   * dependency — and Unit 8's seed step, which mints the conversation via conversationCreate,
   * had nowhere to put the result.
   */
  pointerPath?: string;
  /** A resolved target, used in preference to `pointerPath`. */
  pointer?: ContinuityPointer;
  url?: string;
  pinnedVersion?: string | readonly string[];
  versionPolicy?: VersionPolicy;
  maxReconnectAttempts?: number;
  reconnectDelayMs?: number;
  /**
   * How long a connection must survive before it restores the reconnect budget. Defaults to the
   * longest backoff delay. See connection.ts — a server that accepts and then dies must not be
   * able to rearm the bound that exists for exactly that shape.
   */
  connectionStabilityMs?: number;
  openTimeoutMs?: number;
  helloTimeoutMs?: number;
  rpcTimeoutMs?: number;
  serverInfoTimeoutMs?: number;
  /** Flat reconnect delay override (tests). Omit for exponential backoff with jitter. */
  jitter?: () => number;
  /** Override the per-instance correlation nonce (tests, or a bridge fanning out to N browsers). */
  clientNonce?: string;
  onWarn?: (msg: string) => void;
  /**
   * Idle-sweep tuning. Defaults are sized for real turns (51s-600s); tests override them.
   */
  reapIntervalMs?: number;
  reapIdleMs?: number;
  /**
   * Opt OUT of the loopback trust boundary. Off by default, and deliberately awkward to reach:
   * the App Server has no client auth, so a non-loopback peer sees everything typed and the whole
   * conversation history. See trust.ts.
   */
  allowRemote?: boolean;
  /**
   * Transport factory. Defaults to `new WsConnection(options)`.
   *
   * Two reasons it is a seam rather than a hard-wired `new`. M1 Unit 6's browser client cannot use
   * the `ws` package and needs to supply its own implementation of the same surface. And a write
   * fault — `send` throwing because the socket is no longer OPEN — is the one condition a real
   * loopback socket cannot be made to produce on cue: the frame that triggers the send and the
   * send itself happen in the same tick, so no server-side action can separate them. The approval
   * path's send-then-record ordering guards exactly that condition, and without a way to inject it
   * the ordering is unassertable — which is how the pre-fix "nobody answers" hang came back with a
   * green suite.
   *
   * The return type is the structural `ContinuityTransport`, NOT the concrete `WsConnection`.
   * `WsConnection` has private members, which make its type nominal, so typing this to the class
   * meant only that class or a subclass could satisfy it — and a subclass imports `ws`. The first
   * of the two reasons above did not actually work; a browser transport failed to compile against
   * this seam (TS2322). Anything a browser can implement now satisfies it.
   */
  createConnection?: (options: WsConnectionOptions) => ContinuityTransport;
}

/**
 * An approval request seen on the conversation, and what this client did about it.
 *
 * `toolName` is server-derived and therefore untrusted: it must be sanitized before display.
 * The tool ARGUMENTS are deliberately not exposed — they routinely carry file contents or
 * credentials the agent is passing to a tool, and surfacing them would put that in terminal
 * scrollback and any session capture.
 */
export interface ApprovalEvent {
  requestId: string;
  toolName: string | undefined;
  /** "denied" = the M1 auto-deny backstop; "pending" = a controller-arbitrated approval awaiting the operator. */
  outcome: "denied" | "pending";
}

export class ContinuityCore {
  private readonly config: ContinuityCoreConfig;
  private readonly connectionState: ConnectionStateMachine;
  private readonly assembler = new StreamAssembler();
  private pointer: ContinuityPointer | null = null;
  private runtime: Runtime | null = null;
  private ws: ContinuityTransport | null = null;
  private liveDedup: LiveDedup | null = null;
  /** Which runs on the shared conversation are ours — drives ORIGIN LABELLING, not approvals. */
  private readonly ownership = new RunOwnership();
  /**
   * Makes this instance's correlation ids distinct from any other client PROCESS on the same
   * conversation. See protocol.newClientNonce for why a module-global counter is not enough.
   */
  private readonly clientNonce: string;
  /**
   * control_request ids already answered ON THIS CONNECTION. Prevents a redelivered frame from
   * emitting a second (harmless but noisy) response.
   *
   * CLEARED ON RECONNECT, deliberately. An entry means "we put a deny on the wire", which is not
   * the same as "the server received it" — a socket that dies between the two leaves the approval
   * unanswered while this set claims otherwise. Since the server settles duplicates itself,
   * re-answering after a seam is strictly the safe direction and silence is not.
   */
  private answeredApprovals = new Set<string>();
  /**
   * request_ids of approval responses WE sent, so their acks can be told apart from acks for the
   * user's own turns. The server answers the loser of a settled approval race with
   * `accepted:false, "Approval request is no longer pending"` — expected, not an error.
   */
  private sentApprovalResponses = new Set<string>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reapTimer: ReturnType<typeof setInterval> | null = null;
  private stopped = false;
  private readonly errorListeners = new Set<(err: Error) => void>();
  private readonly fatalListeners = new Set<(err: ContinuityFatalError) => void>();
  private readonly approvalListeners = new Set<(e: ApprovalEvent) => void>();

  constructor(config: ContinuityCoreConfig) {
    this.config = config;
    this.clientNonce = config.clientNonce ?? newClientNonce();
    this.connectionState = new ConnectionStateMachine({
      ...(config.maxReconnectAttempts !== undefined
        ? { maxReconnectAttempts: config.maxReconnectAttempts }
        : {}),
      // `reconnectDelayMs` keeps working as a FLAT override so the existing integration tests can
      // still force a 15-20ms schedule; without it they would each wait out a real backoff.
      ...(config.reconnectDelayMs !== undefined
        ? { baseDelayMs: config.reconnectDelayMs, maxDelayMs: config.reconnectDelayMs }
        : {}),
      ...(config.jitter !== undefined ? { jitter: config.jitter } : {}),
      ...(config.connectionStabilityMs !== undefined
        ? { stabilityMs: config.connectionStabilityMs }
        : {}),
    });
  }

  onRender(cb: RenderListener): () => void {
    return this.assembler.onRender(cb);
  }
  onConnectionState(cb: ConnectionListener): () => void {
    return this.connectionState.onChange(cb);
  }
  onError(cb: (err: Error) => void): () => void {
    this.errorListeners.add(cb);
    return () => this.errorListeners.delete(cb);
  }

  /** Subscribe to session-fatal conditions. Fires at most once per cause. */
  onFatal(cb: (err: ContinuityFatalError) => void): () => void {
    this.fatalListeners.add(cb);
    return () => this.fatalListeners.delete(cb);
  }
  /**
   * Approval activity on this conversation. Surfaced even though M1 answers automatically: an
   * auto-deny the user never sees is indistinguishable from the agent choosing not to use a tool,
   * which makes the whole policy unfalsifiable in practice — and an approval is a
   * security-relevant event regardless of who answered it.
   */
  onApproval(cb: (e: ApprovalEvent) => void): () => void {
    this.approvalListeners.add(cb);
    return () => this.approvalListeners.delete(cb);
  }

  get state(): ConnectionState {
    return this.connectionState.current;
  }
  getRuntime(): Runtime {
    if (!this.runtime) throw new Error("ContinuityCore not started");
    return this.runtime;
  }

  /** Resolve the pointer, connect, and begin streaming. */
  async start(): Promise<void> {
    this.stopped = false;
    // Everything below is PER-CONNECTION and must not survive into a new session.
    //
    // `event_seq` restarts at 1 on every connection, and the assembler drops anything at or below
    // its watermark. Resetting it only in reconnect() meant a core that was stopped and started
    // again carried the previous session's high-water mark into a stream that begins at 1 — so it
    // dropped every frame of the new session while reporting itself connected and accepting
    // input. A total blackout, and a silent one.
    this.assembler.reset();
    this.liveDedup = null;
    this.answeredApprovals = new Set();
    this.sentApprovalResponses = new Set();
    this.pointer = await this.resolvePointer();
    this.runtime = {
      agent_id: this.pointer.agentId,
      conversation_id: this.pointer.conversationId,
    };
    await this.openConnection();
    this.startReaper();
  }

  /**
   * Submit a user turn. Registers a correlation claim so the resulting run can be identified as
   * ours (see ownership.ts), which is what lets the transcript label it `you`/`agent` rather than
   * `peer`. It has no bearing on approvals — those are answered unconditionally.
   */
  send(text: string, opts: SendOptions = {}): SendHandle {
    if (!this.ws || !this.runtime) throw new Error("ContinuityCore not started");
    // Vary the nonce per send when the caller supplies an origin. protocol.nextRequestId has
    // always taken `nonce` as a PARAMETER for exactly this reason — "the web client is ONE core
    // fanning out to N browsers, so it must be able to vary the nonce per send" — but the facade
    // captured a single construction-time value and offered no way to. A bridge therefore could
    // not tell which browser a run belonged to: every run the core started was equally "ours".
    const nonce = opts.origin ? `${this.clientNonce}-${opts.origin}` : this.clientNonce;
    const requestId = nextRequestId("input", nonce);
    const clientMessageId = nextRequestId("cm", nonce);
    // Register the claim only once the frame is actually on the wire. Registering first leaves a
    // claim for a send that threw, and nothing can ever resolve it — hasOutstanding() then stays
    // true for the process lifetime, which pins every downstream bound that depends on it.
    this.ownership.beginSend(requestId, clientMessageId, opts.origin);
    try {
      this.ws.send(buildInput(this.runtime, text, { requestId, clientMessageId }));
    } catch (err) {
      this.ownership.abandon(requestId);
      throw err;
    }
    return { requestId, clientMessageId, origin: opts.origin };
  }

  /** Current run-ownership state (owned run ids, unbound claims, degraded flag). */
  ownershipSnapshot(): OwnershipSnapshot {
    return this.ownership.snapshot();
  }

  /**
   * Did THIS client start `runId`? Surfaces run attribution so a UI can distinguish its own
   * turns from a peer's. Note ownership is RELEASED at turn_finished, so ask while the turn
   * is live (e.g. at turn_start) and remember the answer.
   */
  /**
   * Whether any message queued in this `update_queue` frame is one of OURS.
   *
   * `update_queue` is broadcast to every subscriber, so depth alone cannot tell the surface that
   * is waiting from the surface whose turn is currently running.
   */
  queueHasMine(frame: ServerFrame, origin?: string): boolean {
    if (!isQueue(frame)) return false;
    return this.ownership.ownsAnyMessage(queuedClientMessageIds(frame), origin);
  }

  /**
   * The origin that submitted `runId`, if we own it. A bridge uses this to route a run's output
   * back to the consumer that asked for it, instead of broadcasting every run to all of them.
   */
  runOrigin(runId: string | undefined): string | undefined {
    return runId === undefined ? undefined : this.ownership.originOf(runId);
  }

  ownsRun(runId: string | undefined): boolean {
    return this.ownership.attribute(runId) === "mine";
  }

  /** Full classification: ours, positively a peer's, or not attributable. */
  attributeRun(runId: string | undefined): Attribution {
    return this.ownership.attribute(runId);
  }

  /** List conversations for the pointer's agent (rail primitive). */
  async conversationList(): Promise<ConversationSummary[]> {
    const agentId = this.getRuntime().agent_id;
    const ws = this.requireWs();
    const resp = await ws.request<ConversationListResponseFrame>(
      (rid) => buildConversationList(rid, agentId),
      Outbound.conversationList,
    );
    // The validator checks that `conversations` is an ARRAY; it says nothing about the entries.
    // Returning them under a `ConversationSummary[]` annotation is a claim the wire has not made,
    // and the consumer prints `c.id` — so a renamed field reached the user as `undefined` rather
    // than as the drift signal this layer exists to raise.
    //
    // The predicate checks EVERY field it asserts. It used to check `id` alone and then claim all
    // six, which is strictly worse than a bare cast: a cast is visibly an assumption, whereas
    // `c is ConversationSummary` reads as validation. Deleting the other five fields from every
    // entry left the suite green while the annotation went on promising them.
    return resp.conversations.filter((c): c is ConversationSummary => {
      const missing = missingSummaryField(c);
      if (missing !== null) {
        // Name the FIELD, not just the entry. If this check is ever stricter than the server, the
        // warning says which field to look at — otherwise an over-strict predicate silently drops
        // real conversations and presents as "the agent has none".
        this.config.onWarn?.(
          `conversation_list returned an entry with no valid \`${missing}\` — skipped`,
        );
        return false;
      }
      return true;
    });
  }

  /** Create a conversation for the pointer's agent (rail primitive; also the Unit 8 seed op). */
  async conversationCreate(title?: string): Promise<{ id: string } | undefined> {
    const agentId = this.getRuntime().agent_id;
    const ws = this.requireWs();
    const resp = await ws.request<ConversationCreateResponseFrame>(
      (rid) => buildConversationCreate(rid, agentId, title),
      Outbound.conversationCreate,
    );
    const id = (resp.conversation as { id?: unknown } | undefined)?.id;
    if (typeof id !== "string" || id === "") {
      // Unit 8's seed step writes this id into the pointer every surface then attaches to. A cast
      // that let `undefined` through would have produced a pointer nothing can open, reported as
      // success.
      throw new ProtocolError("conversation_create returned no usable `conversation.id`");
    }
    return { id };
  }

  /** Close the connection and cancel any pending reconnect. Idempotent. */
  stop(): void {
    this.stopped = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.reapTimer) {
      clearInterval(this.reapTimer);
      this.reapTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.connectionState.disconnected();
  }

  // ── internals ────────────────────────────────────────────────────────────

  private requireWs(): ContinuityTransport {
    if (!this.ws) throw new Error("ContinuityCore not connected");
    return this.ws;
  }

  /**
   * Build a wired WsConnection. Single construction point so the initial connect and the
   * reconnect path can never drift in their options (notably the version-gate settings).
   */
  private newConnection(): ContinuityTransport {
    if (!this.runtime) throw new Error("runtime not resolved");
    const url = this.config.url ?? WS_URL;
    // Enforce the trust boundary HERE, before the factory — not only inside the object the factory
    // is allowed to replace.
    //
    // This server has NO client authentication: loopback is the entire access control story, so it
    // is the one rule that must not be delegated. It was checked only in `WsConnection`, which is
    // precisely the class `createConnection` exists to substitute — so any consumer passing a
    // transport bypassed the boundary completely, and the Unit 6 browser transport is exactly such
    // a consumer. Checking in both places is deliberate: the core owns the policy, and
    // `WsConnection` keeps its own check so it stays safe when used directly.
    assertLoopbackUrl(url, this.config.allowRemote ?? false);
    const create =
      this.config.createConnection ?? ((o: WsConnectionOptions) => new WsConnection(o));
    const ws = create({
      url,
      runtime: this.runtime,
      pinnedVersion: this.config.pinnedVersion,
      versionPolicy: this.config.versionPolicy,
      openTimeoutMs: this.config.openTimeoutMs,
      helloTimeoutMs: this.config.helloTimeoutMs,
      rpcTimeoutMs: this.config.rpcTimeoutMs,
      serverInfoTimeoutMs: this.config.serverInfoTimeoutMs,
      clientNonce: this.clientNonce,
      allowRemote: this.config.allowRemote,
      onWarn: this.config.onWarn,
    });
    ws.onFrame((f) => this.routeFrame(f));
    ws.onError((e) => this.emitError(e));
    // `close` alone carries its connection. A politely-closed socket can emit it long after it
    // was replaced (the ws package waits for the handshake, up to 30s), and the event says
    // nothing about the connection that is CURRENT — which is what the identity-free version
    // consulted, so it saw a healthy connection, decided it had dropped, and scheduled a
    // reconnect that replaced it WITHOUT closing it.
    //
    // Frames and errors need no such guard: close() detaches those listeners, so a connection we
    // have finished with stops delivering to anyone. Two guards for one hazard means neither can
    // be held honest by a test — reverting either leaves the other covering for it.
    ws.onClose(() => this.handleClose(ws));
    return ws;
  }

  private async resolvePointer(): Promise<ContinuityPointer> {
    if (this.config.pointer) return this.config.pointer;
    if (this.config.pointerPath) return readPointer(this.config.pointerPath);
    throw new Error(
      "ContinuityCore needs a target: pass `pointer` (an {agentId, conversationId}) or `pointerPath`",
    );
  }

  /** Begin the idle sweep. Idempotent; cleared in stop(). */
  private startReaper(): void {
    if (this.reapTimer) return;
    const idleMs = this.config.reapIdleMs ?? REAP_IDLE_MS;
    this.reapTimer = setInterval(() => {
      const reaped = this.ownership.reapIdle(idleMs, Date.now());
      if (reaped.claims || reaped.runs) {
        this.config.onWarn?.(
          `reaped ${reaped.claims} stuck claim(s) and ${reaped.runs} unfinished run(s) after ${idleMs / 1000}s of stream inactivity — attribution has been reset`,
        );
      }
    }, this.config.reapIntervalMs ?? REAP_INTERVAL_MS);
    this.reapTimer.unref?.();
  }

  private async openConnection(): Promise<void> {
    this.connectionState.connecting();
    // Close the incumbent BEFORE replacing it. `start()` on a core that already holds a live
    // socket simply overwrote the reference, and the old socket was then orphaned: still open,
    // still wired to this core's handlers, still receiving broadcasts for a session nobody holds a
    // handle to. On a server whose entire premise is SOLE ownership of the backend, quietly
    // keeping a second wired socket per restart is the one thing a client here must not do.
    //
    // `close()` marks the connection closed-by-us, so the handleClose identity guard ignores it
    // and no reconnect loop is started for the connection we are deliberately retiring.
    if (this.ws) {
      const previous = this.ws;
      this.ws = null;
      previous.close();
    }
    const ws = this.newConnection();
    this.ws = ws;
    try {
      await ws.connect();
    } catch (err) {
      // connect() cleans up only on the open-timeout path; a version refusal or a hello timeout
      // rejects with the socket still OPEN and its listeners attached. Left alone, that socket's
      // eventual close runs handleClose for a session the caller has already given up on, and
      // starts a full reconnect loop for it. The terminal happens to call stop() here; the core
      // must not depend on every consumer remembering to.
      ws.close();
      this.ws = null;
      // A socket that dies DURING connect() runs handleClose before connect() rejects, so a
      // bounded reconnect is already queued by the time we get here. Left alone, start() reports
      // failure to its caller while the core quietly keeps dialling — a session nobody holds a
      // handle to, reconnecting on its own.
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
      this.connectionState.disconnected();
      throw err;
    }
    this.connectionState.connected();
  }

  private routeFrame(frame: ServerFrame): void {
    // Correlation bookkeeping first — these frames decide which runs are ours (ownership.ts).
    if (isInputAccepted(frame)) {
      // An ack for an approval response we sent is NOT an ack for a user turn. On a shared
      // conversation the server settles each approval race and answers the loser
      // `accepted:false, "Approval request is no longer pending"` — the expected outcome of
      // everyone answering, which is the policy. Reporting it through emitError put a red
      // "input rejected by the server" on N-1 surfaces per approval, indistinguishable from a
      // real rejection of the user's own message.
      if (this.sentApprovalResponses.delete(frame.request_id)) {
        if (!frame.accepted) {
          this.config.onWarn?.(
            `approval settled by another surface: ${frame.error ?? "no longer pending"}`,
          );
        }
        return;
      }
      // Read the origin BEFORE applying the ack: a rejection drops the claim, and with it the
      // only record of who submitted the turn being rejected.
      const origin = this.ownership.originOfRequest(frame.request_id);
      this.ownership.onInputAccepted(frame.request_id, frame.accepted, frame.disposition);
      if (!frame.accepted) {
        this.emitFatal(
          new ContinuityFatalError(
            `input rejected by the server: ${frame.error ?? "unknown"}`,
            "input-rejected",
            { requestId: frame.request_id, origin },
          ),
        );
      }
      return; // control-channel ack: never rendered
    }
    if (isQueue(frame)) {
      this.ownership.onQueueRemovals(queueRemovals(frame), (msg) =>
        this.config.onWarn?.(`queue anomaly: ${msg}`),
      );
      // fall through: the assembler may surface a "queued…" indicator
    }

    // Approval: answer any request we have not already answered, and always DENY (M1).
    //
    // This deliberately does NOT gate on run ownership. The server broadcasts each approval to
    // every subscribed connection and settles the race itself (`settled` guard in
    // requestApprovalOverWS; the loser is answered "Approval request is no longer pending"), so a
    // duplicate response is harmless and the ONLY dangerous outcome is nobody answering. Gating on
    // attribution could produce exactly that — and attribution is inferred from stream position,
    // so it is the less trustworthy of the two.
    //
    // The local at-most-once check is not for the server's benefit: it stops a redelivered frame
    // after a reconnect from emitting a redundant response that would log as an anomaly.
    if (isControlRequest(frame)) {
      const id = frame.request_id;
      if (!this.answeredApprovals.has(id) && this.ws && this.runtime) {
        const responseId = nextRequestId("appr", this.clientNonce);
        // Send FIRST, record second. Recording an intent as if it were a delivered answer is how
        // an approval goes unanswered: `send` throws when the socket is not OPEN, and a watchdog
        // restart lands exactly there. With the id already marked, the server's redelivery on the
        // new connection is suppressed and NOBODY answers — the one outcome that hangs every
        // surface. Same ordering rule as send() below, where the cost of getting it wrong is only
        // a mislabelled turn.
        try {
          this.sentApprovalResponses.add(responseId);
          evictOldest(this.sentApprovalResponses, MAX_ANSWERED_APPROVALS);
          this.ws.send(buildApprovalDeny(responseId, this.runtime, id, APPROVAL_DENY_MESSAGE));
        } catch (err) {
          this.sentApprovalResponses.delete(responseId);
          // Leave `id` unanswered so a redelivery after reconnect is answered rather than skipped.
          this.emitError(err instanceof Error ? err : new Error(String(err)));
          return;
        }
        this.answeredApprovals.add(id);
        evictOldest(this.answeredApprovals, MAX_ANSWERED_APPROVALS);
        this.emitApproval(frame, "denied");
      }
      return;
    }

    // Reconnect replay↔live dedup on message id (never on event_seq).
    // Control deltas carry no id and so cannot be deduped — they are not message content.
    if (
      this.liveDedup &&
      isStreamDelta(frame) &&
      frame.delta.id !== undefined &&
      !this.liveDedup.admit(frame.delta.id)
    ) {
      return; // snapshot replay of an already-rendered message — drop
    }

    // Attribute the run this frame belongs to, then release it when it finishes.
    const runId = frameRunId(frame);
    if (runId !== undefined) this.ownership.onRunObserved(runId);
    if (isTurnFinished(frame) && typeof frame.run_id === "string") {
      this.ownership.onTurnFinished(frame.run_id, frame.stop_reason);
    }
    // The runtime stating that nothing is executing. It bounds continuation inheritance and
    // releases the orphaned first run of a tool-using turn, which never emits a turn_finished of
    // its own — see RunOwnership.onIdle.
    if (isLoopStatus(frame) && frame.loop_status.status === LoopStatuses.waitingOnInput) {
      this.ownership.onIdle();
    }
    this.assembler.ingest(frame);
  }

  /**
   * `source` is load-bearing. The guard used to read `this.ws`, i.e. whatever connection is
   * CURRENT — but a superseded socket can emit `close` long after it was replaced (the ws package
   * waits for a close handshake, up to 30s). The guard then consulted the healthy connection, saw
   * it was not closed by us, and scheduled a reconnect against a live socket. That reconnect
   * replaced `this.ws` WITHOUT closing it, leaving two sockets wired to routeFrame and every
   * broadcast rendered twice on two independent event_seq sequences.
   */
  private handleClose(source: ContinuityTransport): void {
    if (this.stopped || source !== this.ws || source.isClosedByUs) return;
    this.scheduleReconnect();
  }

  /** Schedule one bounded reconnect. Idempotent: an already-pending timer is not doubled. */
  private scheduleReconnect(): void {
    if (this.stopped) return;
    if (this.reconnectTimer) return; // a reconnect is already queued — never double-schedule
    const mayRetry = this.connectionState.dropped();
    if (!mayRetry) {
      // Exhaustion is a dead end the user must be told about: the process stays alive and the
      // prompt still accepts input, so a bare state change reads as "quiet", not "gave up".
      this.emitFatal(
        new ContinuityFatalError(
          "reconnect budget exhausted — the App Server did not come back. Restart this client once it is up.",
          "reconnect-exhausted",
        ),
      );
      return;
    }
    const delay = this.connectionState.nextDelayMs();
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.reconnect();
    }, delay);
  }

  private async reconnect(): Promise<void> {
    if (this.stopped || !this.runtime) return;
    // Held outside the try so the catch can close THIS attempt rather than `this.ws`, which by
    // then may already be a newer connection that a concurrent attempt installed — closing it
    // would take down the recovery in progress and start another.
    let attempt: ContinuityTransport | null = null;
    try {
      const ws = this.newConnection();
      attempt = ws;
      // New connection ⇒ event_seq restarts; forget the per-connection ordering watermark.
      this.assembler.reset();
      // The gap may have hidden an ack, a dequeue, or a turn_finished — so run attribution is no
      // longer trustworthy and armed claims are demoted. Approvals are unaffected: they do not
      // consult attribution.
      this.ownership.onReconnect();
      // An entry in `answeredApprovals` means "we put a deny on the wire", which is not the same
      // as "the server received it": a socket that died between the two leaves the approval
      // unanswered while this set claims otherwise, and the server's redelivery on the new
      // connection would then be skipped. Nobody answers, and the turn parks on every surface.
      // Since the server settles duplicates itself, re-answering after a seam is free.
      this.answeredApprovals = new Set();
      // `sentApprovalResponses` is deliberately NOT cleared here. Its entries are ids we minted,
      // unique for the life of the process, so a stale one can never match a later ack — clearing
      // it would only bound memory, and it is bounded where it is written instead. A line whose
      // removal no test could ever detect is not a fix.
      // Drop the previous snapshot's watermark NOW, not when the next one arrives. Between
      // connect() and fetchSnapshot() resolving — up to rpcTimeoutMs — live frames were being
      // filtered against the PREVIOUS reconnect's id set. Harmless only while the live and
      // snapshot id namespaces stay disjoint, which is exactly what M1 Unit 7 will change.
      this.liveDedup = null;
      // The outgoing connection is not closed here. Every path that reaches a reconnect has
      // already closed it — handleClose only fires for a socket that went away, and the catch
      // below closes the attempt it failed on. A second `close()` here looked like belt and
      // braces but could not be reached by any sequence, so no test could hold it honest; it was
      // removed rather than kept as an unfalsifiable guard. What stops a closed connection
      // talking to a consumer that has moved on is WsConnection.close() detaching its listeners,
      // which IS reachable and IS asserted (test/ws.listeners.test.ts).
      this.ws = ws;
      await ws.connect();
      // Snapshot BEFORE resuming live so the message-id watermark bridges the seam.
      const snapshot = await this.fetchSnapshot(ws);
      // Re-check identity after BOTH awaits. connected() does not merely report a state — it also
      // resets the attempt counter. Calling it for a connection that has since died (or after
      // stop()) rearms the reconnect budget every cycle, so backoff never grows and the cap is
      // never reached: a crash-looping App Server gets hammered by every attached surface while
      // the user is shown "connected" and types into a dead socket.
      if (this.stopped || this.ws !== ws || ws.isClosedByUs) {
        ws.close();
        return;
      }
      this.liveDedup = snapshot ? new LiveDedup(snapshot) : null;
      this.connectionState.connected();
    } catch (e) {
      this.emitError(e as Error);
      // Close the failed attempt so it can't leak or fire a second handleClose (marks it
      // closedByUs → its later 'close' event is ignored), then schedule the next bounded
      // attempt directly (bypassing the closedByUs guard that handleClose would trip on).
      attempt?.close();
      this.scheduleReconnect();
    }
  }

  private async fetchSnapshot(ws: ContinuityTransport): Promise<CatchupSnapshot | null> {
    if (!this.runtime) return null;
    try {
      const resp = await ws.request<MessagesListResponseFrame>(
        (rid) => buildConversationMessagesList(rid, this.runtime as Runtime),
        Outbound.conversationMessagesList,
      );
      if (!resp.success) {
        this.config.onWarn?.(
          `catch-up snapshot failed: ${resp.error ?? "unknown"} — resuming without dedup`,
        );
        return null;
      }
      return snapshotFromResponse(resp);
    } catch (e) {
      // A snapshot RPC that failed because the SOCKET died is not "resume without dedup" — it is
      // a failed reconnect attempt. Swallowing it let the caller fall through to connected().
      if (ws.isClosed) throw e;
      this.config.onWarn?.(
        `catch-up snapshot error: ${(e as Error).message} — resuming without dedup`,
      );
      return null;
    }
  }

  private emitApproval(frame: ControlRequestFrame, outcome: ApprovalEvent["outcome"]): void {
    const event: ApprovalEvent = {
      requestId: frame.request_id,
      toolName: controlRequestToolName(frame),
      outcome,
    };
    fanOut(this.approvalListeners, [event], (e) =>
      this.config.onWarn?.(`approval listener threw: ${e.message}`),
    );
  }

  private emitFatal(err: ContinuityFatalError): void {
    // Fatal implies error: existing consumers that only watch onError keep working unchanged.
    this.emitError(err);
    fanOut(this.fatalListeners, [err], (e) =>
      this.config.onWarn?.(`fatal listener threw: ${e.message}`),
    );
  }

  private emitError(err: Error): void {
    fanOut(this.errorListeners, [err], (e) =>
      this.config.onWarn?.(`error listener threw: ${e.message}`),
    );
  }
}

export type { RenderEvent, RenderListener } from "./stream.js";
export type { ConnectionState } from "./connection.js";
export type { ContinuityPointer } from "./pointer.js";
export { readPointer, writePointer, PointerError } from "./pointer.js";
export { assertLoopbackUrl, TrustBoundaryError } from "./trust.js";
export type { Attribution, OwnershipSnapshot } from "./ownership.js";
/**
 * Exported because BOTH clients keep bounded id caches and each had rolled its own loop. The
 * terminal's two origin caches were the third and fourth copies; Unit 6 would have been the fifth.
 */
export { evictOldest, type BoundedCollection } from "./evict.js";
/**
 * The transport CONTRACT is public; the Node implementation of it is not.
 *
 * `export { WsConnection }` had no consumer in either package — every internal user imports it
 * from `./ws.js` directly — and exporting it pinned the Node-only `ws` package into the public
 * module graph of a package whose next consumer is a browser. What Unit 6 needs from this barrel
 * is the interface it must satisfy, not the implementation it cannot use.
 */
export type { ContinuityTransport } from "./ws.js";
export type { WsConnectionOptions } from "./ws.js";
export * as protocol from "./protocol.js";
