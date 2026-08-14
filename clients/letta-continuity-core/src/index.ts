/**
 * index.ts — ContinuityCore: the reusable client-core both M1 clients import.
 *
 * One raw-WS ordered connection to the sole-owner App Server for a single `{agent, conversation}`:
 *   • live render of own AND foreign turns off one `event_seq`-ordered stream (stream.ts)
 *   • `conversation_*` management RPCs (for later rail reuse)
 *   • approvals that FAIL CLOSED — the injecting client auto-denies; observers never respond
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
import { type Attribution, type OwnershipSnapshot, RunOwnership } from "./ownership.js";
import { type ContinuityPointer, readPointer } from "./pointer.js";
import {
  type ControlRequestFrame,
  type ConversationCreateResponseFrame,
  type ConversationListResponseFrame,
  type ConversationSummary,
  type MessagesListResponseFrame,
  Outbound,
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
  isQueue,
  isStreamDelta,
  isTurnFinished,
  newClientNonce,
  nextRequestId,
  queueRemovals,
} from "./protocol.js";
import { type RenderEvent, type RenderListener, StreamAssembler } from "./stream.js";
import { WsConnection } from "./ws.js";

const WS_URL = "ws://127.0.0.1:4577/ws";

/**
 * The reason attached to every M1 auto-deny. The server requires a string message on a deny, and
 * this one is written for the human who finds it in a transcript, not for a log parser.
 */
const APPROVAL_DENY_MESSAGE =
  "Auto-denied: this conversation is shared across surfaces and has no interactive approval UI yet (milestone 1).";

export interface ContinuityCoreConfig {
  /** Path to the durable `{agent, conversation}` pointer file (pointer.ts). */
  pointerPath: string;
  url?: string;
  pinnedVersion?: string | readonly string[];
  versionPolicy?: VersionPolicy;
  maxReconnectAttempts?: number;
  reconnectDelayMs?: number;
  openTimeoutMs?: number;
  helloTimeoutMs?: number;
  rpcTimeoutMs?: number;
  serverInfoTimeoutMs?: number;
  /** Flat reconnect delay override (tests). Omit for exponential backoff with jitter. */
  jitter?: () => number;
  /** Override the per-instance correlation nonce (tests, or a bridge fanning out to N browsers). */
  clientNonce?: string;
  onWarn?: (msg: string) => void;
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
  outcome: "denied";
}

export class ContinuityCore {
  private readonly config: ContinuityCoreConfig;
  private readonly connectionState: ConnectionStateMachine;
  private readonly assembler = new StreamAssembler();
  private pointer: ContinuityPointer | null = null;
  private runtime: Runtime | null = null;
  private ws: WsConnection | null = null;
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
  private stopped = false;
  private readonly errorListeners = new Set<(err: Error) => void>();
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
    this.pointer = await readPointer(this.config.pointerPath);
    this.runtime = {
      agent_id: this.pointer.agentId,
      conversation_id: this.pointer.conversationId,
    };
    await this.openConnection();
  }

  /**
   * Submit a user turn. Registers a correlation claim so the resulting run can be identified
   * as ours (see ownership.ts) — which is what makes approval fail-closed exact rather than
   * a guess based on how many turns are outstanding.
   */
  send(text: string): void {
    if (!this.ws || !this.runtime) throw new Error("ContinuityCore not started");
    const requestId = nextRequestId("input", this.clientNonce);
    const clientMessageId = nextRequestId("cm", this.clientNonce);
    // Register the claim only once the frame is actually on the wire. Registering first leaves a
    // claim for a send that threw, and nothing can ever resolve it — hasOutstanding() then stays
    // true for the process lifetime, which pins every downstream bound that depends on it.
    this.ownership.beginSend(requestId, clientMessageId);
    try {
      this.ws.send(buildInput(this.runtime, text, { requestId, clientMessageId }));
    } catch (err) {
      this.ownership.abandon(requestId);
      throw err;
    }
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
    return resp.conversations;
  }

  /** Create a conversation for the pointer's agent (rail primitive; also the Unit 8 seed op). */
  async conversationCreate(title?: string): Promise<{ id: string } | undefined> {
    const agentId = this.getRuntime().agent_id;
    const ws = this.requireWs();
    const resp = await ws.request<ConversationCreateResponseFrame>(
      (rid) => buildConversationCreate(rid, agentId, title),
      Outbound.conversationCreate,
    );
    return resp.conversation ? { id: resp.conversation.id } : undefined;
  }

  /** Close the connection and cancel any pending reconnect. Idempotent. */
  stop(): void {
    this.stopped = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.connectionState.disconnected();
  }

  // ── internals ────────────────────────────────────────────────────────────

  private requireWs(): WsConnection {
    if (!this.ws) throw new Error("ContinuityCore not connected");
    return this.ws;
  }

  /**
   * Build a wired WsConnection. Single construction point so the initial connect and the
   * reconnect path can never drift in their options (notably the version-gate settings).
   */
  private newConnection(): WsConnection {
    if (!this.runtime) throw new Error("runtime not resolved");
    const ws = new WsConnection({
      url: this.config.url ?? WS_URL,
      runtime: this.runtime,
      pinnedVersion: this.config.pinnedVersion,
      versionPolicy: this.config.versionPolicy,
      openTimeoutMs: this.config.openTimeoutMs,
      helloTimeoutMs: this.config.helloTimeoutMs,
      rpcTimeoutMs: this.config.rpcTimeoutMs,
      serverInfoTimeoutMs: this.config.serverInfoTimeoutMs,
      clientNonce: this.clientNonce,
      onWarn: this.config.onWarn,
    });
    ws.onFrame((f) => this.routeFrame(f));
    ws.onError((e) => this.emitError(e));
    ws.onClose(() => this.handleClose());
    return ws;
  }

  private async openConnection(): Promise<void> {
    this.connectionState.connecting();
    const ws = this.newConnection();
    this.ws = ws;
    await ws.connect();
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
      this.ownership.onInputAccepted(frame.request_id, frame.accepted, frame.disposition);
      if (!frame.accepted) {
        this.emitError(new Error(`input rejected by the server: ${frame.error ?? "unknown"}`));
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
          this.ws.send(buildApprovalDeny(responseId, this.runtime, id, APPROVAL_DENY_MESSAGE));
        } catch (err) {
          this.sentApprovalResponses.delete(responseId);
          // Leave `id` unanswered so a redelivery after reconnect is answered rather than skipped.
          this.emitError(err instanceof Error ? err : new Error(String(err)));
          return;
        }
        this.answeredApprovals.add(id);
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
    this.assembler.ingest(frame);
  }

  private handleClose(): void {
    if (this.stopped || this.ws?.isClosedByUs) return;
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
      this.emitError(
        new Error(
          "reconnect budget exhausted — the App Server did not come back. Restart this client once it is up.",
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
    try {
      const ws = this.newConnection();
      // New connection ⇒ event_seq restarts; forget the per-connection ordering watermark.
      this.assembler.reset();
      // The gap may have hidden an ack, a dequeue, or a turn_finished — attribution is no
      // longer trustworthy, so unknown approvals fail closed until outstanding work drains.
      this.ownership.onReconnect();
      // Per-connection state: an answer we believe we sent may have died with the old socket, and
      // an ack for it can no longer arrive. Both sets must not outlive the connection.
      this.answeredApprovals = new Set();
      this.sentApprovalResponses = new Set();
      this.ws = ws;
      await ws.connect();
      // Snapshot BEFORE resuming live so the message-id watermark bridges the seam.
      const snapshot = await this.fetchSnapshot(ws);
      this.liveDedup = snapshot ? new LiveDedup(snapshot) : null;
      this.connectionState.connected();
    } catch (e) {
      this.emitError(e as Error);
      // Close the failed socket so it can't leak or fire a second handleClose (marks it
      // closedByUs → its later 'close' event is ignored), then schedule the next bounded
      // attempt directly (bypassing the closedByUs guard that handleClose would trip on).
      this.ws?.close();
      this.scheduleReconnect();
    }
  }

  private async fetchSnapshot(ws: WsConnection): Promise<CatchupSnapshot | null> {
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
    for (const l of this.approvalListeners) l(event);
  }

  private emitError(err: Error): void {
    for (const l of this.errorListeners) l(err);
  }
}

export type { RenderEvent, RenderListener } from "./stream.js";
export type { ConnectionState } from "./connection.js";
export type { ContinuityPointer } from "./pointer.js";
export type { Attribution, OwnershipSnapshot } from "./ownership.js";
export * as protocol from "./protocol.js";
