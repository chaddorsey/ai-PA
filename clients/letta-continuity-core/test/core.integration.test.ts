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
import { __resetRequestCounter } from "../src/protocol.js";
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

  it("a core built WITHOUT explicit timeouts still connects (undefined must not defeat defaults)", async () => {
    // Regression: ContinuityCore forwards `openTimeoutMs: this.config.openTimeoutMs`, so an
    // unconfigured core passes an explicit `undefined`. Spreading that over the defaults gave
    // `setTimeout(fn, undefined)` — a 0 ms bound that aborted every connect. Every other test
    // here sets explicit timeouts, so only a default-constructed core catches it.
    server = new MockAppServer();
    url = await server.start();
    const path = await pointerFile();
    const core = new ContinuityCore({ pointerPath: path, url });
    cores.push(core);
    const events: RenderEvent[] = [];
    core.onRender((e) => events.push(e));

    await core.start();
    core.send("hello");
    await waitFor(() => events.some((e) => e.type === "turn_finished"));
  });

  describe("connection and RPC error semantics", () => {
    it("an RPC issued while the socket is closed throws, leaks no pending entry, and never rejects unhandled", async () => {
      // Regression: registerPending-then-send left a live timer on a promise nobody held, whose
      // later rejection is an unhandled rejection — fatal under Node's default policy, during a
      // reconnect. Ordering is now send-then-register.
      server = new MockAppServer();
      url = await server.start();
      const { core } = await makeCore({ rpcTimeoutMs: 200, maxReconnectAttempts: 0 });
      await core.start();

      const unhandled: unknown[] = [];
      const onUnhandled = (r: unknown): void => {
        unhandled.push(r);
      };
      process.on("unhandledRejection", onUnhandled);
      try {
        // Drop the socket server-side but leave `core.ws` in place, so the RPC actually reaches
        // rawSend. (core.stop() would null `ws` and short-circuit before the path under test.)
        server.dropAllConnections();
        await waitFor(() => core.state !== "connected");

        await expect(core.conversationList()).rejects.toThrow(/socket not open/);
        // Well past the RPC timeout an orphaned entry would have carried.
        await new Promise((r) => setTimeout(r, 400));
        expect(unhandled).toEqual([]);
      } finally {
        process.off("unhandledRejection", onUnhandled);
      }
    });

    it("a response frame that fails validation rejects its RPC with the drift error, not a timeout", async () => {
      server = new MockAppServer({ suppressResponsesFor: ["conversation_list"] });
      url = await server.start();
      const { core } = await makeCore({ rpcTimeoutMs: 5000 });
      await core.start();

      const started = Date.now();
      const pending = core.conversationList();
      // Same request_id the client just used, correct type, but `conversations` renamed —
      // the shape a server-side field rename produces.
      await waitFor(() => server.received.some((m) => m.type === "conversation_list"));
      const rid = server.received.filter((m) => m.type === "conversation_list").at(-1)
        ?.request_id as string;
      server.sendRaw({
        type: "conversation_list_response",
        request_id: rid,
        success: true,
        threads: [],
      });

      await expect(pending).rejects.toThrow(/conversations/);
      // The point of the fix: it fails fast with the real reason, not after the RPC budget.
      expect(Date.now() - started).toBeLessThan(2000);
    });

    it("--strict-version refuses a server whose app_server_info drifts", async () => {
      server = new MockAppServer({ driftAppServerInfo: true });
      url = await server.start();
      const { core } = await makeCore({ versionPolicy: "refuse", maxReconnectAttempts: 0 });
      await expect(core.start()).rejects.toThrow(/refusing to attach/);
    });

    it("a server too old to answer app_server_info still connects under refuse policy (warns)", async () => {
      // "No answer" is a genuinely different class from "answered wrong": it means the build
      // predates the command. Refusing here would lock the client out of older servers.
      server = new MockAppServer({ omitAppServerInfo: true });
      url = await server.start();
      const warns: string[] = [];
      const { core } = await makeCore({
        versionPolicy: "refuse",
        serverInfoTimeoutMs: 150,
        onWarn: (m) => warns.push(m),
      });
      await core.start();
      expect(warns.some((w) => /app_server_info unavailable/.test(w))).toBe(true);
    });
  });

  it("two cores emit disjoint correlation ids even with the counter reset between them", async () => {
    // Simulates two client PROCESSES: each starts its counter at zero. Before per-instance
    // nonces this produced byte-identical client_message_ids, so each core recognised the
    // other's broadcast dequeue notice as its own.
    server = new MockAppServer();
    url = await server.start();
    const { core: a } = await makeCore();
    await a.start();
    a.send("from A");
    await waitFor(() => server.received.some((m) => m.type === "input"));

    __resetRequestCounter();
    const { core: b } = await makeCore();
    await b.start();
    b.send("from B");
    await waitFor(() => server.received.filter((m) => m.type === "input").length >= 2);

    const cms = server.received
      .filter((m) => m.type === "input")
      .map((m) => (m.payload as { client_message_id: string }).client_message_id);
    expect(cms).toHaveLength(2);
    expect(new Set(cms).size).toBe(2); // disjoint — the whole point
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

  /**
   * Followup finding #1: the old outstanding-turn COUNTER passed the test above while the
   * guarantee was weak, because that test never puts a foreign turn in flight. These two
   * exercise the concurrent case in both directions.
   */
  it("approval: a FOREIGN turn finishing does not silence the injector's own deny", async () => {
    server = new MockAppServer({ approvalMode: true });
    url = await server.start();
    const { core: injector } = await makeCore();
    await injector.start();

    injector.send("do a risky thing");
    await waitFor(() => injector.ownershipSnapshot().owned.length === 1);
    const myRun = injector.ownershipSnapshot().owned[0] as string;

    // A peer's turn completes on the same conversation. A counter would zero here and the
    // injector would then fail to answer its OWN approval → both surfaces hang.
    server.broadcastTurn({ agent_id: AGENT, conversation_id: CONV }, "local-run-foreign", [
      { id: "letta-msg-FGN", messageType: "assistant_message", text: "elsewhere" },
    ]);
    await waitFor(() => server.received.some((m) => m.type === "approval_send"));

    expect(injector.ownershipSnapshot().owned).toEqual([myRun]);
    const approvals = server.received.filter((m) => m.type === "approval_send");
    expect(approvals).toHaveLength(1);
    expect(approvals[0]?.decision).toBe("deny");
  });

  it("approval: an observer with its own turn in flight still ignores a FOREIGN approval", async () => {
    // The observer's send is QUEUED behind a peer's in-flight turn, so its claim is NOT armed
    // — then the peer's turn hits an approval. A counter would be >0 here and wrongly answer
    // for the peer. (Queued is the only realistic shape: the server serializes turns, so an
    // "started" ack means our own run is the one running, not a peer's.)
    server = new MockAppServer({ autoTurnOnInput: false, inputDisposition: "queued" });
    url = await server.start();
    const { core: observer } = await makeCore();
    await observer.start();
    observer.send("my own unrelated turn");
    await waitFor(() => server.received.some((m) => m.type === "input"));

    // A run that is demonstrably NOT ours: announced, then gated on approval.
    server.broadcastForeignApproval({ agent_id: AGENT, conversation_id: CONV }, "local-run-peer");
    await new Promise((r) => setTimeout(r, 150));

    expect(server.received.filter((m) => m.type === "approval_send")).toHaveLength(0);
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
