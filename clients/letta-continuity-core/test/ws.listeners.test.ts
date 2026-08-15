/**
 * Listener isolation at the SOCKET seam.
 *
 * Every fan-out in ws.ts runs synchronously inside the socket's `message` (or `close`) handler,
 * so a listener that throws escapes into an EventEmitter and becomes an uncaughtException —
 * which Node's default policy turns into process exit. The terminal's listeners all end in
 * `process.stdout.write`, so `letta-continuity | head -40` killed the client on EPIPE instead of
 * degrading. These are the two channels the facade-level tests cannot reach, because there the
 * only frame and close listeners are the core's own.
 */

import { afterEach, describe, expect, it } from "vitest";
import type { ServerFrame } from "../src/protocol.js";
import { WsConnection } from "../src/ws.js";
import { AGENT, CONV, sleep, waitFor } from "./helpers/harness.js";
import { MockAppServer } from "./helpers/mockServer.js";

const RUNTIME = { agent_id: AGENT, conversation_id: CONV };

describe("WsConnection listener isolation", () => {
  let server: MockAppServer;
  const open: WsConnection[] = [];

  afterEach(async () => {
    for (const ws of open) ws.close();
    open.length = 0;
    await server?.stop();
  });

  async function connect(): Promise<WsConnection> {
    const url = await server.start();
    const ws = new WsConnection({ url, runtime: RUNTIME, openTimeoutMs: 2000 });
    open.push(ws);
    await ws.connect();
    return ws;
  }

  it("a throwing frame listener does not stop the connection delivering frames", async () => {
    server = new MockAppServer();
    const ws = await connect();

    const warnings: string[] = [];
    ws.onFrame(() => {
      throw new Error("EPIPE from a frame listener");
    });
    const survived: ServerFrame[] = [];
    ws.onFrame((f) => survived.push(f));

    server.injectForeignTurn(RUNTIME, "run-1", [
      { id: "letta-msg-1", messageType: "assistant_message", text: "hello" },
    ]);
    await waitFor(() => survived.some((f) => f.type === "turn_finished"), 3000);

    expect(survived.length).toBeGreaterThan(1);
    void warnings;
  });

  it("a throwing close listener does not stop the others learning the socket went away", async () => {
    server = new MockAppServer();
    const ws = await connect();

    ws.onClose(() => {
      throw new Error("EPIPE from a close listener");
    });
    let sawClose = false;
    ws.onClose(() => {
      sawClose = true;
    });

    server.dropAllConnections();
    await waitFor(() => sawClose, 3000);
    expect(sawClose).toBe(true);
  });

  it("a closed connection stops delivering to listeners that have moved on", async () => {
    // A polite close is a handshake, not an instant: this socket keeps receiving until the peer
    // answers, and `ws` waits up to 30s for that. Frames arriving in the meantime belong to a
    // connection the owner has already replaced.
    server = new MockAppServer({ holdFirstConnectionCloseAfter: "runtime_start" });
    const ws = await connect();
    const seen: ServerFrame[] = [];
    ws.onFrame((f) => seen.push(f));

    ws.close();
    server.sendRawTo(0, {
      type: "stream_delta",
      delta: {
        id: "letta-msg-after-close",
        message_type: "assistant_message",
        content: "too late",
        run_id: "run-late",
        type: "message",
      },
      runtime: RUNTIME,
      event_seq: 99,
    });
    await sleep(150);

    expect(seen.filter((f) => JSON.stringify(f).includes("letta-msg-after-close"))).toEqual([]);
  });
});
