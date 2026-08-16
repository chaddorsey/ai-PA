/**
 * The scheduler-dialect ingress (C7) against the REAL worker + mock App Server: actions.py's
 * exact body shape, 202-on-accept, tag→default landing, and VISIBLE (journaled) rejection of
 * everything else — 401 above all, since the secret is the control, not the bind address.
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
import { WorkerDaemon } from "../src/worker.js";

const FAST_RECONNECT = { baseDelayMs: 20, maxDelayMs: 40, stabilityMs: 0, jitter: () => 0 };
const SECRET = "test-ingress-secret";
const AGENT = "ag-1";

interface Stack {
  worker: WorkerDaemon;
  port: number;
  turnJournal: TurnJournal;
  db: ReturnType<typeof openStateDb>["db"];
}

describe("scheduler-dialect ingress", () => {
  let server: MockAppServer;
  let stack: Stack | null = null;

  afterEach(async () => {
    stack?.worker.stop();
    stack = null;
    await server?.stop();
  });

  async function startStack(): Promise<Stack> {
    server = new MockAppServer();
    const url = await server.start();
    const dir = mkdtempSync(join(tmpdir(), "continuity-ingress-"));
    const { db } = openStateDb(dir);
    const registry = new Registry(db);
    registry.upsert({ agent_id: AGENT, conversation_id: "local-conv-1", label: "ops" });
    registry.upsert({
      agent_id: AGENT,
      conversation_id: "local-conv-2",
      label: "main",
      origin: { default: true },
    });
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
      ingressPort: 0,
      ingressSecret: SECRET,
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
      reconnect: FAST_RECONNECT,
    });
    await worker.start();
    const port = worker.ingressBoundPort;
    if (port === null) throw new Error("ingress did not bind");
    stack = { worker, port, turnJournal: new TurnJournal(db), db };
    return stack;
  }

  function post(
    port: number,
    path: string,
    body: unknown,
    headers: Record<string, string> = {},
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    return fetch(`http://127.0.0.1:${port}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: JSON.stringify(body),
    }).then(async (r) => ({
      status: r.status,
      body: (await r.json().catch(() => ({}))) as Record<string, unknown>,
    }));
  }

  const SCHEDULER_BODY = { messages: [{ role: "user", content: "the 10:55 reminder" }] };
  const AUTH = { authorization: `Bearer ${SECRET}` };

  it("actions.py's exact POST lands in the DEFAULT thread, runs, and gets a 202 receipt", async () => {
    const s = await startStack();
    const res = await post(s.port, `/v1/agents/${AGENT}/messages`, SCHEDULER_BODY, AUTH);
    expect(res.status).toBe(202);
    const cm = res.body.client_message_id as string;
    await waitFor(() => s.worker.pipeline.rowFor(cm)?.state === "terminal", 5000);
    const row = s.worker.pipeline.rowFor(cm);
    expect(row?.conversation_id).toBe("local-conv-2"); // the default-stamped thread
    expect(row?.outcome).toBe("end_turn");
    // A foreign (scheduler) turn journals exactly like a surface turn.
    const kinds = s.turnJournal
      .eventsFor({ agent_id: AGENT, conversation_id: "local-conv-2" })
      .map((e) => e.kind);
    expect(kinds).toContain("ingress_accepted");
    expect(kinds).toContain("turn_terminal");
  });

  it("an explicit conversation_tag lands in that thread", async () => {
    const s = await startStack();
    const res = await post(
      s.port,
      `/v1/agents/${AGENT}/messages`,
      { ...SCHEDULER_BODY, conversation_tag: "ops" },
      AUTH,
    );
    expect(res.status).toBe(202);
    const cm = res.body.client_message_id as string;
    await waitFor(() => s.worker.pipeline.rowFor(cm)?.state === "terminal", 5000);
    expect(s.worker.pipeline.rowFor(cm)?.conversation_id).toBe("local-conv-1");
  });

  it("the path-token form authenticates a header-less sender (the config-only re-point)", async () => {
    const s = await startStack();
    const res = await post(s.port, `/t/${SECRET}/v1/agents/${AGENT}/messages`, SCHEDULER_BODY);
    expect(res.status).toBe(202);
  });

  it("no secret → 401, JOURNALED, and no queue row (G5: rejection is visible history)", async () => {
    const s = await startStack();
    const res = await post(s.port, `/v1/agents/${AGENT}/messages`, SCHEDULER_BODY);
    expect(res.status).toBe(401);
    const rejects = s.db
      .prepare("SELECT COUNT(*) AS n FROM turn_events WHERE kind = 'ingress_rejected'")
      .get() as { n: number };
    expect(rejects.n).toBe(1);
    const rows = s.db.prepare("SELECT COUNT(*) AS n FROM turn_queue").get() as { n: number };
    expect(rows.n).toBe(0);
  });

  it("a wrong secret → 401; an unknown agent → 404 with a body; both journaled", async () => {
    const s = await startStack();
    const bad = await post(s.port, `/v1/agents/${AGENT}/messages`, SCHEDULER_BODY, {
      authorization: "Bearer nope",
    });
    expect(bad.status).toBe(401);
    const unknown = await post(s.port, "/v1/agents/ag-nobody/messages", SCHEDULER_BODY, AUTH);
    expect(unknown.status).toBe(404);
    expect(String(unknown.body.error)).toContain("ag-nobody");
    const rejects = s.db
      .prepare("SELECT COUNT(*) AS n FROM turn_events WHERE kind = 'ingress_rejected'")
      .get() as { n: number };
    expect(rejects.n).toBe(2);
  });

  it("a worker WITHOUT a secret refuses to serve ingress at all (fail closed)", async () => {
    server = new MockAppServer();
    const url = await server.start();
    const dir = mkdtempSync(join(tmpdir(), "continuity-ingress-nosecret-"));
    const { db } = openStateDb(dir);
    const worker = new WorkerDaemon({
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
      ingressPort: 0,
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
      reconnect: FAST_RECONNECT,
    });
    await expect(worker.start()).rejects.toThrow(/shared secret/);
    worker.stop();
  });
});
