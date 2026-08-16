/**
 * controller-core.ts — the C6 transport: the terminal as a SURFACE of the Continuity
 * Controller (surface protocol v1) instead of a raw App-Server WS client.
 *
 * Satisfies the SAME seams the raw core does (`SessionCore` for the human path,
 * `JsonBridgeCore` for `--json`), so render/sanitize/NDJSON/exit-code behaviour — all reviewed
 * and mutation-bound — carries over UNCHANGED. What changes underneath:
 *
 *  - attribution is CONTROLLER DATA: every journal event carries the turn's
 *    `client_message_id`, and `turn_accepted` carries its origin (which surface session, or
 *    cli/ingress). The local ownership machinery is gone, not re-implemented.
 *  - detach is safe BY DESIGN: the controller (anchor+worker) holds the runtime's
 *    subscriptions, so leaving the terminal mid-turn no longer cancels the turn — the inverse
 *    of the raw-WS q5 capture, and C6's verification criterion.
 *  - reconnect catch-up is the surface cursor (journal row id): re-attach replays exactly the
 *    rows this terminal has not seen.
 *
 * The direct raw-WS path REMAINS in main.ts behind `--direct` as the emergency break-glass
 * client (operator decision 2026-08-15) — while it is in use, single-submitter ownership and
 * attribution guarantees are suspended, and it says so.
 */

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import type { ApprovalEvent, ConnectionState, RenderEvent } from "@ai-pa/letta-continuity-core";
import type { protocol } from "@ai-pa/letta-continuity-core";

const require = createRequire(import.meta.url);
const { WebSocket } = require("ws") as typeof import("ws");

type SurfaceFrame = { type: string } & Record<string, unknown>;

export interface ControllerCoreOptions {
  /** Controller surface endpoint, e.g. ws://127.0.0.1:4610/surface. Loopback only. */
  url: string;
  tokenFile: string;
  runtime: { agent_id: string; conversation_id: string };
  onWarn?: (msg: string) => void;
  /** Reconnect pacing (tests tighten it). */
  reconnectDelayMs?: number;
  maxReconnectAttempts?: number;
}

export class ControllerFatalError extends Error {
  override name = "ControllerFatalError";
  constructor(
    message: string,
    readonly reason: string = "controller",
  ) {
    super(message);
  }
}

const DEFAULT_RECONNECT_DELAY_MS = 1000;
const DEFAULT_MAX_RECONNECT_ATTEMPTS = 10;
/** Bounded caches, matching the terminal's own eviction discipline. */
const MAX_TRACKED = 512;

function bound(set: Set<string> | Map<string, unknown>): void {
  while (set.size > MAX_TRACKED) {
    const oldest = set.keys().next().value;
    if (oldest === undefined) return;
    set.delete(oldest);
  }
}

/** Extract renderable text from a journaled delta payload. */
function deltaText(delta: Record<string, unknown>): string | undefined {
  const content = delta.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    const joined = content
      .map((p) => (typeof p === "string" ? p : ((p as { text?: string })?.text ?? "")))
      .join("");
    return joined === "" ? undefined : joined;
  }
  const toolReturn = delta.tool_return;
  if (typeof toolReturn === "string") return toolReturn;
  return undefined;
}

export class ControllerCore {
  private socket: import("ws").WebSocket | null = null;
  private readonly renderListeners = new Set<(e: RenderEvent) => void>();
  private readonly stateListeners = new Set<(s: ConnectionState, prev: ConnectionState) => void>();
  private readonly errorListeners = new Set<(err: Error) => void>();
  private readonly approvalListeners = new Set<(e: ApprovalEvent) => void>();
  private readonly fatalListeners = new Set<(err: ControllerFatalError) => void>();
  private readonly receiptListeners = new Set<(clientMessageId: string) => void>();

  /** Turns THIS surface submitted (send receipts). */
  private readonly myClientMessageIds = new Set<string>();
  /** run_id → origin, learned from journal events' client_message_id + turn_accepted origins. */
  private readonly runOrigins = new Map<string, "mine" | "foreign" | "unknown">();
  /** client_message_id → self/peer, learned from turn_accepted origin stamps. */
  private readonly cmOrigins = new Map<string, "mine" | "foreign">();
  private readonly pendingApprovals: string[] = [];

  private cursor: number | null = null;
  private sessionId: string | null = null;
  private state: ConnectionState = "disconnected";
  private activeRunId: string | null = null;
  private sendCounter = 0;
  private reconnectAttempts = 0;
  private stopped = false;
  private generation = 0;

  constructor(private readonly opts: ControllerCoreOptions) {}

  // ── SessionCore seam ──────────────────────────────────────────────────────
  onRender = (cb: (event: RenderEvent) => void): (() => void) => {
    this.renderListeners.add(cb);
    return () => this.renderListeners.delete(cb);
  };
  onConnectionState = (
    cb: (state: ConnectionState, prev: ConnectionState) => void,
  ): (() => void) => {
    this.stateListeners.add(cb);
    return () => this.stateListeners.delete(cb);
  };
  onError = (cb: (err: Error) => void): (() => void) => {
    this.errorListeners.add(cb);
    return () => this.errorListeners.delete(cb);
  };
  onApproval = (cb: (e: ApprovalEvent) => void): (() => void) => {
    this.approvalListeners.add(cb);
    return () => this.approvalListeners.delete(cb);
  };
  onFatal = (cb: (err: ControllerFatalError) => void): (() => void) => {
    this.fatalListeners.add(cb);
    return () => this.fatalListeners.delete(cb);
  };
  /** Send receipts (`send_ok` → client_message_id) — the one-shot keys its wait on this. */
  onReceipt = (cb: (clientMessageId: string) => void): (() => void) => {
    this.receiptListeners.add(cb);
    return () => this.receiptListeners.delete(cb);
  };
  private readonly outcomeListeners = new Set<
    (clientMessageId: string | null, outcome: string) => void
  >();
  /**
   * Turn outcomes BY client_message_id — controller data, so the one-shot can wait for exactly
   * the turn its send receipt named instead of inferring from idle heuristics.
   */
  onTurnOutcome = (cb: (clientMessageId: string | null, outcome: string) => void): (() => void) => {
    this.outcomeListeners.add(cb);
    return () => this.outcomeListeners.delete(cb);
  };

  ownsRun = (runId: string | undefined): boolean => this.attributeRun(runId) === "mine";

  attributeRun = (runId: string | undefined): "mine" | "foreign" | "unknown" => {
    if (!runId) return "unknown";
    return this.runOrigins.get(runId) ?? "unknown";
  };

  /** The controller queues internally; the server-side queue frames never reach surfaces. */
  queueHasMine = (_frame: protocol.ServerFrame, _origin?: string): boolean => false;

  send = (text: string): void => {
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN || !this.sessionId) {
      throw new Error("controller connection is not open");
    }
    this.sendCounter += 1;
    socket.send(JSON.stringify({ type: "send", request_id: `send-${this.sendCounter}`, text }));
  };

  /** Operator abort (surface `abort` capability). Resolves with whether a turn was aborted. */
  abort = (): void => {
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) throw new Error("not connected");
    this.sendCounter += 1;
    socket.send(JSON.stringify({ type: "abort", request_id: `abort-${this.sendCounter}` }));
  };

  /** Answer the OLDEST pending approval. Returns false when none is pending. */
  answerApproval = (behavior: "allow" | "deny"): boolean => {
    const approvalId = this.pendingApprovals.shift();
    if (!approvalId) return false;
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(
      JSON.stringify({ type: "approval_answer", approval_id: approvalId, decision: { behavior } }),
    );
    return true;
  };

  get pendingApprovalCount(): number {
    return this.pendingApprovals.length;
  }

  getRuntime = (): { agent_id: string; conversation_id: string } => this.opts.runtime;

  async start(): Promise<void> {
    this.stopped = false;
    await this.connectOnce();
  }

  stop(): void {
    this.stopped = true;
    this.socket?.close();
    this.socket = null;
    this.transition("disconnected");
  }

  // ── connection lifecycle ──────────────────────────────────────────────────

  private async connectOnce(): Promise<void> {
    const generation = ++this.generation;
    this.transition(this.state === "disconnected" ? "connecting" : "reconnecting");
    let token: string;
    try {
      token = readFileSync(this.opts.tokenFile, "utf8").trim();
    } catch (e) {
      throw new ControllerFatalError(
        `cannot read the surface token (${e instanceof Error ? e.message : String(e)}) — is the controller installed? (${this.opts.tokenFile})`,
        "token",
      );
    }
    const socket = new WebSocket(this.opts.url);
    this.socket = socket;
    await new Promise<void>((resolveOpen, rejectOpen) => {
      socket.once("open", () => resolveOpen());
      socket.once("error", (e: Error) =>
        rejectOpen(new Error(`controller unreachable: ${e.message}`)),
      );
    });
    socket.on("message", (data) => {
      if (generation !== this.generation) return;
      let frame: SurfaceFrame;
      try {
        frame = JSON.parse(data.toString()) as SurfaceFrame;
      } catch {
        this.emitError(new Error("controller sent a non-JSON frame"));
        return;
      }
      this.onFrame(frame);
    });
    socket.on("error", (e: Error) => {
      if (generation === this.generation) this.emitError(e);
    });
    socket.on("close", () => {
      if (generation !== this.generation || this.stopped) return;
      this.scheduleReconnect();
    });
    socket.send(
      JSON.stringify({
        type: "attach",
        token,
        protocol_version: 1,
        capabilities: ["core", "abort", "approvals"],
        runtime: this.opts.runtime,
        cursor: this.cursor,
      }),
    );
    await new Promise<void>((resolveAttach, rejectAttach) => {
      const timer = setTimeout(() => rejectAttach(new Error("attach timed out")), 15_000);
      const onFrame = (raw: import("ws").RawData): void => {
        const frame = JSON.parse(raw.toString()) as SurfaceFrame;
        if (frame.type === "attach_ok") {
          clearTimeout(timer);
          socket.off("message", onFrame);
          resolveAttach();
        } else if (frame.type === "attach_denied") {
          clearTimeout(timer);
          socket.off("message", onFrame);
          rejectAttach(
            new ControllerFatalError(`attach denied: ${String(frame.reason)}`, "attach-denied"),
          );
        }
      };
      socket.on("message", onFrame);
    });
  }

  private scheduleReconnect(): void {
    this.reconnectAttempts += 1;
    if (
      this.reconnectAttempts > (this.opts.maxReconnectAttempts ?? DEFAULT_MAX_RECONNECT_ATTEMPTS)
    ) {
      this.transition("disconnected");
      this.emitFatal(
        new ControllerFatalError("controller reconnect budget exhausted", "reconnect"),
      );
      return;
    }
    this.transition("reconnecting");
    const timer = setTimeout(() => {
      void this.connectOnce().catch((e) => {
        this.emitError(e instanceof Error ? e : new Error(String(e)));
        if (!this.stopped) this.scheduleReconnect();
      });
    }, this.opts.reconnectDelayMs ?? DEFAULT_RECONNECT_DELAY_MS);
    timer.unref?.();
  }

  // ── frame handling ────────────────────────────────────────────────────────

  private onFrame(frame: SurfaceFrame): void {
    if (frame.type === "attach_ok") {
      this.sessionId = frame.session_id as string;
      this.cursor = (frame.cursor as number) ?? this.cursor;
      this.reconnectAttempts = 0;
      for (const event of (frame.replay as SurfaceFrame[]) ?? []) this.onEvent(event);
      this.transition("connected");
      return;
    }
    if (frame.type === "event") {
      this.onEvent(frame);
      return;
    }
    if (frame.type === "send_ok") {
      const clientMessageId = frame.client_message_id as string;
      this.myClientMessageIds.add(clientMessageId);
      this.cmOrigins.set(clientMessageId, "mine");
      bound(this.myClientMessageIds);
      bound(this.cmOrigins);
      for (const cb of this.receiptListeners) cb(clientMessageId);
      return;
    }
    if (frame.type === "approval_request") {
      const approvalId = frame.approval_id as string;
      this.pendingApprovals.push(approvalId);
      const request = (frame.request as Record<string, unknown>) ?? {};
      for (const cb of this.approvalListeners) {
        cb({
          requestId: approvalId,
          toolName: typeof request.tool_name === "string" ? request.tool_name : undefined,
          outcome: "pending",
        });
      }
      return;
    }
    if (frame.type === "approval_resolved") {
      const approvalId = frame.approval_id as string;
      const index = this.pendingApprovals.indexOf(approvalId);
      if (index >= 0) this.pendingApprovals.splice(index, 1);
      return;
    }
    if (frame.type === "error") {
      this.emitError(new Error(String(frame.message ?? "controller error")));
      return;
    }
    // abort_ok and unknown forward-compat frames: tolerated.
  }

  /** Map one journal event row onto the RenderEvent vocabulary the renderer already speaks. */
  private onEvent(event: SurfaceFrame): void {
    const id = event.id as number;
    if (typeof id === "number") this.cursor = Math.max(this.cursor ?? 0, id);
    const kind = event.kind as string;
    const clientMessageId = (event.client_message_id as string | null) ?? null;
    const payload = (event.payload as Record<string, unknown>) ?? {};

    if (kind === "turn_accepted") {
      if (clientMessageId) {
        const origin = (payload.origin as { session?: string } | undefined)?.session;
        // Attribution is CONTROLLER DATA: my session's sends are already recorded via send_ok;
        // anything else that was accepted is a peer (another surface, the CLI, an ingress).
        if (!this.myClientMessageIds.has(clientMessageId)) {
          this.cmOrigins.set(clientMessageId, "foreign");
          bound(this.cmOrigins);
        }
        void origin;
      }
      return;
    }

    const delta = payload.delta as Record<string, unknown> | undefined;
    if (delta && typeof delta.message_type === "string") {
      const runId = typeof delta.run_id === "string" ? delta.run_id : undefined;
      if (runId && clientMessageId) {
        this.runOrigins.set(runId, this.cmOrigins.get(clientMessageId) ?? "unknown");
        bound(this.runOrigins);
      }
      if (runId && runId !== this.activeRunId) {
        this.activeRunId = runId;
        this.emitRender({ type: "turn_start", eventSeq: id, runId, frame: this.stubFrame(kind) });
      }
      this.emitRender({
        type: "delta",
        eventSeq: id,
        runId,
        messageId: typeof delta.id === "string" ? delta.id : undefined,
        messageType: delta.message_type,
        text: deltaText(delta),
        frame: this.stubFrame(kind),
      });
      return;
    }

    if (kind === "turn_terminal") {
      const outcome = String(payload.outcome ?? "");
      const runId =
        typeof payload.run_id === "string" ? payload.run_id : (this.activeRunId ?? undefined);
      this.activeRunId = null;
      const failed = outcome.startsWith("FAILED") || outcome.startsWith("failed");
      for (const cb of this.outcomeListeners) cb(clientMessageId, outcome);
      this.emitRender({
        type: "turn_finished",
        eventSeq: id,
        runId,
        stopReason: failed ? "error" : outcome === "end_turn" ? "end_turn" : outcome,
        frame: this.stubFrame(kind),
      });
      // Renderer flushes on idle; the controller journal has no loop_status rows, so emit the
      // idle boundary the terminal's line discipline expects.
      this.emitRender({
        type: "loop_status",
        eventSeq: id,
        status: "WAITING_ON_INPUT",
        frame: this.stubFrame(kind),
      });
      return;
    }

    if (kind === "turn_failed_visible") {
      this.activeRunId = null;
      for (const cb of this.outcomeListeners) cb(clientMessageId, "FAILED-VISIBLE");
      this.emitRender({
        type: "turn_finished",
        eventSeq: id,
        stopReason: "error",
        frame: this.stubFrame(kind),
      });
      this.emitError(
        new Error(
          `turn FAILED-VISIBLE: ${String(payload.reason ?? "unknown")} (${clientMessageId ?? "?"})`,
        ),
      );
      return;
    }
    // Other journal kinds (turn_submitted, input_accepted, update_queue, …) are bookkeeping.
  }

  private stubFrame(kind: string): protocol.ServerFrame {
    return { type: `surface:${kind}` } as protocol.ServerFrame;
  }

  private emitRender(event: RenderEvent): void {
    for (const cb of this.renderListeners) {
      try {
        cb(event);
      } catch {
        // Listener isolation, same rule as the raw core.
      }
    }
  }

  private emitError(err: Error): void {
    for (const cb of this.errorListeners) {
      try {
        cb(err);
      } catch {
        // isolated
      }
    }
  }

  private emitFatal(err: ControllerFatalError): void {
    for (const cb of this.fatalListeners) {
      try {
        cb(err);
      } catch {
        // isolated
      }
    }
  }

  private transition(next: ConnectionState): void {
    if (next === this.state) return;
    const prev = this.state;
    this.state = next;
    for (const cb of this.stateListeners) {
      try {
        cb(next, prev);
      } catch {
        // isolated
      }
    }
  }
}
