/**
 * Integration tests: ContinuityCore ⇄ MockAppServer over a real WS socket.
 * Deterministic and offline — no live server required.
 */

import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ContinuityCore } from "../src/index.js";
import { writePointer } from "../src/pointer.js";
import type { RenderEvent } from "../src/stream.js";
import { MockAppServer } from "./helpers/mockServer.js";

const AGENT = "agent-local-3898b33a";
const CONV = "local-conv-continuity-uuid";

async function pointerFile(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "continuity-core-"));
  const path = join(dir, "pointer.json");
  await writePointer(path, { agentId: AGENT, conversationId: CONV, label: "MC" });
  return path;
}

function waitFor(pred: () => boolean, timeoutMs = 3000): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = (): void => {
      if (pred()) {
        resolve();
        return;
      }
      if (Date.now() - start > timeoutMs) {
        reject(new Error("waitFor timed out"));
        return;
      }
      setTimeout(tick, 10);
    };
    tick();
  });
}

describe("ContinuityCore integration", () => {
  let server: MockAppServer;
  let url: string;
  let cores: ContinuityCore[];

  beforeEach(async () => {
    cores = [];
  });
  afterEach(async () => {
    for (const c of cores) c.stop();
    await server?.stop();
  });

  async function makeCore(
    over: Partial<ConstructorParameters<typeof ContinuityCore>[0]> = {},
  ): Promise<{
    core: ContinuityCore;
    events: RenderEvent[];
  }> {
    const path = await pointerFile();
    const core = new ContinuityCore({
      pointerPath: path,
      url,
      reconnectDelayMs: 20,
      openTimeoutMs: 2000,
      helloTimeoutMs: 2000,
      rpcTimeoutMs: 2000,
      ...over,
    });
    cores.push(core);
    const events: RenderEvent[] = [];
    core.onRender((e) => events.push(e));
    return { core, events };
  }

  it("version gate: a drifted server under refuse policy aborts connect", async () => {
    server = new MockAppServer({ serverVersion: "0.31.0" });
    url = await server.start();
    const { core } = await makeCore({ versionPolicy: "refuse", maxReconnectAttempts: 0 });
    await expect(core.start()).rejects.toThrow(/0\.31\.0 not in validated set/);
    // The gate ran BEFORE runtime_start — no runtime was started on the drifted server.
    expect(server.received.some((m) => m.type === "app_server_info")).toBe(true);
    expect(server.received.some((m) => m.type === "runtime_start")).toBe(false);
  });

  it("version gate: a drifted server under warn policy connects but warns", async () => {
    server = new MockAppServer({ serverVersion: "0.31.0" });
    url = await server.start();
    const warns: string[] = [];
    const { core, events } = await makeCore({
      versionPolicy: "warn",
      onWarn: (m) => warns.push(m),
    });
    await core.start();
    core.send("hello");
    await waitFor(() => events.some((e) => e.type === "turn_finished"));
    expect(warns.some((w) => /letta_code_version 0\.31\.0 not in validated set/.test(w))).toBe(
      true,
    );
  });

  it("version gate: a server too old to answer app_server_info warns but still connects", async () => {
    server = new MockAppServer({ omitAppServerInfo: true });
    url = await server.start();
    const warns: string[] = [];
    const { core, events } = await makeCore({
      serverInfoTimeoutMs: 150,
      onWarn: (m) => warns.push(m),
    });
    await core.start();
    core.send("hello");
    await waitFor(() => events.some((e) => e.type === "turn_finished"));
    expect(warns.some((w) => /app_server_info unavailable/.test(w))).toBe(true);
  });

  it("version gate: a server missing a required capability aborts connect under warn policy", async () => {
    server = new MockAppServer({ capabilities: { conversation_management: false } });
    url = await server.start();
    const { core } = await makeCore({ versionPolicy: "warn", maxReconnectAttempts: 0 });
    await expect(core.start()).rejects.toThrow(/conversation_management/);
  });

  it("happy path: send a turn, render stream_delta → turn_finished", async () => {
    server = new MockAppServer();
    url = await server.start();
    const { core, events } = await makeCore();
    await core.start();
    core.send("hello");
    await waitFor(() => events.some((e) => e.type === "turn_finished"));
    const delta = events.find((e) => e.type === "delta");
    expect(delta?.text).toBe("OK");
    expect(events.some((e) => e.type === "turn_start")).toBe(true);
  });

  it("a FOREIGN turn (injected by another client) renders on this client's single stream", async () => {
    server = new MockAppServer();
    url = await server.start();
    const { core: observer, events } = await makeCore();
    await observer.start();
    // Another surface injects a turn on the same {agent, conversation}.
    server.injectForeignTurn({ agent_id: AGENT, conversation_id: CONV }, "run-foreign", [
      { id: "letta-msg-F", messageType: "assistant_message", text: "from elsewhere" },
    ]);
    await waitFor(() => events.some((e) => e.type === "turn_finished"));
    const delta = events.find((e) => e.type === "delta");
    expect(delta?.text).toBe("from elsewhere");
    expect(delta?.runId).toBe("run-foreign");
  });

  it("conversation_list / conversation_create RPCs round-trip (request_id-keyed)", async () => {
    server = new MockAppServer({
      conversations: [
        {
          id: "c-1",
          agent_id: AGENT,
          archived: false,
          archived_at: null,
          created_at: "x",
          updated_at: "y",
        },
      ],
    });
    url = await server.start();
    const { core } = await makeCore();
    await core.start();
    const list = await core.conversationList();
    expect(list[0]?.id).toBe("c-1");
    const created = await core.conversationCreate("New");
    expect(created?.id).toMatch(/^local-conv-new-/);
  });

  it("concurrent sends from two cores are server-serialized — both turns complete, no loss", async () => {
    server = new MockAppServer();
    url = await server.start();
    const { core: a } = await makeCore();
    const { core: b, events: bEvents } = await makeCore();
    await a.start();
    await b.start();
    // b observes everything; a and b both inject at once.
    a.send("first");
    b.send("second");
    await waitFor(() => bEvents.filter((e) => e.type === "turn_finished").length >= 2, 4000);
    const runIds = new Set(bEvents.filter((e) => e.type === "turn_finished").map((e) => e.runId));
    expect(runIds.size).toBe(2); // two distinct serialized runs, neither dropped
  });

  it("approval fails CLOSED: the injecting client auto-denies; an observer does not respond", async () => {
    server = new MockAppServer({ approvalMode: true });
    url = await server.start();
    const { core: injector } = await makeCore();
    const { core: observer } = await makeCore();
    await injector.start();
    await observer.start();
    injector.send("do a risky thing");
    // The injector must auto-send an approval_send=deny; the turn must resolve, not hang.
    await waitFor(() =>
      server.received.some((m) => m.type === "approval_send" && m.decision === "deny"),
    );
    const approvals = server.received.filter((m) => m.type === "approval_send");
    expect(approvals).toHaveLength(1); // exactly one responder (the injector), not the observer
    expect(approvals[0]?.decision).toBe("deny");
  });

  it("reconnect + message-id catch-up: no duplicate of a snapshot message, no loss of a new one", async () => {
    // Snapshot (what the server returns on conversation_messages_list after reconnect)
    // contains the already-rendered message A.
    server = new MockAppServer({ messagesSnapshot: [{ id: "letta-msg-A" }] });
    url = await server.start();
    const { core, events } = await makeCore();
    await core.start();
    await waitFor(() => core.state === "connected");

    // Render message A live (pre-disconnect).
    server.injectForeignTurn({ agent_id: AGENT, conversation_id: CONV }, "run-A", [
      { id: "letta-msg-A", messageType: "assistant_message", text: "A" },
    ]);
    await waitFor(() => events.some((e) => e.type === "delta" && e.messageId === "letta-msg-A"));

    // Watchdog stall-restart drops all sockets at once → core reconnects + catches up.
    server.dropAllConnections();
    // wait until we've cycled back to connected (post-reconnect, liveDedup seeded from snapshot)
    let reconnected = false;
    core.onConnectionState((s, prev) => {
      if (s === "connected" && prev === "reconnecting") reconnected = true;
    });
    await waitFor(() => reconnected, 5000);

    // After reconnect: server replays A (same id) AND streams a genuinely new message B.
    server.injectForeignTurn({ agent_id: AGENT, conversation_id: CONV }, "run-A2", [
      { id: "letta-msg-A", messageType: "assistant_message", text: "A-replay" },
    ]);
    server.injectForeignTurn({ agent_id: AGENT, conversation_id: CONV }, "run-B", [
      { id: "letta-msg-B", messageType: "assistant_message", text: "B" },
    ]);
    await waitFor(() => events.some((e) => e.type === "delta" && e.messageId === "letta-msg-B"));

    const aRenders = events.filter((e) => e.type === "delta" && e.messageId === "letta-msg-A");
    const bRenders = events.filter((e) => e.type === "delta" && e.messageId === "letta-msg-B");
    expect(aRenders).toHaveLength(1); // A rendered exactly once (replay deduped) — NO duplicate
    expect(bRenders.length).toBeGreaterThanOrEqual(1); // B rendered — NO loss
  });

  it("surfaces reconnecting state on a mid-session disconnect", async () => {
    server = new MockAppServer();
    url = await server.start();
    const { core } = await makeCore();
    const states: string[] = [];
    core.onConnectionState((s) => states.push(s));
    await core.start();
    await waitFor(() => core.state === "connected");
    server.dropAllConnections();
    await waitFor(() => states.includes("reconnecting"));
    await waitFor(() => core.state === "connected", 5000);
    expect(states).toContain("reconnecting");
  });

  it("bounded reconnect: a server that stays down ends in disconnected after maxReconnectAttempts, no storm", async () => {
    server = new MockAppServer();
    url = await server.start();
    const { core } = await makeCore({ maxReconnectAttempts: 3, reconnectDelayMs: 15 });
    await core.start();
    await waitFor(() => core.state === "connected");
    // Take the server fully down (not just drop sockets) so every reconnect attempt FAILS.
    await server.stop();
    // Must converge to disconnected within a bounded number of attempts — never loop forever.
    await waitFor(() => core.state === "disconnected", 6000);
    expect(core.state).toBe("disconnected");
  });
});
