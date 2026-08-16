/**
 * TurnPipeline through the REAL worker + mock App Server: serialized submission, durable-queue
 * survival, the submitting-window exactly-once seam, the abort-coupled wall-clock backstop,
 * and visible failure on every exit. These are proofs P3/P4's offline halves; the live halves
 * run against the clone stack.
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { sleep, waitFor } from "@ai-pa/letta-continuity-core/testing/harness";
import { afterEach, describe, expect, it } from "vitest";
import { TurnJournal } from "../src/journal.js";
import { Registry } from "../src/registry.js";
import { openStateDb } from "../src/state/db.js";
import { Journal } from "../src/state/journal.js";
import { enqueueDurable } from "../src/turns.js";
import { WorkerDaemon } from "../src/worker.js";

const FAST_RECONNECT = { baseDelayMs: 20, maxDelayMs: 40, stabilityMs: 0, jitter: () => 0 };
const RUNTIME = { agent_id: "ag-1", conversation_id: "local-conv-1" };

interface Fixture {
  dir: string;
  db: ReturnType<typeof openStateDb>["db"];
  registry: Registry;
  journal: Journal;
  turnJournal: TurnJournal;
}

function state(): Fixture {
  const dir = mkdtempSync(join(tmpdir(), "continuity-turns-"));
  const { db } = openStateDb(dir);
  const registry = new Registry(db);
  registry.upsert(RUNTIME);
  return { dir, db, registry, journal: new Journal(db), turnJournal: new TurnJournal(db) };
}

function makeWorker(url: string, fixture: Fixture, overrides: Record<string, unknown> = {}): WorkerDaemon {
  return new WorkerDaemon({
    url,
    db: fixture.db,
    registry: fixture.registry,
    journal: fixture.journal,
    livenessFile: join(fixture.dir, "liveness.json"),
    livenessIntervalMs: 60_000,
    livenessDeadlineMs: 2_000,
    hotsetPollMs: 50,
    queuePollMs: 40,
    turnTimeoutMs: 60_000,
    abortConfirmMs: 500,
    degraded: null,
    onExhausted: () => {
      throw new Error("unexpected exhaustion");
    },
    reconnect: FAST_RECONNECT,
    ...overrides,
  });
}

describe("TurnPipeline (worker + mock server)", () => {
  let server: MockAppServer;
  let worker: WorkerDaemon | null = null;

  afterEach(async () => {
    worker?.stop();
    worker = null;
    await server?.stop();
  });

  it("two messages to one runtime serialize; both reach stop_reason terminality exactly once", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const fixture = state();
    worker = makeWorker(url, fixture);
    await worker.start();

    const cm1 = worker.pipeline.accept(RUNTIME, "first");
    const cm2 = worker.pipeline.accept(RUNTIME, "second");
    await waitFor(
      () => worker?.pipeline.rowFor(cm1)?.state === "terminal" && worker?.pipeline.rowFor(cm2)?.state === "terminal",
      5000,
    );
    expect(worker.pipeline.rowFor(cm1)?.outcome).toBe("end_turn");
    expect(worker.pipeline.rowFor(cm2)?.outcome).toBe("end_turn");
    // Serialization: the second input hit the wire only after the first turn's terminality.
    const inputs = server.received.filter((f) => f.type === "input");
    expect(inputs).toHaveLength(2);
    const terminalEvents = fixture.turnJournal
      .eventsFor(RUNTIME)
      .filter((e) => e.kind === "turn_terminal");
    expect(terminalEvents).toHaveLength(2);
    // Exactly-once on the wire events despite both delta AND turn_finished arms firing.
    expect(fixture.turnJournal.duplicateCount()).toBe(0);
  });

  it("a queued-but-unsubmitted message survives a worker restart and then runs (durable queue)", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const fixture = state();
    // Enqueued while NO worker exists — the S4local property, through the real seam.
    const cm = enqueueDurable(fixture.db, fixture.turnJournal, RUNTIME, "held message", { via: "test" });
    worker = makeWorker(url, fixture);
    await worker.start();
    await waitFor(() => worker?.pipeline.rowFor(cm)?.state === "terminal", 5000);
    expect(worker.pipeline.rowFor(cm)?.outcome).toBe("end_turn");
  });

  it("submitting-window crash, message ABSENT from transcript → requeued and submitted exactly once", async () => {
    server = new MockAppServer(); // empty messagesSnapshot = confirmed absence
    const url = await server.start();
    const fixture = state();
    // Simulate the crash: a row died in `submitting` (write→ack window) in a previous life.
    const cm = enqueueDurable(fixture.db, fixture.turnJournal, RUNTIME, "maybe-lost", {});
    fixture.db
      .prepare("UPDATE turn_queue SET state = 'submitting' WHERE client_message_id = ?")
      .run(cm);

    worker = makeWorker(url, fixture);
    await worker.start();
    await waitFor(() => worker?.pipeline.rowFor(cm)?.state === "terminal", 5000);
    const kinds = fixture.turnJournal.eventsFor(RUNTIME).map((e) => e.kind);
    expect(kinds).toContain("reconciled_absent_requeued");
    // EXACTLY once on the wire.
    expect(server.received.filter((f) => f.type === "input")).toHaveLength(1);
  });

  it("submitting-window crash, message PRESENT with a newer reply → closed by reconciliation, NO resubmit", async () => {
    const fixtureCm = "cm-preexisting-0001";
    const server2 = new MockAppServer({
      messagesSnapshot: [
        { id: "ui-msg-2", message_type: "assistant_message", content: [{ type: "text", text: "done" }] },
        { id: "ui-msg-1", message_type: "user_message", otid: fixtureCm },
      ],
    });
    server = server2;
    const url = await server2.start();
    const fixture = state();
    const now = new Date().toISOString();
    fixture.db
      .prepare(
        `INSERT INTO turn_queue (agent_id, conversation_id, client_message_id, content, origin, state, created_at, updated_at)
         VALUES (?, ?, ?, 'was submitted', '{}', 'submitting', ?, ?)`,
      )
      .run(RUNTIME.agent_id, RUNTIME.conversation_id, fixtureCm, now, now);

    worker = makeWorker(url, fixture);
    await worker.start();
    await waitFor(() => worker?.pipeline.rowFor(fixtureCm)?.state === "terminal", 5000);
    expect(worker.pipeline.rowFor(fixtureCm)?.outcome).toBe("end_turn:reconciled");
    // The documented hazard is the DOUBLE turn — assert zero resubmission.
    expect(server.received.filter((f) => f.type === "input")).toHaveLength(0);
  });

  it("a submitted turn orphaned by a server restart is FAILED-VISIBLE, never silently absent (P4 shape)", async () => {
    server = new MockAppServer(); // transcript comes back WITHOUT the message (server lost it)
    const url = await server.start();
    const fixture = state();
    const cm = "cm-orphaned-0001";
    const now = new Date().toISOString();
    fixture.db
      .prepare(
        `INSERT INTO turn_queue (agent_id, conversation_id, client_message_id, content, origin, state, created_at, updated_at)
         VALUES (?, ?, ?, 'orphaned', '{}', 'submitted', ?, ?)`,
      )
      .run(RUNTIME.agent_id, RUNTIME.conversation_id, cm, now, now);
    // Present-but-unanswered variant: transcript HAS the user row, no reply, runtime idle.
    const cm2 = "cm-orphaned-0002";
    server.options.messagesSnapshot = [{ id: "ui-msg-1", message_type: "user_message", otid: cm2 }];
    fixture.db
      .prepare(
        `INSERT INTO turn_queue (agent_id, conversation_id, client_message_id, content, origin, state, created_at, updated_at)
         VALUES (?, ?, ?, 'orphaned2', '{}', 'submitted', ?, ?)`,
      )
      .run(RUNTIME.agent_id, RUNTIME.conversation_id, cm2, now, now);

    worker = makeWorker(url, fixture, { queuePollMs: 100_000 }); // isolate recovery from pump noise
    await worker.start();
    await waitFor(() => worker?.pipeline.rowFor(cm2)?.state === "terminal", 5000);
    expect(worker.pipeline.rowFor(cm2)?.outcome).toBe("FAILED-VISIBLE:lost-to-restart");
    const kinds = fixture.turnJournal.eventsFor(RUNTIME).map((e) => e.kind);
    expect(kinds).toContain("turn_failed_visible");
  });

  it("a rejected input is FAILED-VISIBLE and the next message still runs", async () => {
    server = new MockAppServer({ rejectInputWith: "runtime is no longer active" });
    const url = await server.start();
    const fixture = state();
    worker = makeWorker(url, fixture);
    await worker.start();
    const cm = worker.pipeline.accept(RUNTIME, "will be rejected");
    await waitFor(() => worker?.pipeline.rowFor(cm)?.state === "terminal", 5000);
    expect(worker.pipeline.rowFor(cm)?.outcome).toBe("FAILED-VISIBLE:rejected");

    server.options.rejectInputWith = undefined;
    const cm2 = worker.pipeline.accept(RUNTIME, "runs fine");
    await waitFor(() => worker?.pipeline.rowFor(cm2)?.state === "terminal", 5000);
    expect(worker.pipeline.rowFor(cm2)?.outcome).toBe("end_turn");
  });

  it("wedged turn: timeout → abort → FAILED-VISIBLE → the NEXT queued message actually runs", async () => {
    server = new MockAppServer({ autoTurnOnInput: false }); // the turn never progresses
    const url = await server.start();
    const fixture = state();
    worker = makeWorker(url, fixture, { turnTimeoutMs: 300 });
    await worker.start();

    const cm1 = worker.pipeline.accept(RUNTIME, "wedges forever");
    const cm2 = worker.pipeline.accept(RUNTIME, "must still run");
    await waitFor(() => worker?.pipeline.rowFor(cm1)?.state === "terminal", 5000);
    expect(worker.pipeline.rowFor(cm1)?.outcome).toBe("FAILED-VISIBLE:timeout");
    // The abort actually went to the server (the coupling, not just a local skip).
    expect(server.received.some((f) => f.type === "abort_message")).toBe(true);
    // No head-of-line cascade: the second message reaches the wire after the abort.
    await waitFor(() => server.received.filter((f) => f.type === "input").length === 2, 5000);
    expect(worker.pipeline.rowFor(cm2)?.state).toBe("submitted");
  });

  it("an UNCONFIRMED abort holds the queue and bounces; recovery requeues via the transcript", async () => {
    server = new MockAppServer({
      autoTurnOnInput: false,
      suppressResponsesFor: ["abort_message"],
    });
    const url = await server.start();
    const fixture = state();
    worker = makeWorker(url, fixture, { turnTimeoutMs: 300, abortConfirmMs: 200 });
    await worker.start();

    const cm1 = worker.pipeline.accept(RUNTIME, "wedges, abort lost");
    const cm2 = worker.pipeline.accept(RUNTIME, "held behind the wedge");
    // The wedge escalates: abort_unconfirmed journaled, connection bounced (a second attach).
    await waitFor(
      () => fixture.turnJournal.eventsFor(RUNTIME).some((e) => e.kind === "abort_unconfirmed"),
      5000,
    );
    // The queue was NOT released while the server might still be running the turn.
    expect(worker.pipeline.rowFor(cm2)?.state).toBe("queued");
    // After the bounce, recovery reconciles cm1 (absent from the empty transcript) → requeued.
    await waitFor(
      () => fixture.turnJournal.eventsFor(RUNTIME).some((e) => e.kind === "reconciled_absent_requeued"),
      5000,
    );
    expect(worker.pipeline.rowFor(cm1)?.outcome).not.toBe("FAILED-VISIBLE:timeout");
  });

  it("the row is durably `submitting` BEFORE the ack returns (the reconcilable crash window)", async () => {
    server = new MockAppServer({ suppressResponsesFor: ["input"] }); // write lands, ack never comes
    const url = await server.start();
    const fixture = state();
    worker = makeWorker(url, fixture);
    await worker.start();
    const cm = worker.pipeline.accept(RUNTIME, "no ack ever");
    await waitFor(() => server.received.some((f) => f.type === "input"), 5000);
    // The socket write happened; the ack did not — the durable state is what recovery reads.
    expect(worker.pipeline.rowFor(cm)?.state).toBe("submitting");
  });

  it("journal generations PERSIST across worker restarts (the ordering audit's grouping key)", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const fixture = state();
    worker = makeWorker(url, fixture);
    await worker.start();
    const gen1 = fixture.db.prepare("SELECT value FROM meta WHERE key = 'journal_generation'").get() as
      | { value: string }
      | undefined;
    expect(Number(gen1?.value)).toBeGreaterThanOrEqual(1);
    worker.stop();

    worker = makeWorker(url, fixture);
    await worker.start();
    const gen2 = fixture.db.prepare("SELECT value FROM meta WHERE key = 'journal_generation'").get() as {
      value: string;
    };
    expect(Number(gen2.value)).toBeGreaterThan(Number(gen1?.value ?? 0));
  });

  it("a reconnect KILLS the previous turn's wall-clock timer — a completed turn stays end_turn", async () => {
    server = new MockAppServer({ autoTurnOnInput: false });
    const url = await server.start();
    const fixture = state();
    worker = makeWorker(url, fixture, { turnTimeoutMs: 400 });
    await worker.start();
    const cm = worker.pipeline.accept(RUNTIME, "will be re-run after a drop");
    await waitFor(() => worker?.pipeline.rowFor(cm)?.state === "submitted", 5000);

    // Drop the connection BEFORE the 400ms timer fires; recovery requeues (empty transcript)
    // and the re-run completes normally.
    server.options.autoTurnOnInput = true;
    server.dropAllConnections();
    await waitFor(() => worker?.pipeline.rowFor(cm)?.outcome === "end_turn", 5000);
    // The FIRST submission's stale timer must not fire and overwrite the completed outcome.
    await sleep(600);
    expect(worker.pipeline.rowFor(cm)?.outcome).toBe("end_turn");
  });

  it("a foreign turn (not controller-submitted) journals identically to a surface turn", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const fixture = state();
    worker = makeWorker(url, fixture);
    await worker.start();

    server.injectForeignTurn(RUNTIME, "run-foreign-1", [
      { id: "m-f1", messageType: "assistant_message", text: "scheduler said hi" },
    ]);
    await waitFor(
      () => fixture.turnJournal.eventsFor(RUNTIME).some((e) => e.kind === "turn_finished"),
      5000,
    );
    const kinds = fixture.turnJournal.eventsFor(RUNTIME).map((e) => e.kind);
    expect(kinds).toContain("assistant_message");
    expect(fixture.turnJournal.duplicateCount()).toBe(0);
  });
});
