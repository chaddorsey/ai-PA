/**
 * OPT-IN live gate for the C4 pipeline: one REAL tool turn end-to-end on a clone backend —
 * accept → durable queue → submit → stream → terminality → journal, all against a real
 * `letta server` and a real model.
 *
 *   LETTA_LIVE_WS=1 LETTA_LIVE_WS_URL=ws://127.0.0.1:4599/ws \
 *     LETTA_LIVE_WS_AGENT=<scratch-agent> npx vitest run test/live.controller.contract.test.ts
 *
 * Uses a scratch agent (tools/scratch-agent.mjs) on a CLONE server only. The P3/P4 crash
 * proofs run as scripted scenarios against the launchd-supervised worker (see the C4 findings
 * in the plan); this gate proves the pipeline itself speaks the live protocol.
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Outbound, buildConversationCreate } from "@ai-pa/letta-continuity-core/protocol";
import { waitFor } from "@ai-pa/letta-continuity-core/testing/harness";
import { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import { afterEach, describe, expect, it } from "vitest";
import { TurnJournal } from "../src/journal.js";
import { Registry } from "../src/registry.js";
import { openStateDb } from "../src/state/db.js";
import { Journal } from "../src/state/journal.js";
import { WorkerDaemon } from "../src/worker.js";

const LIVE = process.env.LETTA_LIVE_WS === "1";
const URL_ = process.env.LETTA_LIVE_WS_URL ?? "ws://127.0.0.1:4599/ws";
const AGENT = process.env.LETTA_LIVE_WS_AGENT ?? "";

describe.skipIf(!LIVE)(`live C4 pipeline (opt-in, ${URL_}, agent ${AGENT})`, () => {
  let worker: WorkerDaemon | null = null;

  afterEach(() => {
    worker?.stop();
    worker = null;
  });

  it("a real tool turn runs the full pipeline to end_turn with an exactly-once journal", async () => {
    if (!AGENT) throw new Error("set LETTA_LIVE_WS_AGENT to a scratch agent id");
    // A fresh conversation per run (created, never `default` — the C1 S3 rule).
    const seed = new WsConnection({ url: URL_, versionPolicy: "warn" });
    await seed.connectBare();
    const created = await seed.request(
      (rid) => buildConversationCreate(rid, AGENT, "live-c4-gate"),
      Outbound.conversationCreate,
    );
    seed.close();
    const conversationId = (created.conversation as { id?: string } | null)?.id;
    if (typeof conversationId !== "string") throw new Error("no conversation id");
    const runtime = { agent_id: AGENT, conversation_id: conversationId };

    const dir = mkdtempSync(join(tmpdir(), "continuity-live-c4-"));
    const { db } = openStateDb(dir);
    const registry = new Registry(db);
    registry.upsert({ ...runtime, label: "live-c4-gate" });
    const turnJournal = new TurnJournal(db);

    worker = new WorkerDaemon({
      url: URL_,
      db,
      registry,
      journal: new Journal(db),
      livenessFile: join(dir, "liveness.json"),
      livenessIntervalMs: 60_000,
      livenessDeadlineMs: 10_000,
      hotsetPollMs: 500,
      queuePollMs: 200,
      turnTimeoutMs: 120_000,
      abortConfirmMs: 10_000,
      degraded: null,
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
    });
    await worker.start();

    const marker = `live-c4-${process.pid}`;
    const cm = worker.pipeline.accept(
      runtime,
      `Run this exact shell command with the Bash tool, as a single foreground command: caffeinate -t 5; echo ${marker}`,
    );
    await waitFor(() => worker?.pipeline.rowFor(cm)?.state === "terminal", 120_000);
    expect(worker.pipeline.rowFor(cm)?.outcome).toBe("end_turn");

    const events = turnJournal.eventsFor(runtime);
    const kinds = events.map((e) => e.kind);
    expect(kinds).toContain("turn_submitted");
    expect(kinds).toContain("input_accepted");
    expect(kinds).toContain("client_tool_start");
    expect(kinds).toContain("tool_return_message");
    expect(kinds).toContain("turn_terminal");
    // The tool's actual output made it into the journaled record.
    const returns = events.filter((e) => e.kind === "tool_return_message");
    expect(JSON.stringify(returns)).toContain(marker);
    // Exactly-once against real wire keys.
    expect(turnJournal.duplicateCount()).toBe(0);
  }, 150_000);
});
