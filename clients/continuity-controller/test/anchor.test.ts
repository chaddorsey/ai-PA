/**
 * AnchorDaemon: subscribes the hot set read-only, follows hotset_version bumps, re-attains its
 * subscriptions after a drop, and actually RECEIVES broadcasts (a subscription that does not
 * deliver frames is not a subscription).
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { sleep, waitFor } from "@ai-pa/letta-continuity-core/testing/harness";
import { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import { afterEach, describe, expect, it } from "vitest";
import { AnchorDaemon } from "../src/anchor.js";
import { ReadOnlyRegistry, Registry } from "../src/registry.js";
import { openStateDb, openStateDbReadOnly } from "../src/state/db.js";

const FAST_RECONNECT = { baseDelayMs: 20, maxDelayMs: 40, stabilityMs: 0, jitter: () => 0 };

describe("AnchorDaemon", () => {
  let server: MockAppServer;
  let anchor: AnchorDaemon | null = null;

  afterEach(async () => {
    anchor?.stop();
    anchor = null;
    await server?.stop();
  });

  function stateWithHotRows(rows: Array<{ agent_id: string; conversation_id: string }>) {
    const dir = mkdtempSync(join(tmpdir(), "continuity-anchor-"));
    const { db } = openStateDb(dir);
    const registry = new Registry(db);
    for (const row of rows) registry.upsert(row);
    return { dir, registry, readOnly: new ReadOnlyRegistry(openStateDbReadOnly(dir)) };
  }

  it("subscribes every hot row at start and follows a hotset_version bump within one poll", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const { registry, readOnly } = stateWithHotRows([
      { agent_id: "ag-1", conversation_id: "local-conv-1" },
    ]);

    anchor = new AnchorDaemon({
      url,
      registry: readOnly,
      hotsetPollMs: 25,
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
      reconnect: FAST_RECONNECT,
    });
    await anchor.start();
    expect(anchor.held).toEqual(["ag-1:local-conv-1"]);

    // The worker's half of the signal: a registry write bumps hotset_version; the read-only
    // anchor notices without any IPC.
    registry.upsert({ agent_id: "ag-2", conversation_id: "local-conv-2" });
    await waitFor(() => anchor?.held.includes("ag-2:local-conv-2") ?? false, 2000);
    expect(anchor?.held).toHaveLength(2);
  });

  it("re-attains its subscriptions after the server drops it (crash-overlap survives restarts)", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const port = Number(new URL(url).port);
    const { readOnly } = stateWithHotRows([{ agent_id: "ag-1", conversation_id: "local-conv-1" }]);

    anchor = new AnchorDaemon({
      url,
      registry: readOnly,
      hotsetPollMs: 25,
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
      reconnect: FAST_RECONNECT,
    });
    await anchor.start();
    const hellosBefore = server.received.filter((f) => f.type === "runtime_start").length;

    server.dropAllConnections();
    await sleep(30);
    await waitFor(
      () => server.received.filter((f) => f.type === "runtime_start").length > hellosBefore,
      3000,
    );
    expect(anchor.held).toEqual(["ag-1:local-conv-1"]);
    void port;
  });

  it("receives broadcasts for a held runtime — the subscription is real, not bookkeeping", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const { readOnly } = stateWithHotRows([{ agent_id: "ag-1", conversation_id: "local-conv-1" }]);

    // Tap the anchor's OWN socket via the injection seam — the daemon stays near-zero-logic,
    // the test still proves frames arrive on it.
    const seen: string[] = [];
    anchor = new AnchorDaemon({
      url,
      registry: readOnly,
      hotsetPollMs: 25,
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
      reconnect: FAST_RECONNECT,
      makeConnection: (u, onWarn) => {
        const conn = new WsConnection({ url: u, versionPolicy: "warn", onWarn });
        conn.onFrame((f) => seen.push(f.type));
        return conn;
      },
    });
    await anchor.start();

    server.broadcastTurn({ agent_id: "ag-1", conversation_id: "local-conv-1" }, "run-x", [
      { id: "m-1", messageType: "assistant_message", text: "held" },
    ]);
    await waitFor(() => seen.includes("turn_finished"), 2000);
    expect(seen).toContain("stream_delta");
  });
});
