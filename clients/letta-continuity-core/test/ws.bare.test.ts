/**
 * The controller-facing seam of WsConnection: `connectBare()` (no hello, many runtimes later)
 * must keep every guarantee `connect()` had — the version gate above all — and the mock must
 * keep the real server's N-subscriptions-per-socket behaviour (C1 spike S6), because the
 * controller's anchor/worker sockets are built on exactly that.
 */

import { afterEach, describe, expect, it } from "vitest";
import { Outbound, ProtocolError, buildRuntimeStart } from "../src/protocol.js";
import { WsConnection } from "../src/ws.js";
import { waitFor } from "./helpers/harness.js";
import { MockAppServer } from "./helpers/mockServer.js";

describe("WsConnection.connectBare", () => {
  let server: MockAppServer;
  const open: WsConnection[] = [];

  afterEach(async () => {
    for (const ws of open) ws.close();
    open.length = 0;
    await server?.stop();
  });

  it("still runs the version gate: a drifted server is REFUSED before any runtime exists", async () => {
    server = new MockAppServer({ driftAppServerInfo: true });
    const url = await server.start();
    const ws = new WsConnection({ url, versionPolicy: "refuse", openTimeoutMs: 2000 });
    open.push(ws);
    await expect(ws.connectBare()).rejects.toThrow(/refusing to attach/);
  });

  it("subscribes N runtimes on ONE bare socket and receives broadcasts for the FIRST after a second hello", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const ws = new WsConnection({ url, versionPolicy: "warn", openTimeoutMs: 2000 });
    open.push(ws);
    const seen: string[] = [];
    ws.onFrame((f) => {
      if (f.type === "turn_finished") seen.push(JSON.stringify(f.runtime));
    });
    await ws.connectBare();

    const first = { agent_id: "ag-1", conversation_id: "local-conv-1" };
    const second = { agent_id: "ag-2", conversation_id: "local-conv-2" };
    for (const runtime of [first, second]) {
      const resp = await ws.request(
        (rid) => buildRuntimeStart(rid, runtime),
        Outbound.runtimeStart,
      );
      expect(resp.success).toBe(true);
    }

    // A later hello ADDS a subscription — it must not re-home the socket off the first runtime.
    server.broadcastTurn(first, "run-multi", [
      { id: "m-1", messageType: "assistant_message", text: "to-first" },
    ]);
    await waitFor(() => seen.length > 0, 2000);
    expect(seen[0]).toContain("local-conv-1");
  });

  it("connect() without a runtime fails loudly instead of sending a malformed hello", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const ws = new WsConnection({ url, versionPolicy: "warn", openTimeoutMs: 2000 });
    open.push(ws);
    await expect(ws.connect()).rejects.toThrow(ProtocolError);
  });
});
