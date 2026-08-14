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
import { type OwnershipSnapshot, RunOwnership } from "./ownership.js";
import { type ContinuityPointer, readPointer } from "./pointer.js";
import {
  type ConversationCreateResponseFrame,
  type ConversationListResponseFrame,
  type ConversationSummary,
  type MessagesListResponseFrame,
  Outbound,
  type Runtime,
  type ServerFrame,
  type VersionPolicy,
  approvalRequestId,
  buildApprovalSend,
  buildConversationCreate,
  buildConversationList,
  buildConversationMessagesList,
  buildInput,
  frameRunId,
  isApprovalRequest,
  isInputAccepted,
  isQueue,
  isStreamDelta,
  isTurnFinished,
  nextRequestId,
  queueRemovals,
} from "./protocol.js";
import { type RenderEvent, type RenderListener, StreamAssembler } from "./stream.js";
import { WsConnection } from "./ws.js";

const WS_URL = "ws://127.0.0.1:4577/ws";

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
  onWarn?: (msg: string) => void;
}

export class ContinuityCore {
  private readonly config: ContinuityCoreConfig;
  private readonly connectionState: ConnectionStateMachine;
  private readonly assembler = new StreamAssembler();
  private pointer: ContinuityPointer | null = null;
  private runtime: Runtime | null = null;
  private ws: WsConnection | null = null;
  private liveDedup: LiveDedup | null = null;
  /** Which runs on the shared conversation are ours (drives approval fail-closed). */
  private readonly ownership = new RunOwnership();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;
  private readonly errorListeners = new Set<(err: Error) => void>();

  constructor(config: ContinuityCoreConfig) {
    this.config = config;
    this.connectionState = new ConnectionStateMachine(
      config.maxReconnectAttempts !== undefined
        ? { maxReconnectAttempts: config.maxReconnectAttempts }
        : {},
    );
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
    const requestId = nextRequestId("input");
    const clientMessageId = nextRequestId("cm");
    this.ownership.beginSend(requestId, clientMessageId);
    this.ws.send(buildInput(this.runtime, text, { requestId, clientMessageId }));
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
    return runId !== undefined && this.ownership.owns(runId);
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
      this.ownership.onInputAccepted(frame.request_id, frame.accepted, frame.disposition);
      if (!frame.accepted) {
        this.emitError(new Error(`input rejected by the server: ${frame.error ?? "unknown"}`));
      }
      return; // control-channel ack: never rendered
    }
    if (isQueue(frame)) {
      this.ownership.onQueueRemovals(queueRemovals(frame));
      // fall through: the assembler may surface a "queued…" indicator
    }

    // Approval fail-closed: only the client that STARTED this run responds, and it always
    // DENIES in M1. Gating on run ownership (not an outstanding-turn counter) is what stops a
    // foreign turn's completion from silencing our own deny, or our own gap from making us
    // answer a peer's approval.
    if (isApprovalRequest(frame)) {
      if (this.ownership.shouldRespondToApproval(frame.run_id) && this.ws && this.runtime) {
        const rid = nextRequestId("appr");
        const approvalId = approvalRequestId(frame) ?? "";
        this.ws.send(buildApprovalSend(rid, this.runtime, approvalId, "deny"));
      }
      return; // observers do nothing; not rendered in M1
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
      this.ownership.onTurnFinished(frame.run_id);
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
    if (!mayRetry) return; // exhausted → disconnected (bounded, no infinite loop)
    const delay = this.config.reconnectDelayMs ?? 1_000;
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

  private emitError(err: Error): void {
    for (const l of this.errorListeners) l(err);
  }
}

export type { RenderEvent, RenderListener } from "./stream.js";
export type { ConnectionState } from "./connection.js";
export type { ContinuityPointer } from "./pointer.js";
export type { OwnershipSnapshot } from "./ownership.js";
export * as protocol from "./protocol.js";
