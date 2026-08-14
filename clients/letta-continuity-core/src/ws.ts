/**
 * ws.ts — the single ordered WS connection to the sole-owner App Server.
 *
 * Loopback, no auth (R20). Opens `ws://127.0.0.1:4577/ws`, runs the `app_server_info`
 * version gate (see protocol.assertServerIdentity), performs the `runtime_start` hello, then
 * pumps parsed+validated broadcast frames to a listener and resolves `request_id`-keyed RPCs.
 *
 * EVERY network wait is bounded (open, hello, RPC). There are no unbounded waits and no
 * retry loops here — reconnect policy is bounded and owned by connection.ts / the facade.
 */

import { type RawData, WebSocket } from "ws";
import { fanOut } from "./fanout.js";
import {
  type AppServerInfoResponseFrame,
  Outbound,
  ProtocolError,
  RpcResponseFor,
  type Runtime,
  type RuntimeStartResponseFrame,
  type ServerFrame,
  type ServerIdentityCheck,
  type VersionPolicy,
  assertServerIdentity,
  buildAppServerInfo,
  buildRuntimeStart,
  nextRequestId,
  parseFrame,
  validateInboundFrame,
} from "./protocol.js";

export interface WsConnectionOptions {
  url: string;
  runtime: Runtime;
  pinnedVersion?: string | readonly string[];
  versionPolicy?: VersionPolicy;
  openTimeoutMs?: number;
  helloTimeoutMs?: number;
  rpcTimeoutMs?: number;
  /**
   * Bound on the pre-hello `app_server_info` version gate. Deliberately short and separate
   * from `helloTimeoutMs`: a server too old to know the RPC never answers, and that must
   * degrade to a warning quickly rather than stalling every connect by the hello budget.
   */
  serverInfoTimeoutMs?: number;
  /** Per-instance nonce making this connection's correlation ids unique across processes. */
  clientNonce?: string;
  onWarn?: (msg: string) => void;
}

interface Pending {
  responseType: string;
  resolve: (frame: ServerFrame) => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

const DEFAULTS = {
  openTimeoutMs: 10_000,
  helloTimeoutMs: 15_000,
  rpcTimeoutMs: 15_000,
  serverInfoTimeoutMs: 5_000,
};

function rawToString(data: RawData): string {
  if (typeof data === "string") return data;
  if (Array.isArray(data)) return Buffer.concat(data).toString("utf-8");
  if (data instanceof ArrayBuffer) return Buffer.from(data).toString("utf-8");
  return (data as Buffer).toString("utf-8");
}

export class WsConnection {
  private socket: WebSocket | null = null;
  private readonly pending = new Map<string, Pending>();
  private readonly frameListeners = new Set<(frame: ServerFrame) => void>();
  private readonly errorListeners = new Set<(err: Error) => void>();
  private readonly closeListeners = new Set<(code: number, reason: string) => void>();
  private readonly opts: Required<
    Omit<WsConnectionOptions, "pinnedVersion" | "versionPolicy" | "clientNonce">
  > &
    Pick<WsConnectionOptions, "pinnedVersion" | "versionPolicy" | "clientNonce">;
  private closedByUs = false;
  private lastIdentity: ServerIdentityCheck | null = null;

  constructor(options: WsConnectionOptions) {
    // Resolve each field with ??, NOT by spreading `options` over the defaults. A caller that
    // forwards an unset config value passes the key with an explicit `undefined`, and a spread
    // happily overwrites the default with it — yielding `setTimeout(fn, undefined)`, which
    // fires immediately and turns every bound into a 0 ms timeout.
    this.opts = {
      url: options.url,
      runtime: options.runtime,
      pinnedVersion: options.pinnedVersion,
      versionPolicy: options.versionPolicy,
      clientNonce: options.clientNonce,
      onWarn: options.onWarn ?? (() => {}),
      openTimeoutMs: options.openTimeoutMs ?? DEFAULTS.openTimeoutMs,
      helloTimeoutMs: options.helloTimeoutMs ?? DEFAULTS.helloTimeoutMs,
      rpcTimeoutMs: options.rpcTimeoutMs ?? DEFAULTS.rpcTimeoutMs,
      serverInfoTimeoutMs: options.serverInfoTimeoutMs ?? DEFAULTS.serverInfoTimeoutMs,
    };
  }

  /** Result of the last `app_server_info` version gate, or null if connect() has not run. */
  get identity(): ServerIdentityCheck | null {
    return this.lastIdentity;
  }

  onFrame(cb: (frame: ServerFrame) => void): () => void {
    this.frameListeners.add(cb);
    return () => this.frameListeners.delete(cb);
  }
  onError(cb: (err: Error) => void): () => void {
    this.errorListeners.add(cb);
    return () => this.errorListeners.delete(cb);
  }
  onClose(cb: (code: number, reason: string) => void): () => void {
    this.closeListeners.add(cb);
    return () => this.closeListeners.delete(cb);
  }

  /** Open the socket, send the hello, assert version. Bounded by open + hello timeouts. */
  async connect(): Promise<RuntimeStartResponseFrame> {
    this.closedByUs = false;
    const socket = new WebSocket(this.opts.url);
    this.socket = socket;

    await this.waitForOpen(socket);

    socket.on("message", (data: RawData) => this.handleMessage(data));
    socket.on("error", (err: Error) => this.emitError(err));
    socket.on("close", (code: number, reason: Buffer) => this.handleClose(code, reason.toString()));

    // Version gate BEFORE the hello: fail fast on a drifted server rather than after
    // starting a runtime on it. Verified live — `app_server_info` answers pre-runtime_start.
    this.lastIdentity = await this.assertIdentity();

    return this.doHello();
  }

  /**
   * Run the `app_server_info` version gate.
   *
   * Three failure classes were previously laundered into one warning, which let a drifted server
   * through even under `refuse` — the policy chosen precisely to keep it out:
   *
   *   (a) no response at all      → the server predates the command. Genuinely "too old": warn.
   *   (b) a response that fails validation → DRIFT. The gate's whole purpose.
   *   (c) a response of the wrong type     → DRIFT.
   *
   * (b) and (c) both surface as `ProtocolError` now that a validation failure rejects the pending
   * RPC (see failPending), which is what makes them distinguishable from (a) at all.
   */
  private async assertIdentity(): Promise<ServerIdentityCheck | null> {
    let info: AppServerInfoResponseFrame;
    try {
      info = await this.request<AppServerInfoResponseFrame>(
        buildAppServerInfo,
        Outbound.appServerInfo,
        this.opts.serverInfoTimeoutMs,
      );
    } catch (err) {
      const drift = err instanceof ProtocolError;
      const detail = err instanceof Error ? err.message : String(err);
      if (drift && this.opts.versionPolicy === "refuse") {
        throw new ProtocolError(
          `app_server_info did not round-trip (${detail}) — refusing to attach to an unverified server`,
        );
      }
      this.opts.onWarn(
        drift
          ? `app_server_info drifted (${detail}); server version unverified — re-run the contract test`
          : `app_server_info unavailable (${detail}); server version unverified — the contract test is the only upgrade gate`,
      );
      return null;
    }
    return assertServerIdentity(info, {
      pinnedVersion: this.opts.pinnedVersion,
      policy: this.opts.versionPolicy,
      onWarn: this.opts.onWarn,
    });
  }

  private waitForOpen(socket: WebSocket): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        socket.terminate();
        reject(new Error(`WS open timed out after ${this.opts.openTimeoutMs}ms`));
      }, this.opts.openTimeoutMs);
      socket.once("open", () => {
        clearTimeout(timer);
        resolve();
      });
      socket.once("error", (err: Error) => {
        clearTimeout(timer);
        reject(err);
      });
    });
  }

  private doHello(): Promise<RuntimeStartResponseFrame> {
    const requestId = nextRequestId("rt", this.opts.clientNonce);
    const responseType = RpcResponseFor[Outbound.runtimeStart];
    if (!responseType) throw new ProtocolError("no known response type for `runtime_start`");
    return this.sendAndAwait<RuntimeStartResponseFrame>(
      buildRuntimeStart(requestId, this.opts.runtime),
      requestId,
      responseType,
      this.opts.helloTimeoutMs,
    );
  }

  /** Send a `conversation_*` RPC and await its `*_response`, correlated by request_id. */
  async request<T extends ServerFrame = ServerFrame>(
    build: (requestId: string) => ServerFrame,
    requestType: string,
    timeoutMs?: number,
  ): Promise<T> {
    const responseType = RpcResponseFor[requestType];
    if (!responseType) throw new ProtocolError(`no known response type for RPC \`${requestType}\``);
    const requestId = nextRequestId("rpc", this.opts.clientNonce);
    return this.sendAndAwait<T>(
      build(requestId),
      requestId,
      responseType,
      timeoutMs ?? this.opts.rpcTimeoutMs,
    );
  }

  /** Fire-and-forget send of an already-built frame (e.g. `input`, `approval_send`). */
  send(frame: ServerFrame): void {
    this.rawSend(frame);
  }

  close(): void {
    this.closedByUs = true;
    for (const [, pend] of this.pending) {
      clearTimeout(pend.timer);
      pend.reject(new Error("connection closed"));
    }
    this.pending.clear();
    this.socket?.close();
  }

  get isClosedByUs(): boolean {
    return this.closedByUs;
  }

  /**
   * Whether the socket can still carry traffic. Distinct from `isClosedByUs`, which records
   * INTENT: a socket the peer dropped is closed without us having closed it. Callers awaiting an
   * RPC need to tell "the request failed" from "the connection is gone".
   */
  get isClosed(): boolean {
    return this.socket === null || this.socket.readyState !== WebSocket.OPEN;
  }

  /**
   * Send a frame and register its waiter — in that order, and atomically from the caller's view.
   *
   * The ordering is load-bearing. Registering first and sending second leaks a pending entry
   * (with a live timer) whenever `rawSend` throws synchronously, because the caller never receives
   * the promise to await. That orphan later rejects with nobody listening, which under Node's
   * default unhandled-rejection policy terminates the process — during a reconnect, which is
   * exactly when the client is supposed to be recovering.
   */
  private sendAndAwait<T extends ServerFrame>(
    frame: ServerFrame,
    requestId: string,
    responseType: string,
    timeoutMs: number,
  ): Promise<T> {
    // Throws before any state is created, so a closed socket leaves nothing behind.
    this.rawSend(frame);
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(requestId);
        reject(
          new Error(
            `RPC \`${responseType}\` (request_id=${requestId}) timed out after ${timeoutMs}ms`,
          ),
        );
      }, timeoutMs);
      this.pending.set(requestId, {
        responseType,
        resolve: (f) => resolve(f as T),
        reject,
        timer,
      });
    });
  }

  private rawSend(frame: ServerFrame): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error(`cannot send \`${frame.type}\`: socket not open`);
    }
    this.socket.send(JSON.stringify(frame));
  }

  private handleMessage(data: RawData): void {
    let frame: ServerFrame;
    try {
      frame = parseFrame(rawToString(data));
    } catch (e) {
      this.emitError(e as Error);
      return;
    }
    try {
      validateInboundFrame(frame);
    } catch (e) {
      // Loud drift signal — surface it, do not silently mis-render. If this frame was an answer
      // to an in-flight RPC, reject THAT promise with the drift error: otherwise the caller waits
      // out its full timeout and reports a contract break as "the server was slow", which is how
      // a renamed field reaches the operator disguised as a transient failure.
      this.failPending(frame, e as Error);
      this.emitError(e as Error);
      return;
    }
    // Route request_id-matched RPC/hello responses to their waiter; broadcast everything else.
    const requestId = typeof frame.request_id === "string" ? frame.request_id : undefined;
    if (requestId && this.pending.has(requestId)) {
      const pend = this.pending.get(requestId);
      if (pend) {
        this.pending.delete(requestId);
        clearTimeout(pend.timer);
        if (frame.type === pend.responseType) {
          pend.resolve(frame);
        } else {
          pend.reject(
            new ProtocolError(
              `expected \`${pend.responseType}\` for request_id=${requestId}, got \`${frame.type}\``,
            ),
          );
        }
      }
      return;
    }
    fanOut(this.frameListeners, [frame], (e) =>
      this.opts.onWarn(`frame listener threw: ${e.message}`),
    );
  }

  /** Reject the pending RPC this frame was answering, if any. No-op for broadcasts. */
  private failPending(frame: ServerFrame, err: Error): void {
    const requestId = typeof frame.request_id === "string" ? frame.request_id : undefined;
    if (!requestId) return;
    const pend = this.pending.get(requestId);
    if (!pend) return;
    this.pending.delete(requestId);
    clearTimeout(pend.timer);
    pend.reject(err);
  }

  private handleClose(code: number, reason: string): void {
    for (const [, pend] of this.pending) {
      clearTimeout(pend.timer);
      pend.reject(new Error(`connection closed (code=${code})`));
    }
    this.pending.clear();
    fanOut(this.closeListeners, [code, reason], (e) =>
      this.opts.onWarn(`close listener threw: ${e.message}`),
    );
  }

  private emitError(err: Error): void {
    fanOut(this.errorListeners, [err], () => {});
  }
}
