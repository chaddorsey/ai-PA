/**
 * OPT-IN live proof P5 (plan C5): an approval survives absence. On a clone backend with the
 * runtime flipped to `standard` permission mode, a real `control_request` fires with ZERO
 * surfaces attached → held pending + unseen marker → survives a controller restart (recovered
 * via runtime_start's recover_approvals default) → answerable on the next capable attach, and
 * the answer releases the real turn.
 *
 *   LETTA_LIVE_WS=1 LETTA_LIVE_WS_URL=ws://127.0.0.1:4599/ws \
 *     LETTA_LIVE_WS_AGENT=<scratch> npx vitest run test/live.approvals.contract.test.ts
 *
 * The production tripwire remains the UNRESTRICTED pin in the core's live gate; this test is
 * the safe-side proof that arbitration works against a real control_request, not only mocks.
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Outbound, buildConversationCreate } from "@ai-pa/letta-continuity-core/protocol";
import { waitFor } from "@ai-pa/letta-continuity-core/testing/harness";
import { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import { afterEach, describe, expect, it } from "vitest";
import { AnchorDaemon } from "../src/anchor.js";
import { ReadOnlyRegistry, Registry } from "../src/registry.js";
import { openStateDb, openStateDbReadOnly } from "../src/state/db.js";
import { Journal } from "../src/state/journal.js";
import { ensureSurfaceToken } from "../src/surface/auth.js";
import { WorkerDaemon } from "../src/worker.js";
import { TestSurface } from "./helpers/surfaceClient.js";

const LIVE = process.env.LETTA_LIVE_WS === "1";
const URL_ = process.env.LETTA_LIVE_WS_URL ?? "ws://127.0.0.1:4599/ws";
const AGENT = process.env.LETTA_LIVE_WS_AGENT ?? "";

function makeWorker(dir: string, db: ReturnType<typeof openStateDb>["db"]): WorkerDaemon {
  return new WorkerDaemon({
    url: URL_,
    db,
    registry: new Registry(db),
    journal: new Journal(db),
    livenessFile: join(dir, "liveness.json"),
    livenessIntervalMs: 60_000,
    livenessDeadlineMs: 10_000,
    hotsetPollMs: 500,
    queuePollMs: 200,
    turnTimeoutMs: 300_000,
    abortConfirmMs: 10_000,
    degraded: null,
    surfacePort: 0,
    stateDir: dir,
    runtimeMode: "standard", // THE FLIP: approvals become observable on this clone runtime
    onExhausted: () => {
      throw new Error("unexpected exhaustion");
    },
  });
}

describe.skipIf(!LIVE)(`live P5 approval-survives-absence (opt-in, ${URL_})`, () => {
  let worker: WorkerDaemon | null = null;
  let anchor: AnchorDaemon | null = null;
  const surfaces: TestSurface[] = [];

  afterEach(() => {
    for (const s of surfaces) s.close();
    surfaces.length = 0;
    worker?.stop();
    worker = null;
    anchor?.stop();
    anchor = null;
  });

  it("held with zero surfaces → survives restart → answered on attach → turn completes", async () => {
    if (!AGENT) throw new Error("set LETTA_LIVE_WS_AGENT to a scratch agent id");
    const seed = new WsConnection({ url: URL_, versionPolicy: "warn" });
    await seed.connectBare();
    const created = await seed.request(
      (rid) => buildConversationCreate(rid, AGENT, "live-p5-gate"),
      Outbound.conversationCreate,
    );
    seed.close();
    const conversationId = (created.conversation as { id?: string } | null)?.id;
    if (typeof conversationId !== "string") throw new Error("no conversation id");
    const runtime = { agent_id: AGENT, conversation_id: conversationId };

    const dir = mkdtempSync(join(tmpdir(), "continuity-live-p5-"));
    const { db } = openStateDb(dir);
    new Registry(db).upsert({ ...runtime, label: "live-p5" });

    // Phase 1: a gated tool turn with ZERO surfaces attached.
    worker = makeWorker(dir, db);
    await worker.start();
    // A WRITE command: `standard` mode auto-allows harmless reads (probed live — a bare echo
    // sails through with requires_approval as a mere continuation), but a file write raises a
    // real `can_use_tool` control_request.
    const marker = `p5-approved-${process.pid}`;
    worker.pipeline.accept(
      runtime,
      `Run this exact shell command with the Bash tool, as a single foreground command: echo ${marker} > /private/tmp/${marker}.txt; cat /private/tmp/${marker}.txt`,
    );
    await waitFor(() => (worker?.approvals.pendingApprovals().length ?? 0) > 0, 90_000);
    const held = worker.approvals.pendingApprovals()[0];
    expect(held).toBeDefined();
    const markerRow = db
      .prepare("SELECT COUNT(*) AS n FROM unseen WHERE kind = 'approval'")
      .get() as {
      n: number;
    };
    expect(markerRow.n).toBeGreaterThan(0);

    // Phase 2: the controller RESTARTS — with the ANCHOR holding the runtime, exactly the
    // production topology. Live-probed: with no second subscriber the parked turn (and its
    // approval) is CANCELLED by the worker's detach (q5), and there is nothing to recover;
    // with one, the reconnect re-broadcasts the pending control_request. The anchor is
    // load-bearing for approval survival, not just for turn survival.
    anchor = new AnchorDaemon({
      url: URL_,
      registry: new ReadOnlyRegistry(openStateDbReadOnly(dir)),
      hotsetPollMs: 500,
      runtimeMode: "standard",
      onExhausted: () => {
        throw new Error("unexpected anchor exhaustion");
      },
    });
    await anchor.start();
    worker.stop();
    worker = makeWorker(dir, db);
    await worker.start();
    await waitFor(() => (worker?.approvals.pendingApprovals().length ?? 0) > 0, 60_000);

    // Phase 3: a capable surface attaches — the held approval is delivered and answerable.
    const port = worker.surfaceBoundPort;
    if (port === null) throw new Error("no surface port");
    const surface = new TestSurface();
    surfaces.push(surface);
    await surface.connect(port);
    const ok = await surface.attach({
      token: ensureSurfaceToken(dir),
      runtime,
      capabilities: ["core", "approvals"],
    });
    expect(ok.type).toBe("attach_ok");
    const request = await surface.waitFrame((f) => f.type === "approval_request", 30_000);
    expect(request).not.toBeNull();

    surface.send({
      type: "approval_answer",
      approval_id: request?.approval_id as string,
      decision: { behavior: "allow" },
    });
    // The allow releases the REAL turn: the tool runs and the journal records its output.
    await waitFor(
      () =>
        db
          .prepare(
            "SELECT COUNT(*) AS n FROM turn_events WHERE kind = 'tool_return_message' AND payload LIKE ?",
          )
          .get(`%${marker}%`) !== undefined &&
        (
          db
            .prepare(
              "SELECT COUNT(*) AS n FROM turn_events WHERE kind = 'tool_return_message' AND payload LIKE ?",
            )
            .get(`%${marker}%`) as { n: number }
        ).n > 0,
      120_000,
    );
    const cleared = db
      .prepare("SELECT COUNT(*) AS n FROM unseen WHERE kind = 'approval'")
      .get() as {
      n: number;
    };
    expect(cleared.n).toBe(0);
  }, 300_000);
});
