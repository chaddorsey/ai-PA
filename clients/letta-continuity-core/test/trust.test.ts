/**
 * The loopback trust boundary, tested where it is now ENFORCED — in the core.
 *
 * It previously lived only in the terminal's CLI, so `new WsConnection({ url })` would dial
 * anywhere. The core is the published seam and the web client is its next consumer; a check the
 * consumer has to remember to re-implement is one that gets missed.
 */

import { describe, expect, it } from "vitest";
import { ContinuityCore } from "../src/index.js";
import { TrustBoundaryError, assertLoopbackUrl, assertTailnetOrLoopbackUrl } from "../src/trust.js";
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

describe("assertTailnetOrLoopbackUrl", () => {
  it("always accepts loopback, either scheme", () => {
    expect(() => assertTailnetOrLoopbackUrl("ws://127.0.0.1:4610/surface")).not.toThrow();
    expect(() => assertTailnetOrLoopbackUrl("wss://localhost:4610/surface")).not.toThrow();
  });

  it("accepts tailnet destinations over wss only", () => {
    expect(() =>
      assertTailnetOrLoopbackUrl("wss://dorseys-mac-mini.tailf9b999.ts.net/pa/surface"),
    ).not.toThrow();
    expect(() => assertTailnetOrLoopbackUrl("wss://100.99.171.119:4610/surface")).not.toThrow();
    expect(() =>
      assertTailnetOrLoopbackUrl("ws://dorseys-mac-mini.tailf9b999.ts.net/pa/surface"),
    ).toThrow(/wss/);
  });

  it("refuses non-tailnet hosts — this is not a general remote escape hatch", () => {
    expect(() => assertTailnetOrLoopbackUrl("wss://evil.example/surface")).toThrow(/non-tailnet/);
    // 100.x outside the CGNAT /10 is NOT a tailnet address.
    expect(() => assertTailnetOrLoopbackUrl("wss://100.128.0.1/surface")).toThrow(/non-tailnet/);
    expect(() => assertTailnetOrLoopbackUrl("wss://100.63.255.255/surface")).toThrow(/non-tailnet/);
    // A .ts.net LABEL inside another domain must not pass.
    expect(() => assertTailnetOrLoopbackUrl("wss://x.ts.net.evil.example/surface")).toThrow(
      /non-tailnet/,
    );
    // Userinfo that merely looks tailnet-ish: the real host is evil.example.
    expect(() => assertTailnetOrLoopbackUrl("wss://a.ts.net@evil.example/surface")).toThrow(
      /non-tailnet/,
    );
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

describe("ContinuityCore enforces the boundary itself, not via the transport", () => {
  // The check lived ONLY inside `WsConnection` — which is exactly the class `createConnection`
  // exists to replace. So any consumer supplying a transport bypassed the boundary entirely, and
  // the M1 Unit 6 browser client is precisely such a consumer. On a server with NO client
  // authentication, loopback is the whole of the access control, so it cannot be delegated to a
  // component the caller is invited to swap out.
  //
  // Driven through a substituted transport ON PURPOSE: with the real `WsConnection` these would
  // pass whether or not the core checked anything, which is how the gap stayed invisible.
  function coreWithSubstituteTransport(url: string, allowRemote?: boolean): ContinuityCore {
    return new ContinuityCore({
      pointer: { agentId: RT.agent_id, conversationId: RT.conversation_id },
      url,
      ...(allowRemote === undefined ? {} : { allowRemote }),
      // A transport that would happily dial anywhere. If the core does not check, nothing does.
      createConnection: () => {
        throw new Error("the transport was reached — the boundary was NOT enforced by the core");
      },
    });
  }

  it("refuses a non-loopback URL before the transport factory is called", async () => {
    const core = coreWithSubstituteTransport("ws://evil.example/ws");
    await expect(core.start()).rejects.toThrow(/non-loopback/);
    core.stop();
  });

  it("still honours an explicit allowRemote opt-out", async () => {
    // The other half: the boundary must be a gate, not a wall. This reaches the factory, which
    // proves the check passed rather than that it merely failed differently.
    const core = coreWithSubstituteTransport("ws://evil.example/ws", true);
    await expect(core.start()).rejects.toThrow(/the transport was reached/);
    core.stop();
  });
});
