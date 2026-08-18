/**
 * The minimal web slice (2026-08-17 handoff, session 2): the surface's HTTP handler serves
 * the static page, and the WS endpoint tolerates a tailscale-serve mount prefix. The
 * surface protocol itself is covered by surface.protocol.test.ts — this file pins only the
 * HTTP/GET + prefixed-upgrade additions.
 */

import { mkdtempSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { afterEach, describe, expect, it } from "vitest";
import { Registry } from "../src/registry.js";
import { openStateDb } from "../src/state/db.js";
import { Journal } from "../src/state/journal.js";
import { ensureSurfaceToken } from "../src/surface/auth.js";
import { WorkerDaemon } from "../src/worker.js";

const require = createRequire(import.meta.url);
const { WebSocket } = require("ws") as typeof import("ws");

const FAST_RECONNECT = { baseDelayMs: 20, maxDelayMs: 40, stabilityMs: 0, jitter: () => 0 };
const RUNTIME = { agent_id: "ag-1", conversation_id: "local-conv-1" };

describe("surface web slice (page + prefixed WS)", () => {
  let server: MockAppServer;
  let worker: WorkerDaemon | null = null;

  afterEach(async () => {
    worker?.stop();
    worker = null;
    await server?.stop();
  });

  async function startStack(): Promise<{ port: number; token: string }> {
    server = new MockAppServer();
    const url = await server.start();
    const dir = mkdtempSync(join(tmpdir(), "continuity-web-"));
    const { db } = openStateDb(dir);
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
    return { port, token: ensureSurfaceToken(dir) };
  }

  it("GET / serves the page; other paths still refuse loudly", async () => {
    const { port } = await startStack();

    const page = await fetch(`http://127.0.0.1:${port}/`);
    expect(page.status).toBe(200);
    expect(page.headers.get("content-type")).toContain("text/html");
    const html = await page.text();
    expect(html).toContain("<title>Kinara</title>");
    expect(html).toContain("surface"); // the WS URL derivation lives in the page

    // A mounted-prefix directory path serves the same page (tailscale set-path pass-through).
    const mounted = await fetch(`http://127.0.0.1:${port}/pa/`);
    expect(mounted.status).toBe(200);

    const other = await fetch(`http://127.0.0.1:${port}/tickets`);
    expect(other.status).toBe(501);

    // agent-info validates its parameter immediately (mount-prefix tolerant).
    const noParam = await fetch(`http://127.0.0.1:${port}/pa/agent-info`);
    expect(noParam.status).toBe(400);
    const noParamBody = (await noParam.json()) as { error: string };
    expect(noParamBody.error).toContain("agent");
  });

  it("GET /history is token-gated (conversation content) and validates its params", async () => {
    const { port, token } = await startStack();

    const noAuth = await fetch(`http://127.0.0.1:${port}/history?agent=a&conversation=c&before=5`);
    expect(noAuth.status).toBe(401);

    const badParams = await fetch(`http://127.0.0.1:${port}/pa/history?agent=a`, {
      headers: { authorization: `Bearer ${token}` },
    });
    expect(badParams.status).toBe(400);

    const ok = await fetch(
      `http://127.0.0.1:${port}/history?agent=${RUNTIME.agent_id}&conversation=${RUNTIME.conversation_id}&before=999999`,
      { headers: { authorization: `Bearer ${token}` } },
    );
    expect(ok.status).toBe(200);
    const body = (await ok.json()) as { events: unknown[] };
    expect(Array.isArray(body.events)).toBe(true);
  });

  it("POST /agent-model is token-gated and validates its body before touching the WS", async () => {
    const { port, token } = await startStack();

    const noAuth = await fetch(`http://127.0.0.1:${port}/agent-model`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ agent_id: "a", conversation_id: "c", model: "m" }),
    });
    expect(noAuth.status).toBe(401);

    const badBody = await fetch(`http://127.0.0.1:${port}/pa/agent-model`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify({ agent_id: "a" }),
    });
    expect(badBody.status).toBe(400);
    const badBodyJson = (await badBody.json()) as { error: string };
    expect(badBodyJson.error).toContain("model");
  });

  it("WS attach works under a mount prefix, and a non-surface upgrade path is destroyed", async () => {
    const { port, token } = await startStack();

    // Prefixed path — what arrives if tailscale serve passes the mount path through.
    const attachOk = await new Promise<Record<string, unknown>>((resolve, reject) => {
      const socket = new WebSocket(`ws://127.0.0.1:${port}/pa/surface`);
      const timer = setTimeout(() => reject(new Error("attach timeout")), 5_000);
      socket.on("open", () =>
        socket.send(
          JSON.stringify({
            type: "attach",
            token,
            protocol_version: 1,
            capabilities: ["core", "notify"],
            runtime: RUNTIME,
            cursor: null,
          }),
        ),
      );
      socket.on("message", (d) => {
        clearTimeout(timer);
        socket.close();
        resolve(JSON.parse(d.toString()) as Record<string, unknown>);
      });
      socket.on("error", (e) => {
        clearTimeout(timer);
        reject(e);
      });
    });
    expect(attachOk.type).toBe("attach_ok");

    // A WS upgrade against a non-surface path must not reach the protocol at all.
    const refused = await new Promise<boolean>((resolve) => {
      const socket = new WebSocket(`ws://127.0.0.1:${port}/definitely-not`);
      const timer = setTimeout(() => resolve(false), 5_000);
      socket.on("error", () => {
        clearTimeout(timer);
        resolve(true);
      });
      socket.on("open", () => {
        clearTimeout(timer);
        socket.close();
        resolve(false);
      });
    });
    expect(refused).toBe(true);
  });
});
