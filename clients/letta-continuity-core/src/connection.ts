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

import { fanOut } from "./fanout.js";

export type ConnectionState = "disconnected" | "connecting" | "connected" | "reconnecting";

export type ConnectionListener = (state: ConnectionState, prev: ConnectionState) => void;

export interface ReconnectPolicy {
  maxReconnectAttempts?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  /** Returns [0,1). Injectable so the jitter is testable rather than flaky. */
  jitter?: () => number;
  /**
   * How long a connection must SURVIVE before it counts as a recovery and restores the budget.
   *
   * Resetting the counter the instant a hello completes is no budget at all. A server that
   * accepts the socket, answers every RPC, and then dies rearms it on every cycle, so backoff
   * never grows and the cap is never reached — measured at 81 handshakes against a budget of 2.
   * That is precisely the crash-loop the bound exists for, and the client hammers the recovering
   * server through it while showing the user "connected".
   *
   * Defaults to `DEFAULT_STABILITY_MS`, INDEPENDENTLY of the delay schedule.
   *
   * It used to default to `maxDelayMs`, which coupled the crash-loop guard to a knob that means
   * something else entirely. `ContinuityCore` maps its `reconnectDelayMs` onto both `baseDelayMs`
   * and `maxDelayMs`, so a consumer tuning the retry delay silently shrank the guard — and every
   * test in this suite sets `reconnectDelayMs: 20`, so the whole suite ran a 20ms stability window
   * and the real default was executed by exactly zero tests. Tie it to nothing: "long enough to
   * count as a recovery" is not the same question as "how long before retrying".
   */
  stabilityMs?: number;
}

/**
 * Sized for a real `letta server` restart rather than a transient blip. Ten attempts backing off
 * from 500ms to a 15s cap spans roughly two minutes — comfortably longer than a boot, while the
 * growing delay keeps it storm-safe.
 */
const DEFAULT_MAX_ATTEMPTS = 10;
const DEFAULT_BASE_DELAY_MS = 500;
const DEFAULT_MAX_DELAY_MS = 15_000;
/**
 * How long a connection must survive to count as a recovery rather than an attempt.
 *
 * Numerically the same as the delay cap and deliberately a SEPARATE constant: they answer
 * different questions and must be free to diverge. The value remains reasoned rather than
 * measured — it is "about as long as a `letta server` boot" — and a live watchdog-restart profile
 * would settle it. Recorded as an accepted open risk rather than presented as a measured figure.
 */
const DEFAULT_STABILITY_MS = 15_000;

export class ConnectionStateMachine {
  private state: ConnectionState = "disconnected";
  private attempts = 0;
  private readonly listeners = new Set<ConnectionListener>();
  private readonly maxReconnectAttempts: number;

  private readonly baseDelayMs: number;
  private readonly maxDelayMs: number;
  private readonly jitter: () => number;
  private readonly stabilityMs: number;
  /** Pending "this connection has survived long enough to count" timer. */
  private stabilityTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(opts: ReconnectPolicy = {}) {
    this.maxReconnectAttempts = opts.maxReconnectAttempts ?? DEFAULT_MAX_ATTEMPTS;
    this.baseDelayMs = opts.baseDelayMs ?? DEFAULT_BASE_DELAY_MS;
    this.maxDelayMs = opts.maxDelayMs ?? DEFAULT_MAX_DELAY_MS;
    this.stabilityMs = opts.stabilityMs ?? DEFAULT_STABILITY_MS;
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
    fanOut(this.listeners, [next, prev]);
  }

  /** Initial connect attempt starting from disconnected. */
  connecting(): void {
    this.transition("connecting");
  }

  /**
   * Socket opened and hello succeeded.
   *
   * The budget is NOT restored here. It is restored once this connection has survived
   * `stabilityMs` — see the field. A connection that dies before then was an attempt, not a
   * recovery, and must count against the bound like any other.
   */
  connected(): void {
    this.armStability();
    this.transition("connected");
  }

  /**
   * Socket dropped. Returns true if another (bounded) reconnect attempt is permitted,
   * false if the attempt budget is exhausted (→ disconnected).
   */
  dropped(): boolean {
    this.cancelStability();
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
    this.cancelStability();
    this.attempts = 0;
    this.transition("disconnected");
  }

  private armStability(): void {
    this.cancelStability();
    if (this.stabilityMs <= 0) {
      this.attempts = 0;
      return;
    }
    this.stabilityTimer = setTimeout(() => {
      this.stabilityTimer = null;
      this.attempts = 0;
    }, this.stabilityMs);
    this.stabilityTimer.unref?.();
  }

  private cancelStability(): void {
    if (!this.stabilityTimer) return;
    clearTimeout(this.stabilityTimer);
    this.stabilityTimer = null;
  }
}
