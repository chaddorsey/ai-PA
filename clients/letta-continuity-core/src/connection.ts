/**
 * connection.ts — connection-state machine (connected / reconnecting / disconnected).
 *
 * Pure and UI-facing: ws.ts drives it with lifecycle events; the facade and clients
 * subscribe to render "reconnecting…" (R17). Reconnect is BOUNDED — a max number of attempts,
 * no unbounded retry loop — but the budget and the delay schedule are sized for the event that
 * actually causes reconnects: the App Server watchdog killing and restarting the runtime.
 *
 * The previous defaults (5 attempts, fixed 1s, no jitter) expired in about five seconds — less
 * than a `letta server` boot — after which the client sat permanently disconnected while still
 * accepting input. And because a watchdog restart drops EVERY surface at once, a fixed delay put
 * all of them in lockstep against a cold-starting server.
 */

export type ConnectionState = "disconnected" | "connecting" | "connected" | "reconnecting";

export type ConnectionListener = (state: ConnectionState, prev: ConnectionState) => void;

export interface ReconnectPolicy {
  maxReconnectAttempts?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  /** Returns [0,1). Injectable so the jitter is testable rather than flaky. */
  jitter?: () => number;
}

/**
 * Sized for a real `letta server` restart rather than a transient blip. Ten attempts backing off
 * from 500ms to a 15s cap spans roughly two minutes — comfortably longer than a boot, while the
 * growing delay keeps it storm-safe.
 */
const DEFAULT_MAX_ATTEMPTS = 10;
const DEFAULT_BASE_DELAY_MS = 500;
const DEFAULT_MAX_DELAY_MS = 15_000;

export class ConnectionStateMachine {
  private state: ConnectionState = "disconnected";
  private attempts = 0;
  private readonly listeners = new Set<ConnectionListener>();
  private readonly maxReconnectAttempts: number;

  private readonly baseDelayMs: number;
  private readonly maxDelayMs: number;
  private readonly jitter: () => number;

  constructor(opts: ReconnectPolicy = {}) {
    this.maxReconnectAttempts = opts.maxReconnectAttempts ?? DEFAULT_MAX_ATTEMPTS;
    this.baseDelayMs = opts.baseDelayMs ?? DEFAULT_BASE_DELAY_MS;
    this.maxDelayMs = opts.maxDelayMs ?? DEFAULT_MAX_DELAY_MS;
    // Injectable so the jitter is testable: with Math.random the schedule assertion would be
    // either flaky or vacuous.
    this.jitter = opts.jitter ?? Math.random;
  }

  /**
   * Delay before the attempt that has just been permitted by `dropped()`.
   *
   * Exponential with full jitter. Jitter is not decoration here — a watchdog restart drops every
   * attached surface simultaneously, so a deterministic schedule reconnects them in lockstep.
   */
  nextDelayMs(): number {
    const exponential = Math.min(
      this.maxDelayMs,
      this.baseDelayMs * 2 ** Math.max(0, this.attempts - 1),
    );
    return Math.round(exponential * (0.5 + this.jitter() * 0.5));
  }

  get current(): ConnectionState {
    return this.state;
  }

  get reconnectAttempts(): number {
    return this.attempts;
  }

  onChange(listener: ConnectionListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private transition(next: ConnectionState): void {
    if (next === this.state) return;
    const prev = this.state;
    this.state = next;
    for (const l of this.listeners) l(next, prev);
  }

  /** Initial connect attempt starting from disconnected. */
  connecting(): void {
    this.transition("connecting");
  }

  /** Socket opened and hello succeeded. */
  connected(): void {
    this.attempts = 0;
    this.transition("connected");
  }

  /**
   * Socket dropped. Returns true if another (bounded) reconnect attempt is permitted,
   * false if the attempt budget is exhausted (→ disconnected).
   */
  dropped(): boolean {
    if (this.attempts >= this.maxReconnectAttempts) {
      this.transition("disconnected");
      return false;
    }
    this.attempts += 1;
    this.transition("reconnecting");
    return true;
  }

  /** Give up / explicit close. */
  disconnected(): void {
    this.transition("disconnected");
  }
}
