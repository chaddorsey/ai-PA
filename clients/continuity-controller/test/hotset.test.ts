/**
 * subscribeRuntimes against the salvaged mock App Server: worker subscriptions carry
 * `wait_for_replay`, a refused row is reported broken WITHOUT costing the others their
 * subscriptions, and a connection-level fault is a drop, not a broken row.
 */

import { MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import { afterEach, describe, expect, it } from "vitest";
import { subscribeRuntimes } from "../src/hotset.js";

describe("subscribeRuntimes", () => {
  let server: MockAppServer;
  const open: WsConnection[] = [];

  afterEach(async () => {
    for (const ws of open) ws.close();
    open.length = 0;
    await server?.stop();
  });

  async function bare(url: string): Promise<WsConnection> {
    const ws = new WsConnection({ url, versionPolicy: "warn", openTimeoutMs: 2000 });
    open.push(ws);
    await ws.connectBare();
    return ws;
  }

  it("subscribes every row, with wait_for_replay for the worker and WITHOUT it for the anchor", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const rows = [
      { agent_id: "ag-1", conversation_id: "local-conv-1" },
      { agent_id: "ag-1", conversation_id: "local-conv-2" },
    ];

    const worker = await bare(url);
    const workerReport = await subscribeRuntimes(worker, rows, { waitForReplay: true });
    expect(workerReport.subscribed).toHaveLength(2);
    expect(workerReport.broken).toHaveLength(0);

    const anchor = await bare(url);
    const anchorReport = await subscribeRuntimes(anchor, rows, { waitForReplay: false });
    expect(anchorReport.subscribed).toHaveLength(2);

    const hellos = server.received.filter((f) => f.type === "runtime_start");
    // 2 worker (replay-complete) + 2 anchor (bare) — the dual-subscription frames themselves.
    expect(hellos.filter((f) => f.wait_for_replay === true)).toHaveLength(2);
    expect(hellos.filter((f) => f.wait_for_replay === undefined)).toHaveLength(2);
  });

  it("a refused conversation is BROKEN, and the healthy rows still subscribe", async () => {
    server = new MockAppServer({ failRuntimeStartFor: ["local-conv-dead"] });
    const url = await server.start();
    const conn = await bare(url);

    const report = await subscribeRuntimes(
      conn,
      [
        { agent_id: "ag-1", conversation_id: "local-conv-dead" },
        { agent_id: "ag-1", conversation_id: "local-conv-live" },
      ],
      { waitForReplay: true },
    );

    expect(report.broken).toEqual([
      {
        runtime: { agent_id: "ag-1", conversation_id: "local-conv-dead" },
        reason: expect.stringMatching(/not found/),
      },
    ]);
    expect(report.subscribed).toEqual([{ agent_id: "ag-1", conversation_id: "local-conv-live" }]);
  });

  it("a connection-level fault THROWS (a drop) instead of mislabeling healthy rows broken", async () => {
    server = new MockAppServer({ suppressResponsesFor: ["runtime_start"] });
    const url = await server.start();
    const conn = await bare(url);
    await expect(
      subscribeRuntimes(conn, [{ agent_id: "ag-1", conversation_id: "local-conv-1" }], {
        waitForReplay: true,
        timeoutMs: 300,
      }),
    ).rejects.toThrow(/timed out/);
  });
});
