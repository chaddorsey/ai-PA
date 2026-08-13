/**
 * ws.ts — the single ordered WS connection to the sole-owner App Server.
 *
 * Loopback, no auth (R20). Opens `ws://127.0.0.1:4577/ws`, performs the `runtime_start`
 * hello, asserts the server version (best-effort — see protocol.assertServerVersion), then
 * pumps parsed+validated broadcast frames to a listener and resolves `request_id`-keyed RPCs.
 *
 * EVERY network wait is bounded (open, hello, RPC). There are no unbounded waits and no
 * retry loops here — reconnect policy is bounded and owned by connection.ts / the facade.
 */

import { type RawData, WebSocket } from "ws";
import {
  ProtocolError,
  RpcResponseFor,
  type Runtime,
  type RuntimeStartResponseFrame,
  type ServerFrame,
  type VersionPolicy,
  assertServerVersion,
  buildRuntimeStart,
  nextRequestId,
  parseFrame,
  validateInboundFrame,
} from "./protocol.js";

export interface WsConnectionOptions {
  url: string;
  runtime: Runtime;
  pinnedVersion?: string;
  versionPolicy?: VersionPolicy;
  openTimeoutMs?: number;
  helloTimeoutMs?: number;
  rpcTimeoutMs?: number;
  onWarn?: (msg: string) => void;
}

interface Pending {
  responseType: string;
  resolve: (frame: ServerFrame) => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

const DEFAULTS = { openTimeoutMs: 10_000, helloTimeoutMs: 15_000, rpcTimeoutMs: 15_000 };

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
  private readonly opts: Required<Omit<WsConnectionOptions, "pinnedVersion" | "versionPolicy">> &
    Pick<WsConnectionOptions, "pinnedVersion" | "versionPolicy">;
  private closedByUs = false;

  constructor(options: WsConnectionOptions) {
    this.opts = {
      onWarn: () => {},
      openTimeoutMs: DEFAULTS.openTimeoutMs,
      helloTimeoutMs: DEFAULTS.helloTimeoutMs,
      rpcTimeoutMs: DEFAULTS.rpcTimeoutMs,
      ...options,
    };
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

    const hello = await this.doHello();
    assertServerVersion(hello, {
      pinnedVersion: this.opts.pinnedVersion,
      policy: this.opts.versionPolicy,
      onWarn: this.opts.onWarn,
    });
    return hello;
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
    const requestId = nextRequestId("rt");
    const frame = buildRuntimeStart(requestId, this.opts.runtime);
    const p = this.registerPending<RuntimeStartResponseFrame>(
      requestId,
      "runtime_start_response",
      this.opts.helloTimeoutMs,
    );
    this.rawSend(frame);
    return p;
  }

  /** Send a `conversation_*` RPC and await its `*_response`, correlated by request_id. */
  async request<T extends ServerFrame = ServerFrame>(
    build: (requestId: string) => ServerFrame,
    requestType: string,
    timeoutMs?: number,
  ): Promise<T> {
    const responseType = RpcResponseFor[requestType];
    if (!responseType) throw new ProtocolError(`no known response type for RPC \`${requestType}\``);
    const requestId = nextRequestId("rpc");
    const frame = build(requestId);
    const p = this.registerPending<T>(requestId, responseType, timeoutMs ?? this.opts.rpcTimeoutMs);
    this.rawSend(frame);
    return p;
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

  private registerPending<T extends ServerFrame>(
    requestId: string,
    responseType: string,
    timeoutMs: number,
  ): Promise<T> {
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
      // Loud drift signal — surface it, do not silently mis-render.
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
    for (const l of this.frameListeners) l(frame);
  }

  private handleClose(code: number, reason: string): void {
    for (const [, pend] of this.pending) {
      clearTimeout(pend.timer);
      pend.reject(new Error(`connection closed (code=${code})`));
    }
    this.pending.clear();
    for (const l of this.closeListeners) l(code, reason);
  }

  private emitError(err: Error): void {
    for (const l of this.errorListeners) l(err);
  }
}
