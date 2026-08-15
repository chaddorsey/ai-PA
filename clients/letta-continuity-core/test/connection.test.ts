import { describe, expect, it } from "vitest";
import { type ConnectionState, ConnectionStateMachine } from "../src/connection.js";

describe("ConnectionStateMachine", () => {
  it("transitions connecting → connected and notifies listeners", () => {
    const m = new ConnectionStateMachine();
    const seen: ConnectionState[] = [];
    m.onChange((s) => seen.push(s));
    m.connecting();
    m.connected();
    expect(seen).toEqual(["connecting", "connected"]);
    expect(m.current).toBe("connected");
  });

  it("dropped() → reconnecting while within budget, disconnected when exhausted", () => {
    const m = new ConnectionStateMachine({ maxReconnectAttempts: 2 });
    m.connecting();
    m.connected();
    expect(m.dropped()).toBe(true); // attempt 1
    expect(m.current).toBe("reconnecting");
    expect(m.dropped()).toBe(true); // attempt 2
    expect(m.dropped()).toBe(false); // budget exhausted → bounded, no infinite loop
    expect(m.current).toBe("disconnected");
  });

  /**
   * PROPERTY CHANGED, deliberately. `connected()` used to restore the budget the instant a hello
   * completed, which made the bound unenforceable against the exact shape it exists for: a server
   * that accepts the socket, answers every RPC, and dies seconds later rearmed it on every cycle.
   * A recovery is now a connection that SURVIVES, not one that merely opens.
   */
  it("a recovered connection restores the budget once it has proven itself", async () => {
    const m = new ConnectionStateMachine({ maxReconnectAttempts: 2, stabilityMs: 30 });
    m.connecting();
    m.connected();
    expect(m.dropped()).toBe(true);

    m.connected(); // reattached, but zero seconds old
    expect(m.reconnectAttempts).toBe(1);

    await new Promise((r) => setTimeout(r, 60));
    expect(m.reconnectAttempts).toBe(0);
    expect(m.dropped()).toBe(true);
  });

  it("a connection that dies inside the stability window spends budget instead of restoring it", async () => {
    const m = new ConnectionStateMachine({ maxReconnectAttempts: 2, stabilityMs: 10_000 });
    m.connecting();
    m.connected();
    expect(m.dropped()).toBe(true); // attempt 1
    m.connected();
    expect(m.dropped()).toBe(true); // attempt 2 — the flap did NOT count as a recovery
    expect(m.dropped()).toBe(false); // exhausted, as it must be
    expect(m.current).toBe("disconnected");
  });

  it("no duplicate notifications for same-state transitions", () => {
    const m = new ConnectionStateMachine();
    const seen: ConnectionState[] = [];
    m.onChange((s) => seen.push(s));
    m.connecting();
    m.connecting();
    expect(seen).toEqual(["connecting"]);
  });

  describe("reconnect schedule (sized for a real App Server restart)", () => {
    // The old defaults — 5 attempts at a fixed 1s — expired in ~5s, less than a `letta server`
    // boot, leaving the client permanently disconnected while still accepting input.
    it("backs off exponentially up to a cap", () => {
      const m = new ConnectionStateMachine({ jitter: () => 1, baseDelayMs: 500, maxDelayMs: 4000 });
      const delays: number[] = [];
      for (let i = 0; i < 6; i += 1) {
        m.dropped();
        delays.push(m.nextDelayMs());
      }
      expect(delays).toEqual([500, 1000, 2000, 4000, 4000, 4000]);
    });

    it("applies jitter, so simultaneously-dropped surfaces do not retry in lockstep", () => {
      // A watchdog restart drops EVERY attached client at once; a deterministic schedule would
      // point them all at a cold-starting server at the same instant.
      const low = new ConnectionStateMachine({ jitter: () => 0, baseDelayMs: 1000 });
      const high = new ConnectionStateMachine({ jitter: () => 1, baseDelayMs: 1000 });
      low.dropped();
      high.dropped();
      expect(low.nextDelayMs()).toBe(500); // full-jitter floor
      expect(high.nextDelayMs()).toBe(1000);
      expect(low.nextDelayMs()).toBeLessThan(high.nextDelayMs());
    });

    it("the default budget spans well past a server boot", () => {
      const m = new ConnectionStateMachine({ jitter: () => 1 });
      let total = 0;
      let attempts = 0;
      while (m.dropped()) {
        total += m.nextDelayMs();
        attempts += 1;
      }
      expect(attempts).toBeGreaterThanOrEqual(10);
      expect(total).toBeGreaterThan(60_000); // > a minute of retrying, vs ~5s before
    });

    it("a connection that lasts resets the schedule", async () => {
      const m = new ConnectionStateMachine({ jitter: () => 1, baseDelayMs: 500, stabilityMs: 20 });
      m.dropped();
      m.dropped();
      expect(m.nextDelayMs()).toBe(1000);
      m.connected();
      await new Promise((r) => setTimeout(r, 50));
      m.dropped();
      expect(m.nextDelayMs()).toBe(500);
    });
  });
});
