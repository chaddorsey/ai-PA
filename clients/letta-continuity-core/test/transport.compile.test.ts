/**
 * The seam Unit 6 has to build against — proven by IMPLEMENTING it, not by describing it.
 *
 * `createConnection` was typed to the concrete `WsConnection`, whose eight private members make
 * its type NOMINAL: only that class or a subclass could satisfy it, and a subclass drags the
 * Node-only `ws` package into whatever imports it. The seam's own doc-comment said its purpose was
 * that "M1 Unit 6's browser client cannot use the `ws` package and will need to supply its own
 * implementation of the same surface" — and that was false. A scratch browser transport failed to
 * compile against it (TS2322). Half the seam's stated reason for existing did not work, and the
 * discovery would have fallen to Unit 6, mid-build, against a design decision already made.
 *
 * So this file is mostly a COMPILE-TIME assertion. `BrowserishTransport` below imports nothing
 * from `ws`, names no `Buffer` and no `RawData`, and is handed to `ContinuityCore` through the
 * real config type. If the seam ever narrows back to something only a Node class can satisfy,
 * `npm run typecheck` fails here — which is a gate Unit 6 cannot forget to run, unlike a comment.
 *
 * The runtime assertions are deliberately thin: this is not a test of the fake. The tests that
 * exercise a substituted transport for BEHAVIOUR are trust.test.ts (the loopback boundary) and
 * FaultyWsConnection (injected write faults).
 */

import { describe, expect, it } from "vitest";
import { ContinuityCore } from "../src/index.js";
import type { RuntimeStartResponseFrame, ServerFrame } from "../src/protocol.js";
import type { ContinuityTransport } from "../src/ws.js";

/**
 * A transport of the kind Unit 6 will actually write.
 *
 * Note what is NOT here: no `import { WebSocket } from "ws"`, no `Buffer`, no `RawData`. Every
 * member is expressible against the browser's own `WebSocket` and `MessageEvent`. That absence is
 * the assertion — the class body is only as complete as it needs to be to typecheck.
 */
class BrowserishTransport implements ContinuityTransport {
  private closed = false;
  private closedDeliberately = false;
  readonly sent: ServerFrame[] = [];

  onFrame(_cb: (frame: ServerFrame) => void): () => void {
    return () => {};
  }
  onError(_cb: (err: Error) => void): () => void {
    return () => {};
  }
  onClose(_cb: (code: number, reason: string) => void): () => void {
    return () => {};
  }
  async connect(): Promise<RuntimeStartResponseFrame> {
    return {
      type: "runtime_start_response",
      request_id: "rpc-browserish-1",
      success: true,
      runtime: { agent_id: "agent-local-x", conversation_id: "local-conv-1" },
    } as RuntimeStartResponseFrame;
  }
  async request<T extends ServerFrame = ServerFrame>(
    build: (requestId: string) => ServerFrame,
    _requestType: string,
    _timeoutMs?: number,
  ): Promise<T> {
    return build("rpc-browserish-2") as T;
  }
  send(frame: ServerFrame): void {
    this.sent.push(frame);
  }
  close(): void {
    this.closed = true;
    this.closedDeliberately = true;
  }
  get isClosedByUs(): boolean {
    return this.closedDeliberately;
  }
  get isClosed(): boolean {
    return this.closed;
  }
}

describe("the transport seam is implementable without `ws`", () => {
  it("accepts a transport built from nothing but the interface", () => {
    // The real assertion is that this file COMPILES. Before the seam was re-typed, this
    // assignment was a TS2322 — `ContinuityTransport` is missing `socket`, `pending`,
    // `frameListeners`, and 14 more private members of `WsConnection`.
    const transport = new BrowserishTransport();
    const core = new ContinuityCore({
      pointer: { agentId: "agent-local-x", conversationId: "local-conv-1" },
      url: "ws://127.0.0.1:4577/ws",
      createConnection: () => transport,
    });

    expect(core).toBeInstanceOf(ContinuityCore);
    core.stop();
  });

  it("is satisfied by the Node implementation too, so the two cannot drift", async () => {
    // `WsConnection implements ContinuityTransport` is declared in ws.ts; this is the use site
    // that makes the declaration load-bearing rather than decorative.
    const { WsConnection } = await import("../src/ws.js");
    const asTransport: (o: ConstructorParameters<typeof WsConnection>[0]) => ContinuityTransport = (
      o,
    ) => new WsConnection(o);
    expect(typeof asTransport).toBe("function");
  });
});
