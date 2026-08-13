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
});
