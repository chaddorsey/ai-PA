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

  it("connected() resets the reconnect attempt budget", () => {
    const m = new ConnectionStateMachine({ maxReconnectAttempts: 1 });
    m.connecting();
    m.connected();
    expect(m.dropped()).toBe(true);
    m.connected(); // recovered
    expect(m.reconnectAttempts).toBe(0);
    expect(m.dropped()).toBe(true); // budget available again
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

    it("a successful connect resets the schedule", () => {
      const m = new ConnectionStateMachine({ jitter: () => 1, baseDelayMs: 500 });
      m.dropped();
      m.dropped();
      expect(m.nextDelayMs()).toBe(1000);
      m.connected();
      m.dropped();
      expect(m.nextDelayMs()).toBe(500);
    });
  });
});
