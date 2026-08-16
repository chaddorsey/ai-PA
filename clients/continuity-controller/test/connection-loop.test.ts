/**
 * ConnectionLoop: the bounded budget ends in a VISIBLE exhaustion callback (the daemon exits
 * for launchd to restart) — never a silent in-process retry storm.
 */

import { waitFor } from "@ai-pa/letta-continuity-core/testing/harness";
import { describe, expect, it } from "vitest";
import { ConnectionLoop } from "../src/connection-loop.js";

describe("ConnectionLoop", () => {
  it("reports exhaustion after the bounded budget against an unreachable server", async () => {
    let exhausted = false;
    const loop = new ConnectionLoop({
      // A loopback port nothing listens on: every attempt fails fast with ECONNREFUSED.
      url: "ws://127.0.0.1:1/ws",
      onConnected: async () => {},
      onExhausted: () => {
        exhausted = true;
      },
      reconnect: {
        maxReconnectAttempts: 2,
        baseDelayMs: 10,
        maxDelayMs: 20,
        stabilityMs: 0,
        jitter: () => 0,
      },
    });
    await loop.start();
    await waitFor(() => exhausted, 5000);
    expect(loop.state).toBe("disconnected");
    loop.stop();
  });
});
