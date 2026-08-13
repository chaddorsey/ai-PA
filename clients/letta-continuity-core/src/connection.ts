/**
 * connection.ts — connection-state machine (connected / reconnecting / disconnected).
 *
 * Pure and UI-facing: ws.ts drives it with lifecycle events; the facade and clients
 * subscribe to render "reconnecting…" (R17). Reconnect is BOUNDED — a fixed max number
 * of attempts, no unbounded retry loop.
 */

export type ConnectionState = "disconnected" | "connecting" | "connected" | "reconnecting";

export type ConnectionListener = (state: ConnectionState, prev: ConnectionState) => void;

export class ConnectionStateMachine {
  private state: ConnectionState = "disconnected";
  private attempts = 0;
  private readonly listeners = new Set<ConnectionListener>();
  private readonly maxReconnectAttempts: number;

  constructor(opts: { maxReconnectAttempts?: number } = {}) {
    this.maxReconnectAttempts = opts.maxReconnectAttempts ?? 5;
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
