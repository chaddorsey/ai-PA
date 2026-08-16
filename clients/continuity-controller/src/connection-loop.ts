/**
 * connection-loop.ts — the resident reconnect loop shared by anchor and worker.
 *
 * Wraps core's WsConnection + ConnectionStateMachine into "keep one bare connection alive
 * forever, re-running the caller's subscription routine on every (re)connect". The budget is
 * BOUNDED (learnings: recovery = surviving the stability window, not opening); when it is
 * exhausted the loop reports it and the daemon EXITS non-zero — launchd's KeepAlive is the
 * outer, genuinely unbounded loop, and a process restart is visible where an in-process silent
 * retry storm is not.
 *
 * Close handlers are identity-guarded (learnings): a superseded connection's close event must
 * not schedule a reconnect for the current one.
 */

import {
  ConnectionStateMachine,
  type ReconnectPolicy,
} from "@ai-pa/letta-continuity-core/connection";
import { WsConnection } from "@ai-pa/letta-continuity-core/ws";

export interface ConnectionLoopOptions {
  url: string;
  /** Re-establish subscriptions/state on this fresh connection. A throw counts as a drop. */
  onConnected: (conn: WsConnection) => Promise<void>;
  /** The reconnect budget ran out. The daemon should exit; launchd restarts it visibly. */
  onExhausted: () => void;
  onWarn?: (msg: string) => void;
  reconnect?: ReconnectPolicy;
  /** Injectable for tests. */
  makeConnection?: (url: string, onWarn: (msg: string) => void) => WsConnection;
}

export class ConnectionLoop {
  private readonly sm: ConnectionStateMachine;
  private conn: WsConnection | null = null;
  private generation = 0;
  private stopped = false;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private readonly opts: ConnectionLoopOptions) {
    this.sm = new ConnectionStateMachine(opts.reconnect);
  }

  get state(): string {
    return this.sm.current;
  }

  /** The live connection, or null while down. Callers must tolerate null between generations. */
  get current(): WsConnection | null {
    return this.conn;
  }

  async start(): Promise<void> {
    this.stopped = false;
    this.sm.connecting();
    await this.attempt();
  }

  stop(): void {
    this.stopped = true;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.conn?.close();
    this.conn = null;
    this.sm.disconnected();
  }

  /** Drop the current connection on purpose (e.g. a failed liveness probe) → loop reconnects. */
  bounce(reason: string): void {
    this.opts.onWarn?.(`bouncing connection: ${reason}`);
    // close() marks closedByUs, which would suppress the reconnect — so detach and reconnect
    // explicitly instead of relying on the close event.
    const old = this.conn;
    this.conn = null;
    this.generation += 1;
    old?.close();
    if (!this.stopped) this.scheduleRetry();
  }

  private async attempt(): Promise<void> {
    if (this.stopped) return;
    const generation = ++this.generation;
    const warn = this.opts.onWarn ?? (() => {});
    const conn =
      this.opts.makeConnection?.(this.opts.url, warn) ??
      new WsConnection({ url: this.opts.url, versionPolicy: "warn", onWarn: warn });
    try {
      await conn.connectBare();
      conn.onClose(() => {
        // Identity guard: only the CURRENT generation's close schedules a reconnect.
        if (this.stopped || generation !== this.generation) return;
        this.conn = null;
        this.scheduleRetry();
      });
      await this.opts.onConnected(conn);
      if (generation !== this.generation || this.stopped) {
        conn.close();
        return;
      }
      this.conn = conn;
      this.sm.connected();
    } catch (e) {
      warn(`connect attempt failed: ${e instanceof Error ? e.message : String(e)}`);
      conn.close();
      if (generation !== this.generation || this.stopped) return;
      this.scheduleRetry();
    }
  }

  private scheduleRetry(): void {
    if (this.stopped) return;
    if (!this.sm.dropped()) {
      this.opts.onExhausted();
      return;
    }
    const delay = this.sm.nextDelayMs();
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      void this.attempt();
    }, delay);
    this.retryTimer.unref?.();
  }
}
