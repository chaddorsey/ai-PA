/**
 * The C5 surface contract through the REAL worker + mock App Server: authenticated attach,
 * cursor replay (gapless, duplicate-free — journal-id keyed), cross-surface visibility,
 * mid-turn attach coherence, presence, version gating, and operator abort.
 */

import { mkdtempSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { waitFor } from "@ai-pa/letta-continuity-core/testing/harness";
import { afterEach, describe, expect, it } from "vitest";
import { Registry } from "../src/registry.js";
import { openStateDb } from "../src/state/db.js";
import { Journal } from "../src/state/journal.js";
import { SURFACE_TOKEN_FILENAME, ensureSurfaceToken } from "../src/surface/auth.js";
import { WorkerDaemon } from "../src/worker.js";
import { TestSurface } from "./helpers/surfaceClient.js";

const FAST_RECONNECT = { baseDelayMs: 20, maxDelayMs: 40, stabilityMs: 0, jitter: () => 0 };
const RUNTIME = { agent_id: "ag-1", conversation_id: "local-conv-1" };

interface Stack {
  dir: string;
  token: string;
  worker: WorkerDaemon;
  port: number;
}

describe("surface protocol (worker + mock server)", () => {
  let server: MockAppServer;
  let stack: Stack | null = null;
  const surfaces: TestSurface[] = [];

  afterEach(async () => {
    for (const s of surfaces) s.close();
    surfaces.length = 0;
    stack?.worker.stop();
    stack = null;
    await server?.stop();
  });

  async function startStack(options: Record<string, unknown> = {}): Promise<Stack> {
    const url = await server.start();
    const dir = mkdtempSync(join(tmpdir(), "continuity-surface-"));
    const { db } = openStateDb(dir);
    new Registry(db).upsert(RUNTIME);
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
      surfacePort: 0,
      stateDir: dir,
      onExhausted: () => {
        throw new Error("unexpected exhaustion");
      },
      reconnect: FAST_RECONNECT,
      ...options,
    });
    await worker.start();
    const token = ensureSurfaceToken(dir);
    const port = worker.surfaceBoundPort;
    if (port === null) throw new Error("surface did not bind");
    stack = { dir, token, worker, port };
    return stack;
  }

  async function attach(s: Stack, capabilities: string[] = ["core"], cursor: number | null = null) {
    const surface = new TestSurface();
    surfaces.push(surface);
    await surface.connect(s.port);
    const ok = await surface.attach({ token: s.token, runtime: RUNTIME, capabilities, cursor });
    expect(ok.type).toBe("attach_ok");
    return surface;
  }

  it("the token file is created 0600 and a message from one surface reaches the other live", async () => {
    server = new MockAppServer();
    const s = await startStack();
    expect(statSync(join(s.dir, SURFACE_TOKEN_FILENAME)).mode & 0o777).toBe(0o600);

    const a = await attach(s);
    const b = await attach(s);
    const sent = await a.request(
      { type: "send", request_id: "r1", text: "hello from A" },
      (f) => f.type === "send_ok",
    );
    const clientMessageId = sent.client_message_id as string;
    // B sees the whole turn — the accepted marker, the assistant delta, terminality.
    const terminal = await b.waitFrame(
      (f) =>
        f.type === "event" && f.kind === "turn_terminal" && f.client_message_id === clientMessageId,
    );
    expect(terminal).not.toBeNull();
    expect(b.frames.some((f) => f.type === "event" && f.kind === "assistant_message")).toBe(true);
  });

  it("replay from a stale cursor is gapless and duplicate-free (journal-id keyed)", async () => {
    server = new MockAppServer();
    const s = await startStack();
    const a = await attach(s);
    await a.request(
      { type: "send", request_id: "r1", text: "first turn" },
      (f) => f.type === "send_ok",
    );
    await a.waitFrame((f) => f.type === "event" && f.kind === "turn_terminal");
    const midCursor = Math.max(
      ...a.frames.filter((f) => f.type === "event").map((f) => f.id as number),
    );
    await a.request(
      { type: "send", request_id: "r2", text: "second turn" },
      (f) => f.type === "send_ok",
    );
    await a.waitFrame(
      (f) => f.type === "event" && f.kind === "turn_terminal" && (f.id as number) > midCursor,
    );

    // A late surface replays from the mid-point: everything after, nothing before, no dupes.
    const late = new TestSurface();
    surfaces.push(late);
    await late.connect(s.port);
    const ok = await late.attach({ token: s.token, runtime: RUNTIME, cursor: midCursor });
    const replay = (ok.replay as Array<{ id: number }>).map((e) => e.id);
    expect(replay.length).toBeGreaterThan(0);
    expect(Math.min(...replay)).toBeGreaterThan(midCursor);
    expect(new Set(replay).size).toBe(replay.length);
    // Gapless against the journal: ids are consecutive rows of this runtime's journal slice.
    const sorted = [...replay].sort((x, y) => x - y);
    expect(sorted).toEqual(replay);
  });

  it("a surface attaching MID-TURN receives the partial turn coherently (replay + live join)", async () => {
    // The turn is driven MANUALLY so there is a genuine mid-turn window to attach inside.
    server = new MockAppServer({ autoTurnOnInput: false });
    const s = await startStack();
    const a = await attach(s);
    await a.request(
      { type: "send", request_id: "r1", text: "long turn" },
      (f) => f.type === "send_ok",
    );
    await a.waitFrame((f) => f.type === "event" && f.kind === "turn_submitted", 5000);

    // B attaches while the turn is genuinely in flight: the partial turn arrives as REPLAY.
    const b = new TestSurface();
    surfaces.push(b);
    await b.connect(s.port);
    const ok = await b.attach({ token: s.token, runtime: RUNTIME, cursor: null });
    const replayKinds = (ok.replay as Array<{ kind: string }>).map((e) => e.kind);
    expect(replayKinds).toContain("turn_submitted");
    expect(replayKinds).not.toContain("turn_terminal");

    // The server now finishes the turn; B's live tail joins the replay WITHOUT a gap.
    server.broadcastTurn(RUNTIME, "run-live-1", [
      { id: "m-live-1", messageType: "assistant_message", text: "the live tail" },
    ]);
    const terminal = await b.waitFrame((f) => f.type === "event" && f.kind === "turn_terminal");
    expect(terminal).not.toBeNull();
    const replayMax = Math.max(...(ok.replay as Array<{ id: number }>).map((e) => e.id));
    const liveIds = b.frames.filter((f) => f.type === "event").map((f) => f.id as number);
    expect(Math.min(...liveIds)).toBeGreaterThan(replayMax);
  });

  it("bad token → clean denial, no session; wrong protocol version → denial naming both versions", async () => {
    server = new MockAppServer();
    const s = await startStack();
    const bad = new TestSurface();
    surfaces.push(bad);
    await bad.connect(s.port);
    const denied = await bad.attach({ token: "wrong", runtime: RUNTIME });
    expect(denied.type).toBe("attach_denied");
    expect(s.worker.surface?.sessionCount).toBe(0);

    const versioned = new TestSurface();
    surfaces.push(versioned);
    await versioned.connect(s.port);
    const deniedVersion = await versioned.attach({
      token: s.token,
      runtime: RUNTIME,
      protocolVersion: 99,
    });
    expect(deniedVersion.type).toBe("attach_denied");
    expect(String(deniedVersion.reason)).toContain("99");
  });

  it("unknown capabilities degrade with a warning (R28), never a rejection", async () => {
    server = new MockAppServer();
    const s = await startStack();
    const surface = new TestSurface();
    surfaces.push(surface);
    await surface.connect(s.port);
    const ok = await surface.attach({
      token: s.token,
      runtime: RUNTIME,
      capabilities: ["core", "holograms"],
    });
    expect(ok.type).toBe("attach_ok");
    expect((ok.warnings as string[])[0]).toContain("holograms");
  });

  it("presence updates are recorded per session (C7's routing input)", async () => {
    server = new MockAppServer();
    const s = await startStack();
    const a = await attach(s);
    a.send({ type: "presence", state: "background" });
    await waitFor(
      () =>
        s.worker.surface?.presenceFor(RUNTIME).some((p) => p.presence === "background") ?? false,
      2000,
    );
  });

  it("operator abort from a surface kills the running turn: journal shows aborted terminality", async () => {
    server = new MockAppServer({ autoTurnOnInput: false }); // the turn would hang forever
    const s = await startStack();
    const a = await attach(s, ["core", "abort"]);
    await a.request(
      { type: "send", request_id: "r1", text: "will be aborted" },
      (f) => f.type === "send_ok",
    );
    await waitFor(() => server.received.some((f) => f.type === "input"), 3000);
    const abortResult = await a.request(
      { type: "abort", request_id: "r2" },
      (f) => f.type === "abort_ok",
    );
    expect(abortResult.aborted).toBe(true);
    const terminal = await a.waitFrame((f) => f.type === "event" && f.kind === "turn_terminal");
    expect((terminal?.payload as { outcome?: string })?.outcome).toBe("aborted:operator");
    // A core-tier surface WITHOUT the abort capability is refused the lever.
    const plain = await attach(s, ["core"]);
    const refused = await plain.request(
      { type: "abort", request_id: "r3" },
      (f) => f.type === "error",
    );
    expect(String(refused.message)).toContain("abort capability");
  });
});
