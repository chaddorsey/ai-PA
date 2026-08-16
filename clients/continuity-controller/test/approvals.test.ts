/**
 * Approval arbitration (C5): fan-out to capable surfaces, first answer wins, the server is
 * acked exactly once, later answers see resolution; with nobody capable attached the approval
 * is HELD with an unseen marker and delivered on the next capable attach.
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { waitFor } from "@ai-pa/letta-continuity-core/testing/harness";
import { afterEach, describe, expect, it } from "vitest";
import { Registry } from "../src/registry.js";
import { openStateDb } from "../src/state/db.js";
import { Journal } from "../src/state/journal.js";
import { ensureSurfaceToken } from "../src/surface/auth.js";
import { WorkerDaemon } from "../src/worker.js";
import { TestSurface } from "./helpers/surfaceClient.js";

const FAST_RECONNECT = { baseDelayMs: 20, maxDelayMs: 40, stabilityMs: 0, jitter: () => 0 };
const RUNTIME = { agent_id: "ag-1", conversation_id: "local-conv-1" };

describe("approval arbitration", () => {
  let server: MockAppServer;
  let worker: WorkerDaemon | null = null;
  let db: ReturnType<typeof openStateDb>["db"] | null = null;
  const surfaces: TestSurface[] = [];

  afterEach(async () => {
    for (const s of surfaces) s.close();
    surfaces.length = 0;
    worker?.stop();
    worker = null;
    await server?.stop();
  });

  async function startStack(): Promise<{ token: string; port: number; dir: string }> {
    const url = await server.start();
    const dir = mkdtempSync(join(tmpdir(), "continuity-approvals-"));
    const opened = openStateDb(dir);
    db = opened.db;
    new Registry(db).upsert(RUNTIME);
    worker = new WorkerDaemon({
      url,
      db,
      registry: new Registry(db),
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
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
      reconnect: FAST_RECONNECT,
    });
    await worker.start();
    const port = worker.surfaceBoundPort;
    if (port === null) throw new Error("surface did not bind");
    return { token: ensureSurfaceToken(dir), port, dir };
  }

  async function attach(stack: { token: string; port: number }, capabilities: string[]) {
    const surface = new TestSurface();
    surfaces.push(surface);
    await surface.connect(stack.port);
    const ok = await surface.attach({ token: stack.token, runtime: RUNTIME, capabilities });
    expect(ok.type).toBe("attach_ok");
    return surface;
  }

  it("two capable surfaces: first answer wins, second sees resolution, server acked ONCE", async () => {
    server = new MockAppServer({ approvalMode: true });
    const stack = await startStack();
    const a = await attach(stack, ["core", "approvals"]);
    const b = await attach(stack, ["core", "approvals"]);
    const plain = await attach(stack, ["core"]); // core tier must never see approval frames

    if (!worker) throw new Error("no worker");
    worker.pipeline.accept(RUNTIME, "do something gated");
    const requestA = await a.waitFrame((f) => f.type === "approval_request");
    const requestB = await b.waitFrame((f) => f.type === "approval_request");
    expect(requestA).not.toBeNull();
    expect(requestB).not.toBeNull();
    const approvalId = requestA?.approval_id as string;

    a.send({
      type: "approval_answer",
      approval_id: approvalId,
      decision: { behavior: "deny", message: "no" },
    });
    const resolvedOnB = await b.waitFrame((f) => f.type === "approval_resolved");
    expect(resolvedOnB?.approval_id).toBe(approvalId);

    // Late answer from B: sees resolution, does NOT double-ack the server.
    b.send({ type: "approval_answer", approval_id: approvalId, decision: { behavior: "allow" } });
    await b.waitFrame((f) => f.type === "approval_resolved" && f.by === "already-settled");
    await waitFor(
      () =>
        server.received.filter(
          (f) =>
            f.type === "input" && (f.payload as { kind?: string })?.kind === "approval_response",
        ).length === 1,
      2000,
    );
    const approvalAcks = server.received.filter(
      (f) => f.type === "input" && (f.payload as { kind?: string })?.kind === "approval_response",
    );
    expect(approvalAcks).toHaveLength(1);
    // The core-tier surface saw the turn events but never an approval frame (R28 degradation).
    expect(plain.frames.some((f) => f.type === "approval_request")).toBe(false);
  });

  it("no capable surface: HELD pending + unseen marker; delivered on the next capable attach", async () => {
    server = new MockAppServer({ approvalMode: true });
    const stack = await startStack();
    await attach(stack, ["core"]); // attached, but not approval-capable

    if (!worker) throw new Error("no worker");
    worker.pipeline.accept(RUNTIME, "gated with nobody capable");
    await waitFor(() => (worker?.approvals.pendingApprovals().length ?? 0) > 0, 3000);
    // Unseen marker persisted (the R28 degradation trail).
    const marker = db
      ?.prepare("SELECT COUNT(*) AS n FROM unseen WHERE kind = 'approval'")
      .get() as { n: number };
    expect(marker.n).toBe(1);

    // A capable surface attaches LATER: the held approval is delivered immediately.
    const late = await attach(stack, ["core", "approvals"]);
    const request = await late.waitFrame((f) => f.type === "approval_request");
    expect(request).not.toBeNull();
    late.send({
      type: "approval_answer",
      approval_id: request?.approval_id as string,
      decision: { behavior: "deny" },
    });
    await waitFor(() => (worker?.approvals.pendingApprovals().length ?? 1) === 0, 3000);
    const cleared = db
      ?.prepare("SELECT COUNT(*) AS n FROM unseen WHERE kind = 'approval'")
      .get() as { n: number };
    expect(cleared.n).toBe(0);
  });
});
