/**
 * Awareness + unseen (C7): THE 10:55 shape — a turn delivered with zero surfaces attached is
 * completed, marked unseen, presented on the next attach, and consumed there. Attached
 * notify-capable surfaces get live awareness frames; `muted` notifies nobody but is journaled;
 * `notify_operator` (the agent's lever) overrides the default level.
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
const SECRET = "awareness-secret";
const AGENT = "ag-1";
const RUNTIME = { agent_id: AGENT, conversation_id: "local-conv-1" };

interface Stack {
  worker: WorkerDaemon;
  server: MockAppServer;
  ingressPort: number;
  surfacePort: number;
  token: string;
  turnJournal: TurnJournal;
  db: ReturnType<typeof openStateDb>["db"];
}

describe("awareness + unseen", () => {
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
    const dir = mkdtempSync(join(tmpdir(), "continuity-awareness-"));
    const { db } = openStateDb(dir);
    const registry = new Registry(db);
    registry.upsert({ ...RUNTIME, label: "main", origin: { default: true } });
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
      ingressPort: 0,
      ingressSecret: SECRET,
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
      reconnect: FAST_RECONNECT,
    });
    await worker.start();
    if (worker.ingressBoundPort === null || worker.surfaceBoundPort === null)
      throw new Error("ports did not bind");
    stack = {
      worker,
      server,
      ingressPort: worker.ingressBoundPort,
      surfacePort: worker.surfaceBoundPort,
      token: ensureSurfaceToken(dir),
      turnJournal: new TurnJournal(db),
      db,
    };
    return stack;
  }

  function ingressPost(s: Stack, content: string): Promise<Response> {
    return fetch(`http://127.0.0.1:${s.ingressPort}/v1/agents/${AGENT}/messages`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${SECRET}` },
      body: JSON.stringify({ messages: [{ role: "user", content }] }),
    });
  }

  it("THE 10:55 TEST: zero surfaces → turn completes, unseen marked, presented on attach, consumed", async () => {
    const s = await startStack();
    const res = await ingressPost(s, "scheduled reminder");
    expect(res.status).toBe(202);
    const { client_message_id: cm } = (await res.json()) as { client_message_id: string };
    await waitFor(() => s.worker.pipeline.rowFor(cm)?.state === "terminal", 5000);
    expect(s.worker.pipeline.rowFor(cm)?.outcome).toBe("end_turn");
    // Nobody was attached: the arrival is durable state.
    const unseen = s.db.prepare("SELECT ref FROM unseen WHERE kind = 'turn'").all() as Array<{
      ref: string;
    }>;
    expect(unseen.map((u) => u.ref)).toContain(cm);

    // The next attach is SHOWN what arrived while away — and the showing consumes it.
    const surface = new TestSurface();
    surfaces.push(surface);
    await surface.connect(s.surfacePort);
    const ok = await surface.attach({
      token: s.token,
      runtime: RUNTIME,
      capabilities: ["core", "notify"],
    });
    const presented = (ok.unseen as Array<{ ref: string }>).map((u) => u.ref);
    expect(presented).toContain(cm);
    // The replayed journal contains the completed turn itself, not just the marker.
    expect((ok.replay as Array<{ kind: string }>).map((e) => e.kind)).toContain("turn_terminal");
    const after = s.db.prepare("SELECT COUNT(*) AS n FROM unseen WHERE kind = 'turn'").get() as {
      n: number;
    };
    expect(after.n).toBe(0);
  });

  it("an attached notify-capable surface gets a live `badge`; a core-only surface gets nothing", async () => {
    const s = await startStack();
    const notify = new TestSurface();
    const plain = new TestSurface();
    surfaces.push(notify, plain);
    await notify.connect(s.surfacePort);
    await plain.connect(s.surfacePort);
    await notify.attach({ token: s.token, runtime: RUNTIME, capabilities: ["core", "notify"] });
    await plain.attach({ token: s.token, runtime: RUNTIME, capabilities: ["core"] });

    await ingressPost(s, "badge me");
    const frame = await notify.waitFrame((f) => f.type === "awareness", 5000);
    expect(frame?.level).toBe("badge");
    expect(plain.frames.some((f) => f.type === "awareness")).toBe(false);
    // Somebody capable saw it arrive → no unseen marker.
    const unseen = s.db.prepare("SELECT COUNT(*) AS n FROM unseen WHERE kind = 'turn'").get() as {
      n: number;
    };
    expect(unseen.n).toBe(0);
  });

  it("notify_operator overrides the default: interrupt raises; muted silences (but journals)", async () => {
    const s = await startStack();
    const surface = new TestSurface();
    surfaces.push(surface);
    await surface.connect(s.surfacePort);
    await surface.attach({ token: s.token, runtime: RUNTIME, capabilities: ["core", "notify"] });

    // The agent pulls the lever mid-turn: the server routes the external tool call to the
    // registering connection — simulated by the mock delivering the request frame.
    s.server.sendRaw({
      type: "external_tool_call_request",
      request_id: "ext-1",
      runtime: RUNTIME,
      tool_call_id: "call-notify-1",
      tool_name: "notify_operator",
      input: { level: "interrupt", note: "urgent" },
    });
    await waitFor(
      () => s.server.received.some((f) => f.type === "external_tool_call_response"),
      5000,
    );
    await ingressPost(s, "urgent thing");
    const frame = await surface.waitFrame((f) => f.type === "awareness", 5000);
    expect(frame?.level).toBe("interrupt");

    // muted: journaled, delivered to nobody, and no unseen marker either — muted means muted.
    s.server.sendRaw({
      type: "external_tool_call_request",
      request_id: "ext-2",
      runtime: RUNTIME,
      tool_call_id: "call-notify-2",
      tool_name: "notify_operator",
      input: { level: "muted" },
    });
    await waitFor(
      () => s.server.received.filter((f) => f.type === "external_tool_call_response").length >= 2,
      5000,
    );
    const before = surface.frames.filter((f) => f.type === "awareness").length;
    const res = await ingressPost(s, "quiet thing");
    const { client_message_id: cm } = (await res.json()) as { client_message_id: string };
    await waitFor(() => s.worker.pipeline.rowFor(cm)?.state === "terminal", 5000);
    expect(surface.frames.filter((f) => f.type === "awareness").length).toBe(before);
    const kinds = s.turnJournal.eventsFor(RUNTIME).map((e) => e.kind);
    expect(kinds).toContain("awareness_directive");
    const signals = s.turnJournal.eventsFor(RUNTIME).filter((e) => e.kind === "awareness_signal");
    expect(JSON.stringify(signals.at(-1)?.payload)).toContain("muted");
  });

  it("the worker's hellos REGISTER notify_operator (re-registration rides every reconnect)", async () => {
    const s = await startStack();
    const hellos = s.server.received.filter((f) => f.type === "runtime_start");
    expect(hellos.length).toBeGreaterThan(0);
    expect(JSON.stringify(hellos.at(-1)?.external_tools ?? [])).toContain("notify_operator");
  });
});
