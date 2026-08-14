/**
 * The loopback trust boundary, tested where it is now ENFORCED — in the core.
 *
 * It previously lived only in the terminal's CLI, so `new WsConnection({ url })` would dial
 * anywhere. The core is the published seam and the web client is its next consumer; a check the
 * consumer has to remember to re-implement is one that gets missed.
 */

import { describe, expect, it } from "vitest";
import { TrustBoundaryError, assertLoopbackUrl } from "../src/trust.js";
import { WsConnection } from "../src/ws.js";

const RT = { agent_id: "agent-local-x", conversation_id: "local-conv-1" };

describe("assertLoopbackUrl", () => {
  it("accepts loopback in its usual spellings", () => {
    for (const u of [
      "ws://127.0.0.1:4577/ws",
      "ws://localhost:4577/ws",
      "ws://[::1]:4577/ws",
      // WHATWG normalises these to a loopback hostname before we ever see them.
      "ws://127.1:4577/ws",
      "ws://2130706433:4577/ws",
    ]) {
      expect(() => assertLoopbackUrl(u)).not.toThrow();
    }
  });

  it("refuses a non-loopback host", () => {
    expect(() => assertLoopbackUrl("ws://evil.example/ws")).toThrow(/non-loopback/);
    expect(() => assertLoopbackUrl("ws://10.0.0.5:4577/ws")).toThrow(/non-loopback/);
  });

  it("is not fooled by userinfo that merely LOOKS like loopback", () => {
    // The host here is evil.example; 127.0.0.1 is a username.
    expect(() => assertLoopbackUrl("ws://127.0.0.1@evil.example/ws")).toThrow(/non-loopback/);
  });

  it("refuses a non-ws scheme", () => {
    expect(() => assertLoopbackUrl("http://127.0.0.1:4577/ws")).toThrow(TrustBoundaryError);
  });

  it("honours an explicit opt-out", () => {
    expect(() => assertLoopbackUrl("ws://evil.example/ws", true)).not.toThrow();
  });
});

describe("WsConnection", () => {
  it("refuses to be CONSTRUCTED against a non-loopback peer", () => {
    // The point of the whole finding: enforcement has to sit with the socket, not with one
    // consumer's argument parser. This throws before any network call.
    expect(() => new WsConnection({ url: "ws://evil.example/ws", runtime: RT })).toThrow(
      /non-loopback/,
    );
  });

  it("can still be opted out of deliberately", () => {
    expect(
      () => new WsConnection({ url: "ws://evil.example/ws", runtime: RT, allowRemote: true }),
    ).not.toThrow();
  });
});
