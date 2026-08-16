/**
 * WorkerDaemon: replay-complete subscriptions, broken rows marked + journaled, the liveness
 * contract (fresh file only after a REAL round-trip; a probe miss bounces the connection), the
 * db-degrade visibility, and the dual-subscription property in both directions.
 */

import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { sleep, waitFor } from "@ai-pa/letta-continuity-core/testing/harness";
import { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import { afterEach, describe, expect, it } from "vitest";
import { AnchorDaemon } from "../src/anchor.js";
import { ReadOnlyRegistry, Registry } from "../src/registry.js";
import { openStateDb, openStateDbReadOnly } from "../src/state/db.js";
import { Journal } from "../src/state/journal.js";
import { WorkerDaemon } from "../src/worker.js";

const FAST_RECONNECT = { baseDelayMs: 20, maxDelayMs: 40, stabilityMs: 0, jitter: () => 0 };

interface Fixture {
  dir: string;
  registry: Registry;
  journal: Journal;
  degraded: string | null;
}

function stateWith(
  rows: Array<{ agent_id: string; conversation_id: string; temp?: "hot" | "cold" }>,
): Fixture {
  const dir = mkdtempSync(join(tmpdir(), "continuity-worker-"));
  const { db, degraded } = openStateDb(dir);
  const registry = new Registry(db);
  for (const row of rows) registry.upsert(row);
  return { dir, registry, journal: new Journal(db), degraded };
}

function makeWorker(
  url: string,
  fixture: Fixture,
  overrides: Partial<ConstructorParameters<typeof WorkerDaemon>[0]> = {},
): WorkerDaemon {
  return new WorkerDaemon({
    url,
    registry: fixture.registry,
    journal: fixture.journal,
    livenessFile: join(fixture.dir, "liveness.json"),
    livenessIntervalMs: 60_000, // probes are driven by start() or explicitly in tests
    livenessDeadlineMs: 500,
    hotsetPollMs: 25,
    degraded: fixture.degraded,
    onExhausted: () => {
      throw new Error("unexpected exhaustion");
    },
    reconnect: FAST_RECONNECT,
    ...overrides,
  });
}

describe("WorkerDaemon", () => {
  let server: MockAppServer;
  let worker: WorkerDaemon | null = null;
  let anchor: AnchorDaemon | null = null;

  afterEach(async () => {
    worker?.stop();
    anchor?.stop();
    worker = null;
    anchor = null;
    await server?.stop();
  });

  it("boot: subscribes exactly the hot rows, replay-complete, and journals the connect", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const fixture = stateWith([
      { agent_id: "ag-1", conversation_id: "local-conv-1" },
      { agent_id: "ag-1", conversation_id: "local-conv-2" },
      { agent_id: "ag-2", conversation_id: "local-conv-3", temp: "cold" },
    ]);
    worker = makeWorker(url, fixture);
    await worker.start();

    expect(worker.held.sort()).toEqual(["ag-1:local-conv-1", "ag-1:local-conv-2"]);
    const hellos = server.received.filter((f) => f.type === "runtime_start");
    expect(hellos).toHaveLength(2);
    // THE journaled subscription: every worker hello is replay-complete.
    expect(hellos.every((f) => f.wait_for_replay === true)).toBe(true);
    expect(fixture.journal.tail().map((r) => r.kind)).toContain("worker_connected");
  });

  it("a refused row is marked broken in the REGISTRY and journaled; the rest stay subscribed", async () => {
    server = new MockAppServer({ failRuntimeStartFor: ["local-conv-dead"] });
    const url = await server.start();
    const fixture = stateWith([
      { agent_id: "ag-1", conversation_id: "local-conv-dead" },
      { agent_id: "ag-1", conversation_id: "local-conv-live" },
    ]);
    worker = makeWorker(url, fixture);
    await worker.start();

    expect(worker.held).toEqual(["ag-1:local-conv-live"]);
    expect(
      fixture.registry.get({ agent_id: "ag-1", conversation_id: "local-conv-dead" })?.broken,
    ).toMatch(/not found/);
    expect(fixture.journal.tail().map((r) => r.kind)).toContain("registry_row_broken");
  });

  it("liveness: the file is fresh ONLY after a real sync round-trip, and carries `degraded`", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const fixture = stateWith([{ agent_id: "ag-1", conversation_id: "local-conv-1" }]);
    worker = makeWorker(url, fixture);
    await worker.start(); // start() runs one immediate probe

    const livenessPath = join(fixture.dir, "liveness.json");
    expect(existsSync(livenessPath)).toBe(true);
    const liveness = JSON.parse(readFileSync(livenessPath, "utf8"));
    expect(liveness.state).toBe("connected");
    expect(liveness.hot).toBe(1);
    expect(liveness.degraded).toBeNull();
    // The probe was a REAL sync RPC, not bookkeeping.
    expect(server.received.some((f) => f.type === "sync")).toBe(true);
  });

  it("a liveness probe MISS bounces the connection (reconnect observed) and writes no fresh file", async () => {
    server = new MockAppServer({ suppressResponsesFor: ["sync"] });
    const url = await server.start();
    const fixture = stateWith([{ agent_id: "ag-1", conversation_id: "local-conv-1" }]);
    worker = makeWorker(url, fixture);
    await worker.start(); // immediate probe times out (500ms) → bounce

    await waitFor(
      () => server.received.filter((f) => f.type === "runtime_start").length >= 2,
      5000,
    );
    expect(existsSync(join(fixture.dir, "liveness.json"))).toBe(false);
    expect(fixture.journal.tail().map((r) => r.kind)).toContain("liveness_probe_failed");
  });

  it("a hotset change subscribes the new runtime and journals the anchor-lag exposure", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const fixture = stateWith([{ agent_id: "ag-1", conversation_id: "local-conv-1" }]);
    worker = makeWorker(url, fixture);
    await worker.start();

    fixture.registry.upsert({ agent_id: "ag-2", conversation_id: "local-conv-2" });
    await waitFor(() => worker?.held.includes("ag-2:local-conv-2") ?? false, 2000);
    const kinds = fixture.journal.tail().map((r) => r.kind);
    expect(kinds).toContain("hotset_changed");
  });

  it("a degraded state db is journaled at boot — the rebuilt authority is never silent", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const fixture = stateWith([]);
    fixture.degraded =
      "integrity_check failed; damaged db preserved at …; starting with a REBUILT (empty) authority";
    worker = makeWorker(url, fixture);
    await worker.start();

    const row = fixture.journal.tail().find((r) => r.kind === "state_db_degraded");
    expect(row?.payload.detail).toMatch(/REBUILT/);
    const liveness = JSON.parse(readFileSync(join(fixture.dir, "liveness.json"), "utf8"));
    expect(liveness.degraded).toMatch(/REBUILT/);
  });

  it("DUAL SUBSCRIPTION: deltas flow to the worker with the anchor absent, and vice versa", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const fixture = stateWith([{ agent_id: "ag-1", conversation_id: "local-conv-1" }]);
    const runtime = { agent_id: "ag-1", conversation_id: "local-conv-1" };

    const workerFrames: string[] = [];
    worker = makeWorker(url, fixture, {
      makeConnection: (u, onWarn) => {
        const conn = new WsConnection({ url: u, versionPolicy: "warn", onWarn });
        conn.onFrame((f) => workerFrames.push(f.type));
        return conn;
      },
    });
    const anchorFrames: string[] = [];
    anchor = new AnchorDaemon({
      url,
      registry: new ReadOnlyRegistry(openStateDbReadOnly(fixture.dir)),
      hotsetPollMs: 25,
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
      reconnect: FAST_RECONNECT,
      makeConnection: (u, onWarn) => {
        const conn = new WsConnection({ url: u, versionPolicy: "warn", onWarn });
        conn.onFrame((f) => anchorFrames.push(f.type));
        return conn;
      },
    });
    await worker.start();
    await anchor.start();
    expect(server.connectionCount).toBe(2);

    // Anchor ABSENT → the worker still receives the runtime's frames.
    anchor.stop();
    await waitFor(() => server.connectionCount === 1, 2000);
    server.broadcastTurn(runtime, "run-worker-only", [
      { id: "m-1", messageType: "assistant_message", text: "to-worker" },
    ]);
    await waitFor(() => workerFrames.includes("turn_finished"), 2000);

    // Worker ABSENT → the anchor still receives them (this is what holds detached turns).
    anchorFrames.length = 0;
    await anchor.start();
    await waitFor(() => server.connectionCount === 2, 2000);
    worker.stop();
    await waitFor(() => server.connectionCount === 1, 2000);
    server.broadcastTurn(runtime, "run-anchor-only", [
      { id: "m-2", messageType: "assistant_message", text: "to-anchor" },
    ]);
    await waitFor(() => anchorFrames.includes("turn_finished"), 2000);
    await sleep(10);
  });
});
