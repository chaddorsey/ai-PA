/**
 * The direct lane (C8): `@alias` resolves BEFORE any model call, exchanges journal in the
 * SPECIALIST's thread with zero Kinara involvement, replies render inline on the route-origin
 * surface with attribution, bindings route everything until unbound, Kinara authors routes via
 * manage_routes (journaled author), and a routing miss is a visible error — never a model call.
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MockAppServer } from "@ai-pa/letta-continuity-core/testing";
import { waitFor } from "@ai-pa/letta-continuity-core/testing/harness";
import { afterEach, describe, expect, it } from "vitest";
import { TurnJournal } from "../src/journal.js";
import { Registry } from "../src/registry.js";
import { RouteMissError } from "../src/routing/routes.js";
import { openStateDb } from "../src/state/db.js";
import { Journal } from "../src/state/journal.js";
import { ensureSurfaceToken } from "../src/surface/auth.js";
import { WorkerDaemon } from "../src/worker.js";
import { TestSurface } from "./helpers/surfaceClient.js";

const FAST_RECONNECT = { baseDelayMs: 20, maxDelayMs: 40, stabilityMs: 0, jitter: () => 0 };
const KINARA = { agent_id: "ag-kinara", conversation_id: "local-conv-k" };
const CAL = { agent_id: "ag-calendar", conversation_id: "local-conv-cal" };

interface Stack {
  worker: WorkerDaemon;
  server: MockAppServer;
  surfacePort: number;
  token: string;
  turnJournal: TurnJournal;
  db: ReturnType<typeof openStateDb>["db"];
}

describe("direct-lane routing", () => {
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
    const dir = mkdtempSync(join(tmpdir(), "continuity-routes-"));
    const { db } = openStateDb(dir);
    const registry = new Registry(db);
    registry.upsert({ ...KINARA, label: "kinara", origin: { default: true } });
    registry.upsert({ ...CAL, label: "calendar", temp: "cold" }); // cold on purpose: R26 warms it
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
      digestSweepMs: 100_000, // digests are the OTHER test file's subject
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

  async function attachKinara(s: Stack, capabilities = ["core", "direct"]): Promise<TestSurface> {
    const surface = new TestSurface();
    surfaces.push(surface);
    await surface.connect(s.surfacePort);
    const ok = await surface.attach({ token: s.token, runtime: KINARA, capabilities });
    expect(ok.type).toBe("attach_ok");
    return surface;
  }

  it("@calendar routes direct: specialist turn, ZERO Kinara turns, inline attributed reply, cold→hot", async () => {
    const s = await startStack();
    s.worker.routes.set("calendar", CAL.agent_id, CAL.conversation_id, "operator-cli");
    const surface = await attachKinara(s);
    const coreOnly = await attachKinara(s, ["core"]); // no `direct` capability

    const sent = await surface.request(
      { type: "send", request_id: "r1", text: "@calendar check tomorrow" },
      (f) => f.type === "send_ok",
    );
    expect((sent.routed_to as { agent_id: string }).agent_id).toBe(CAL.agent_id);
    const cm = sent.client_message_id as string;
    await waitFor(() => s.worker.pipeline.rowFor(cm)?.state === "terminal", 5000);

    // The exchange lives in the SPECIALIST's thread; the stripped text is what was submitted.
    const row = s.worker.pipeline.rowFor(cm);
    expect(row?.agent_id).toBe(CAL.agent_id);
    expect(row?.content).toBe("check tomorrow");
    // ZERO model hops before the specialist's own turn: no Kinara-thread turn exists at all.
    const kinaraTurns = s.db
      .prepare("SELECT COUNT(*) AS n FROM turn_queue WHERE agent_id = ?")
      .get(KINARA.agent_id) as { n: number };
    expect(kinaraTurns.n).toBe(0);
    // R26: the cold specialist was warmed by the route.
    expect(new Registry(s.db).get(CAL)?.temp).toBe("hot");

    // The reply rendered INLINE on the route-origin surface, attributed.
    const foreign = await surface.waitFrame(
      (f) => f.type === "foreign_event" && (f.event as { kind?: string })?.kind === "turn_terminal",
      5000,
    );
    expect(foreign?.route).toBe("calendar");
    expect((foreign?.specialist as { agent_id: string }).agent_id).toBe(CAL.agent_id);
    expect(
      surface.frames.some(
        (f) =>
          f.type === "foreign_event" &&
          (f.event as { kind?: string })?.kind === "assistant_message",
      ),
    ).toBe(true);
    // R28: the capability gates the channel — a core-only surface never sees foreign events.
    expect(coreOnly.frames.some((f) => f.type === "foreign_event")).toBe(false);
  });

  it("bind routes plain messages until unbind restores the Kinara lane", async () => {
    const s = await startStack();
    s.worker.routes.set("calendar", CAL.agent_id, CAL.conversation_id, "operator-cli");
    const surface = await attachKinara(s);

    await surface.request(
      { type: "bind", request_id: "b1", alias: "calendar" },
      (f) => f.type === "bind_ok",
    );
    const bound = await surface.request(
      { type: "send", request_id: "r1", text: "plain line while bound" },
      (f) => f.type === "send_ok",
    );
    expect((bound.routed_to as { agent_id: string } | undefined)?.agent_id).toBe(CAL.agent_id);

    await surface.request({ type: "unbind", request_id: "u1" }, (f) => f.type === "unbind_ok");
    const unbound = await surface.request(
      { type: "send", request_id: "r2", text: "plain line after unbind" },
      (f) => f.type === "send_ok",
    );
    expect(unbound.routed_to).toBeUndefined();
    const cmUnbound = unbound.client_message_id as string;
    expect(s.worker.pipeline.rowFor(cmUnbound)?.agent_id).toBe(KINARA.agent_id);

    // The audit trail names every mutation and its author (R25).
    const audit = s.turnJournal
      .eventsFor(KINARA)
      .filter((e) => e.kind === "route_mutation")
      .map((e) => e.payload.op);
    expect(audit).toContain("bind");
    expect(audit).toContain("unbind");
  });

  it("an explicit @address BEATS an active binding", async () => {
    const s = await startStack();
    s.worker.routes.set("calendar", CAL.agent_id, CAL.conversation_id, "operator-cli");
    s.worker.routes.set("kinara", KINARA.agent_id, KINARA.conversation_id, "operator-cli");
    const surface = await attachKinara(s);
    await surface.request(
      { type: "bind", request_id: "b1", alias: "calendar" },
      (f) => f.type === "bind_ok",
    );
    const sent = await surface.request(
      { type: "send", request_id: "r1", text: "@kinara back to you" },
      (f) => f.type === "send_ok",
    );
    expect((sent.routed_to as { agent_id: string }).agent_id).toBe(KINARA.agent_id);
  });

  it("an address matching no route is a VISIBLE error and nothing is submitted", async () => {
    const s = await startStack();
    const surface = await attachKinara(s);
    const err = await surface.request(
      { type: "send", request_id: "r1", text: "@nobody hello" },
      (f) => f.type === "error",
    );
    expect(String(err.message)).toContain("@nobody");
    const rows = s.db.prepare("SELECT COUNT(*) AS n FROM turn_queue").get() as { n: number };
    expect(rows.n).toBe(0);
  });

  it("Kinara authors a route via manage_routes: journaled author, active WITHOUT restart", async () => {
    const s = await startStack();
    s.server.sendRaw({
      type: "external_tool_call_request",
      request_id: "ext-route-1",
      runtime: KINARA,
      tool_call_id: "call-mr-1",
      tool_name: "manage_routes",
      input: {
        op: "set",
        alias: "cal2",
        agent_id: CAL.agent_id,
        conversation_id: CAL.conversation_id,
      },
    });
    await waitFor(
      () => s.server.received.some((f) => f.type === "external_tool_call_response"),
      5000,
    );
    expect(s.worker.routes.get("cal2")?.agent_id).toBe(CAL.agent_id);
    const mutation = s.turnJournal
      .eventsFor(CAL)
      .find((e) => e.kind === "route_mutation" && e.payload.op === "set");
    expect(String(mutation?.payload.author)).toBe(`agent:${KINARA.agent_id}`);

    // …and immediately usable.
    const surface = await attachKinara(s);
    const sent = await surface.request(
      { type: "send", request_id: "r1", text: "@cal2 route me" },
      (f) => f.type === "send_ok",
    );
    expect((sent.routed_to as { agent_id: string }).agent_id).toBe(CAL.agent_id);
  });

  it("a route must point at a registry-known specialist", async () => {
    const s = await startStack();
    expect(() => s.worker.routes.set("ghost", "ag-ghost", undefined, "operator-cli")).toThrow(
      RouteMissError,
    );
  });
});
