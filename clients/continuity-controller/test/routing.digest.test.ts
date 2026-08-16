/**
 * The Kinara digest (C8/R24): a completed direct exchange becomes a digest row for its
 * route-origin thread; the sweep delivers ONE batched muted turn — never while an operator
 * message is pending for that runtime, never fanned out, never badging anyone, and never
 * silently dropped (undelivered rows survive to the next sweep).
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { waitFor } from "@ai-pa/letta-continuity-core/testing/harness";
import { afterEach, describe, expect, it } from "vitest";
import { TurnJournal } from "../src/journal.js";
import { Registry } from "../src/registry.js";
import { openStateDb } from "../src/state/db.js";
import { Journal } from "../src/state/journal.js";
import { ensureSurfaceToken } from "../src/surface/auth.js";
import { WorkerDaemon } from "../src/worker.js";
import { TestSurface } from "./helpers/surfaceClient.js";

const FAST_RECONNECT = { baseDelayMs: 20, maxDelayMs: 40, stabilityMs: 0, jitter: () => 0 };
const KINARA = { agent_id: "ag-kinara", conversation_id: "local-conv-k" };
const KINARA_B = { agent_id: "ag-kinara", conversation_id: "local-conv-k2" };
const CAL = { agent_id: "ag-calendar", conversation_id: "local-conv-cal" };

interface Stack {
  worker: WorkerDaemon;
  server: MockAppServer;
  surfacePort: number;
  token: string;
  turnJournal: TurnJournal;
  db: ReturnType<typeof openStateDb>["db"];
}

describe("Kinara digest", () => {
  let stack: Stack | null = null;
  const surfaces: TestSurface[] = [];

  afterEach(async () => {
    for (const s of surfaces) s.close();
    surfaces.length = 0;
    stack?.worker.stop();
    await stack?.server.stop();
    stack = null;
  });

  async function startStack(): Promise<Stack> {
    const server = new MockAppServer();
    const url = await server.start();
    const dir = mkdtempSync(join(tmpdir(), "continuity-digest-"));
    const { db } = openStateDb(dir);
    const registry = new Registry(db);
    registry.upsert({ ...KINARA, label: "kinara", origin: { default: true } });
    registry.upsert({ ...KINARA_B, label: "kinara-b" });
    registry.upsert({ ...CAL, label: "calendar" });
    const worker = new WorkerDaemon({
      url,
      db,
      registry,
      journal: new Journal(db),
      livenessFile: join(dir, "liveness.json"),
      livenessIntervalMs: 60_000,
      livenessDeadlineMs: 2_000,
      hotsetPollMs: 50,
      queuePollMs: 40,
      turnTimeoutMs: 60_000,
      abortConfirmMs: 1_000,
      degraded: null,
      surfacePort: 0,
      stateDir: dir,
      digestSweepMs: 100_000, // swept EXPLICITLY in these tests, deterministic
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
      reconnect: FAST_RECONNECT,
    });
    await worker.start();
    if (worker.surfaceBoundPort === null) throw new Error("no surface port");
    stack = {
      worker,
      server,
      surfacePort: worker.surfaceBoundPort,
      token: ensureSurfaceToken(dir),
      turnJournal: new TurnJournal(db),
      db,
    };
    return stack;
  }

  async function directExchange(s: Stack, text: string): Promise<string> {
    const surface = new TestSurface();
    surfaces.push(surface);
    await surface.connect(s.surfacePort);
    await surface.attach({ token: s.token, runtime: KINARA, capabilities: ["core", "direct"] });
    s.worker.routes.set("calendar", CAL.agent_id, CAL.conversation_id, "operator-cli");
    const sent = await surface.request(
      { type: "send", request_id: "r1", text: `@calendar ${text}` },
      (f) => f.type === "send_ok",
    );
    const cm = sent.client_message_id as string;
    await waitFor(() => s.worker.pipeline.rowFor(cm)?.state === "terminal", 5000);
    surface.close();
    return cm;
  }

  it("a completed direct exchange digests into its ROUTE-ORIGIN thread as ONE batched muted turn", async () => {
    const s = await startStack();
    const cm = await directExchange(s, "check tomorrow");
    expect(s.worker.digests.undeliveredCount()).toBe(1);

    s.worker.digests.sweep();
    await waitFor(() => s.worker.digests.undeliveredCount() === 0, 5000);
    // Exactly one digest turn, in KINARA's thread (the route origin), carrying the item id.
    const digestRows = s.worker.pipeline
      .rows(["queued", "submitting", "submitted", "terminal"])
      .filter((r) => (r.origin as { via?: string }).via === "digest");
    expect(digestRows).toHaveLength(1);
    expect(digestRows[0]?.agent_id).toBe(KINARA.agent_id);
    expect(digestRows[0]?.conversation_id).toBe(KINARA.conversation_id);
    expect(digestRows[0]?.content).toContain(cm); // the R12 dedupe key
    // MUTED: no awareness signal fired for the digest, no unseen marker.
    const unseen = s.db.prepare("SELECT COUNT(*) AS n FROM unseen").get() as { n: number };
    expect(unseen.n).toBe(0);
    const kinds = s.turnJournal.eventsFor(KINARA).map((e) => e.kind);
    expect(kinds).toContain("digest_delivered");
    expect(kinds).not.toContain("awareness_signal");
  });

  it("OPERATOR MESSAGES PREEMPT: the sweep defers while one is pending, delivers after", async () => {
    const s = await startStack();
    await directExchange(s, "check tomorrow");
    // Wedge the Kinara thread with a pending operator message.
    s.server.options.autoTurnOnInput = false;
    const operatorCm = s.worker.pipeline.accept(KINARA, "operator first", { via: "surface" });
    await waitFor(() => s.worker.pipeline.rowFor(operatorCm)?.state === "submitted", 5000);

    s.worker.digests.sweep();
    expect(s.worker.digests.undeliveredCount()).toBe(1); // deferred, not dropped

    // The operator's turn completes; the next sweep delivers.
    s.server.broadcastTurn(KINARA, "run-op-1", [
      { id: "m-op-1", messageType: "assistant_message", text: "operator reply" },
    ]);
    await waitFor(() => s.worker.pipeline.rowFor(operatorCm)?.state === "terminal", 5000);
    s.server.options.autoTurnOnInput = true;
    s.worker.digests.sweep();
    await waitFor(() => s.worker.digests.undeliveredCount() === 0, 5000);
  });

  it("digests map to the thread whose route produced them — never fanned out to all threads", async () => {
    const s = await startStack();
    await directExchange(s, "for thread A");
    s.worker.digests.sweep();
    await waitFor(() => s.worker.digests.undeliveredCount() === 0, 5000);
    const digestRowsB = s.worker.pipeline
      .rows(["queued", "submitting", "submitted", "terminal"])
      .filter(
        (r) =>
          (r.origin as { via?: string }).via === "digest" &&
          r.conversation_id === KINARA_B.conversation_id,
      );
    expect(digestRowsB).toHaveLength(0);
  });
});
