/**
 * Properties the previous suite could not disprove.
 *
 * Every test here was written from a PROPERTY and then checked against a mutation that reverts
 * exactly one component of the fix it covers (see `tools/mutations.mjs`). That is the difference
 * from the tests these supplement: those were written from the fix, so they pinned the shape of
 * the code rather than the behaviour the code exists to produce, and thirteen single-component
 * reverts left the suite green — including one that restores a hang on every approval.
 *
 * Where a scenario needs a socket state a healthy server cannot produce on cue, it comes from the
 * doubles (`helpers/mockServer.ts`): a held close handshake, a first-connection-only failure, an
 * orphaned run, or an injected write fault.
 */

import { afterEach, describe, expect, it } from "vitest";
import { ContinuityCore } from "../src/index.js";
import type { RenderEvent } from "../src/stream.js";
import { AGENT, CONV, pointerFile, sleep, waitFor } from "./helpers/harness.js";
import { FaultyWsConnection, MockAppServer } from "./helpers/mockServer.js";

const RUNTIME = { agent_id: AGENT, conversation_id: CONV };

describe("ContinuityCore properties", () => {
  let server: MockAppServer;
  let url: string;
  const cores: ContinuityCore[] = [];

  afterEach(async () => {
    for (const c of cores) c.stop();
    cores.length = 0;
    FaultyWsConnection.reset();
    await server?.stop();
  });

  async function makeCore(
    over: Partial<ConstructorParameters<typeof ContinuityCore>[0]> = {},
  ): Promise<{ core: ContinuityCore; events: RenderEvent[]; warnings: string[] }> {
    const warnings: string[] = [];
    const core = new ContinuityCore({
      pointerPath: await pointerFile(),
      url,
      reconnectDelayMs: 20,
      openTimeoutMs: 2000,
      helloTimeoutMs: 2000,
      rpcTimeoutMs: 2000,
      onWarn: (m) => warnings.push(m),
      ...over,
    });
    cores.push(core);
    const events: RenderEvent[] = [];
    core.onRender((e) => events.push(e));
    return { core, events, warnings };
  }

  function approvalResponses(): Array<Record<string, unknown>> {
    return server.received.filter(
      (m) => m.type === "input" && (m.payload as { kind?: string }).kind === "approval_response",
    );
  }

  function controlRequest(id: string): Record<string, unknown> {
    return {
      type: "control_request",
      request_id: id,
      request: {
        subtype: "can_use_tool",
        tool_name: "Bash",
        tool_call_id: id.replace(/^perm-/, ""),
      },
      agent_id: AGENT,
      conversation_id: CONV,
    };
  }

  // ── the approval path ────────────────────────────────────────────────────

  describe("approvals", () => {
    it("a deny whose WRITE FAILED is answered again on redelivery — nobody-answers is the one fatal outcome", async () => {
      // Mutation 1 restores `answeredApprovals.add(id)` BEFORE the send. That marks an INTENT as
      // if it were a delivered answer: the server, having received nothing, re-broadcasts the
      // still-pending request, this client skips it as already answered, and the turn parks
      // forever on every attached surface. The suite could not see it because a real loopback
      // socket cannot be made to fail a write on cue — the frame that triggers the send and the
      // send itself run in the same tick. Hence the injected write fault.
      server = new MockAppServer({ autoTurnOnInput: false });
      url = await server.start();
      const { core } = await makeCore({ createConnection: FaultyWsConnection.factory });
      const errors: string[] = [];
      core.onError((e) => errors.push(e.message));
      await core.start();

      FaultyWsConnection.failSendsWith = "cannot send `input`: socket not open";
      server.sendRaw(controlRequest("perm-toolu-1"));
      await waitFor(() => errors.length > 0);
      expect(approvalResponses()).toHaveLength(0);

      // The socket recovers and the server, still holding the request, re-broadcasts it.
      FaultyWsConnection.failSendsWith = null;
      server.sendRaw(controlRequest("perm-toolu-1"));

      await waitFor(() => approvalResponses().length === 1, 3000);
      expect((approvalResponses()[0]?.payload as { request_id: string }).request_id).toBe(
        "perm-toolu-1",
      );
    });

    it("a failed deny is not reported to the user as a completed denial", async () => {
      // The other half: an approval event says "we answered". Emitting it for a write that threw
      // makes the transcript claim something that never reached the server.
      server = new MockAppServer({ autoTurnOnInput: false });
      url = await server.start();
      const { core } = await makeCore({ createConnection: FaultyWsConnection.factory });
      const approvals: string[] = [];
      const errors: string[] = [];
      core.onApproval((e) => approvals.push(e.requestId));
      core.onError((e) => errors.push(e.message));
      await core.start();

      FaultyWsConnection.failSendsWith = "cannot send `input`: socket not open";
      server.sendRaw(controlRequest("perm-toolu-2"));
      await waitFor(() => errors.length > 0);
      await sleep(50);

      expect(approvals).toEqual([]);
    });
  });

  // ── connection lifecycle ─────────────────────────────────────────────────

  describe("connection lifecycle", () => {
    it("a superseded connection's LATE close does not disturb the healthy one", async () => {
      // Mutation 5 restores the identity-free guard, which consults whatever connection is
      // CURRENT rather than the one that closed. A politely-closed socket can emit `close` long
      // after it was replaced (the ws package waits for the handshake), and the old guard then
      // saw a healthy connection that was not closed by us and scheduled a reconnect against it —
      // replacing it WITHOUT closing it, so two sockets stayed wired to routeFrame and every
      // broadcast rendered twice on two independent event_seq sequences.
      server = new MockAppServer({
        suppressFirstResponseFor: ["runtime_start"],
        holdFirstConnectionCloseAfter: "runtime_start",
      });
      url = await server.start();
      const { core } = await makeCore({ helloTimeoutMs: 200, maxReconnectAttempts: 0 });
      core.onError(() => {});

      await expect(core.start()).rejects.toThrow(/timed out/);
      // The first socket is closed BY US but its close event is held by the server.
      expect(server.connectionCount).toBe(1);

      await core.start(); // the retry attaches cleanly on a second connection
      await waitFor(() => core.state === "connected");
      const handshakes = () => server.received.filter((m) => m.type === "runtime_start").length;
      const before = handshakes();

      server.releaseCloseHandshakes(); // the superseded socket's `close` lands NOW
      await sleep(250);

      expect(core.state).toBe("connected");
      expect(handshakes()).toBe(before); // no reconnect was scheduled for a connection we replaced
      expect(server.connectionCount).toBe(1);
    });

    it("a frame arriving on a SUPERSEDED connection is not rendered", async () => {
      // routeFrame had no identity guard at all, so a lingering socket's broadcasts entered the
      // transcript on a second, independent event_seq sequence — the double-print half of the
      // same defect the close guard covers.
      server = new MockAppServer({
        suppressFirstResponseFor: ["runtime_start"],
        holdFirstConnectionCloseAfter: "runtime_start",
      });
      url = await server.start();
      const { core, events } = await makeCore({ helloTimeoutMs: 200, maxReconnectAttempts: 0 });
      core.onError(() => {});
      await expect(core.start()).rejects.toThrow(/timed out/);
      await core.start();
      await waitFor(() => core.state === "connected");

      // A HIGH event_seq on purpose. The superseded socket runs its own independent sequence, so
      // a low number would be swallowed by the healthy connection's watermark and the test would
      // pass without exercising anything. A high one both renders AND latches the watermark past
      // every future frame — the double-print and the blackout are the same defect.
      server.sendRawTo(0, {
        type: "stream_delta",
        delta: {
          id: "letta-msg-ghost",
          message_type: "assistant_message",
          content: "from a socket we already replaced",
          run_id: "run-ghost",
          type: "message",
        },
        runtime: RUNTIME,
        event_seq: 5000,
      });
      await sleep(150);

      expect(events.filter((e) => e.messageId === "letta-msg-ghost")).toEqual([]);
      // And the healthy connection is undamaged.
      core.send("still there?");
      await waitFor(() => events.some((e) => e.type === "turn_finished"), 3000);
    });

    it("a REJECTED start() leaves no socket and no reconnect loop behind", async () => {
      // Mutation 7 removes openConnection's cleanup. connect() rejects with the socket still
      // OPEN on the version-refusal and hello-timeout paths, and the close that eventually
      // arrives starts a full reconnect loop for a session the caller has already given up on.
      // The terminal happens to call stop() here; the core must not depend on every consumer
      // remembering to.
      server = new MockAppServer({ suppressFirstResponseFor: ["runtime_start"] });
      url = await server.start();
      const { core } = await makeCore({ helloTimeoutMs: 150, maxReconnectAttempts: 5 });
      core.onError(() => {});

      await expect(core.start()).rejects.toThrow(/timed out/);

      await waitFor(() => server.connectionCount === 0, 2000);
      const handshakes = () => server.received.filter((m) => m.type === "runtime_start").length;
      const settled = handshakes();
      await sleep(300);
      expect(handshakes()).toBe(settled);
      expect(core.state).toBe("disconnected");
    });

    it("a start() whose socket DIES mid-hello does not leave a reconnect loop running", async () => {
      // The other route to the same zombie: the socket closes during connect(), handleClose
      // schedules a reconnect, and only then does connect() reject. start() reports failure while
      // the core quietly keeps dialling.
      server = new MockAppServer({ dropFirstConnectionAfter: "runtime_start" });
      url = await server.start();
      const { core } = await makeCore({ helloTimeoutMs: 2000, maxReconnectAttempts: 5 });
      core.onError(() => {});

      await expect(core.start()).rejects.toThrow();
      const handshakes = () => server.received.filter((m) => m.type === "runtime_start").length;
      const settled = handshakes();
      await sleep(300);

      expect(handshakes()).toBe(settled);
      expect(core.state).toBe("disconnected");
    });

    it("a server that ACCEPTS, answers, and then dies cannot rearm the reconnect budget", async () => {
      // Mutation 13's property, and the one the committed flapping test missed: it suppressed
      // conversation_messages_list, so it bound to fetchSnapshot's rethrow rather than to the
      // budget. Here every RPC succeeds — the connection is textbook healthy and then dies 60ms
      // later. A budget that resets the instant a hello completes is no budget at all: it is
      // exactly the crash-loop shape, and every attached surface hammers the recovering server
      // while showing the user "connected".
      server = new MockAppServer();
      url = await server.start();
      const MAX_ATTEMPTS = 2;
      const { core } = await makeCore({
        reconnectDelayMs: 20,
        maxReconnectAttempts: MAX_ATTEMPTS,
        connectionStabilityMs: 500,
      });
      core.onError(() => {});
      await core.start();

      const killer = setInterval(() => server.dropAllConnections(), 60);
      await sleep(1200);
      clearInterval(killer);

      const handshakes = server.received.filter((m) => m.type === "runtime_start").length;
      expect(handshakes).toBeLessThanOrEqual(MAX_ATTEMPTS + 1);
      expect(core.state).not.toBe("connected");
    });

    it("a connection that PROVES itself does restore the budget", async () => {
      // The other side of the same property: a real recovery must not be punished for an earlier
      // outage, or a long-lived client eventually exhausts its budget on unrelated blips.
      server = new MockAppServer();
      url = await server.start();
      const { core } = await makeCore({
        reconnectDelayMs: 20,
        maxReconnectAttempts: 2,
        connectionStabilityMs: 60,
      });
      core.onError(() => {});
      await core.start();

      for (let i = 0; i < 4; i += 1) {
        server.dropAllConnections();
        await waitFor(() => core.state === "connected", 3000);
        await sleep(120); // longer than the stability window: this connection proved itself
      }
      expect(core.state).toBe("connected");
    });

    it("a server that shuts down POLITELY is recovered from like one that vanishes", async () => {
      // A close handshake and a TCP reset are different events on the wire, and the double could
      // only produce the reset — so the whole recovery path had been exercised against one of the
      // two shapes a real shutdown takes. `letta server` stopping cleanly is the commoner one.
      server = new MockAppServer();
      url = await server.start();
      const { core, events } = await makeCore();
      await core.start();

      server.closeAllConnections();
      await waitFor(() => core.state !== "connected", 3000);
      await waitFor(() => core.state === "connected", 5000);

      const before = events.length;
      core.send("after a polite goodbye");
      await waitFor(
        () => events.length > before && events.some((e) => e.type === "turn_finished"),
        3000,
      );
    });

    it("a session stopped and started again renders the new session's stream", async () => {
      // `event_seq` is PER-CONNECTION and restarts at 1. The watermark was reset only in
      // reconnect(), so a second start() kept the first session's high-water mark and dropped
      // every frame of the new one: connected, accepting input, rendering nothing, reporting
      // nothing. A total blackout, and silent.
      server = new MockAppServer();
      url = await server.start();
      const { core, events } = await makeCore();
      await core.start();
      core.send("first session");
      await waitFor(() => events.some((e) => e.type === "turn_finished"));

      core.stop();
      await waitFor(() => server.connectionCount === 0, 3000);

      await core.start();
      core.send("second session");
      await waitFor(() => events.filter((e) => e.type === "turn_finished").length >= 2, 3000);
    });
  });

  // ── listener isolation ───────────────────────────────────────────────────

  describe("a throwing consumer is a consumer problem, never a connection problem", () => {
    // Mutation 3 reverts six of the seven fan-out sites to bare loops and the suite stays green,
    // because only ONE channel was covered. Every one of these runs synchronously inside the
    // socket's message handler, so a throw becomes an uncaughtException and Node exits — and the
    // terminal's listeners all end in process.stdout.write, so `letta-continuity | head -40`
    // killed the client on EPIPE rather than degrading.

    it("onRender survives a throwing listener", async () => {
      server = new MockAppServer();
      url = await server.start();
      const { core } = await makeCore();
      const survived: RenderEvent[] = [];
      core.onRender(() => {
        throw new Error("EPIPE from the render sink");
      });
      core.onRender((e) => survived.push(e));
      await core.start();
      core.send("hello");
      await waitFor(() => survived.some((e) => e.type === "turn_finished"), 3000);
      expect(core.state).toBe("connected");
    });

    it("onConnectionState survives a throwing listener", async () => {
      server = new MockAppServer();
      url = await server.start();
      const { core } = await makeCore();
      const survived: string[] = [];
      core.onConnectionState(() => {
        throw new Error("EPIPE from the status sink");
      });
      core.onConnectionState((s) => survived.push(s));
      await core.start();
      await waitFor(() => survived.includes("connected"), 3000);
    });

    it("onError survives a throwing listener", async () => {
      server = new MockAppServer();
      url = await server.start();
      const { core } = await makeCore();
      const survived: string[] = [];
      core.onError(() => {
        throw new Error("EPIPE from the error sink");
      });
      core.onError((e) => survived.push(e.message));
      await core.start();
      // A frame that fails validation is the ordinary way an error reaches consumers.
      server.sendRaw({ type: "turn_finished", turn_id: "t", runtime: RUNTIME, event_seq: 1 });
      await waitFor(() => survived.length > 0, 3000);
      expect(core.state).toBe("connected");
    });

    it("onApproval survives a throwing listener", async () => {
      server = new MockAppServer({ approvalMode: true });
      url = await server.start();
      const { core } = await makeCore();
      const survived: string[] = [];
      core.onApproval(() => {
        throw new Error("EPIPE from the approval sink");
      });
      core.onApproval((e) => survived.push(e.requestId));
      await core.start();
      core.send("do a risky thing");
      await waitFor(() => survived.length > 0, 3000);
      expect(core.state).toBe("connected");
    });

    it("onFatal survives a throwing listener", async () => {
      server = new MockAppServer();
      url = await server.start();
      const { core } = await makeCore({ reconnectDelayMs: 10, maxReconnectAttempts: 1 });
      const survived: string[] = [];
      core.onError(() => {});
      core.onFatal(() => {
        throw new Error("EPIPE from the fatal sink");
      });
      core.onFatal((e) => survived.push(e.reason));
      await core.start();
      await server.stop();
      await waitFor(() => survived.includes("reconnect-exhausted"), 5000);
    });
  });

  // ── one core, several origins ────────────────────────────────────────────

  describe("one core, several origins (the M1 Unit 6 shape)", () => {
    it("a TOOL-USING reply is routed back to the origin that submitted it", async () => {
      // The reply to a multi-step turn does not arrive on the run our send started — that run is
      // suspended by the tool call and never closed. It arrives on a NEW run, which no claim can
      // bind. Origin threading that stops at the first run therefore hands a bridge nothing to
      // route by for exactly the replies that matter most.
      server = new MockAppServer({ toolUse: true });
      url = await server.start();
      const { core, events } = await makeCore();
      await core.start();

      const routed: Array<{ text: string; origin: string | undefined }> = [];
      core.onRender((e) => {
        if (e.type === "delta" && e.text) {
          routed.push({ text: e.text, origin: core.runOrigin(e.runId) });
        }
      });

      core.send("use a tool for tab A", { origin: "tab-A" });
      await waitFor(() => events.some((e) => e.type === "turn_finished"), 5000);

      const answer = routed.filter((r) => r.text !== "");
      expect(answer.length).toBeGreaterThan(0);
      // EVERY chunk of the reply, not just the first, and none of them unattributed.
      expect(new Set(answer.map((r) => r.origin))).toEqual(new Set(["tab-A"]));
    });

    it("TWO origins each get their own TOOL-USING reply, on runs no claim of theirs could bind", async () => {
      // Metric 5, and the shape M1 Unit 6 is: one core, N browsers, replies that arrive on
      // continuation runs. Getting this wrong does not merely lose a label — it hands one
      // consumer another consumer's answer.
      server = new MockAppServer({ toolUse: true });
      url = await server.start();
      const { core, events } = await makeCore();
      await core.start();

      const routed: Array<{ text: string; origin: string | undefined }> = [];
      core.onRender((e) => {
        if (e.type === "delta" && e.text)
          routed.push({ text: e.text, origin: core.runOrigin(e.runId) });
      });

      core.send("tab A asks for a tool", { origin: "tab-A" });
      core.send("tab B asks for a tool", { origin: "tab-B" });
      await waitFor(() => events.filter((e) => e.type === "turn_finished").length >= 2, 8000);

      const origins = routed.filter((r) => r.text !== "").map((r) => r.origin);
      expect(origins.length).toBeGreaterThanOrEqual(2);
      // Both are represented, and nothing arrived unattributed or under the wrong tab.
      expect(new Set(origins)).toEqual(new Set(["tab-A", "tab-B"]));
      // Submission order: the server serializes, so tab-A's reply precedes tab-B's.
      expect(origins[0]).toBe("tab-A");
      expect(origins.at(-1)).toBe("tab-B");
    }, 20_000);

    it("two origins on one core each get their own reply, in submission order", async () => {
      server = new MockAppServer();
      url = await server.start();
      const { core, events } = await makeCore();
      await core.start();

      const originsAtStart: Array<string | undefined> = [];
      core.onRender((e) => {
        if (e.type === "turn_start" && e.runId) originsAtStart.push(core.runOrigin(e.runId));
      });

      core.send("from tab A", { origin: "tab-A" });
      core.send("from tab B", { origin: "tab-B" });
      await waitFor(() => events.filter((e) => e.type === "turn_finished").length >= 2, 5000);

      expect(originsAtStart).toEqual(["tab-A", "tab-B"]);
    });

    it("the WIRE ids name the origin, so attribution survives without the in-memory map", async () => {
      // Mutation 10 reverts send() to the single construction-time nonce. Ids stay distinct
      // either way — the counter sees to that — so "they differ" was never the property. What the
      // per-origin nonce buys is that a captured frame is self-describing: a bridge restarted
      // mid-turn, or an operator reading a packet capture, can still say which consumer a queued
      // message belongs to.
      server = new MockAppServer({ autoTurnOnInput: false });
      url = await server.start();
      const { core } = await makeCore();
      await core.start();

      const handle = core.send("from tab A", { origin: "tab-A" });
      await waitFor(() => server.received.some((m) => m.type === "input"));
      const sent = server.received.find((m) => m.type === "input") as {
        request_id: string;
        payload: { client_message_id: string };
      };

      expect(sent.request_id).toContain("tab-A");
      expect(sent.payload.client_message_id).toContain("tab-A");
      expect(handle.requestId).toBe(sent.request_id);
      expect(handle.clientMessageId).toBe(sent.payload.client_message_id);
    });
  });

  // ── failures name what failed ────────────────────────────────────────────

  describe("failures carry enough to act on", () => {
    it("a REJECTED input names the send and the origin that made it", async () => {
      // A bridge fanning out to N consumers has to fail the one that asked. Telling all of them,
      // or none, are both wrong — and neither the message text nor the reason code identifies a
      // submitter, so there was nothing to route the failure by.
      server = new MockAppServer({ rejectInputWith: "runtime is no longer active" });
      url = await server.start();
      const { core } = await makeCore();
      const fatals: Array<{ requestId?: string; origin?: string; reason: string }> = [];
      core.onError(() => {});
      core.onFatal((e) =>
        fatals.push({ requestId: e.requestId, origin: e.origin, reason: e.reason }),
      );
      await core.start();

      const handle = core.send("this will be refused", { origin: "tab-A" });
      await waitFor(() => fatals.length > 0, 3000);

      expect(fatals[0]?.reason).toBe("input-rejected");
      expect(fatals[0]?.requestId).toBe(handle.requestId);
      expect(fatals[0]?.origin).toBe("tab-A");
    });

    it("a conversation_create with no usable id fails loudly, not with an unopenable pointer", async () => {
      // Unit 8's seed step writes this id into the pointer every surface then attaches to. A cast
      // let `undefined` through, so the failure would have surfaced as "no such conversation" on
      // every client, one step removed from the thing that actually broke.
      server = new MockAppServer({ suppressResponsesFor: ["conversation_create"] });
      url = await server.start();
      const { core } = await makeCore({ rpcTimeoutMs: 5000 });
      await core.start();

      const pending = core.conversationCreate("seed");
      await waitFor(() => server.received.some((m) => m.type === "conversation_create"));
      const rid = server.received.filter((m) => m.type === "conversation_create").at(-1)
        ?.request_id as string;
      server.sendRaw({
        type: "conversation_create_response",
        request_id: rid,
        success: true,
        // The field renamed, exactly as a server-side change would leave it.
        thread: { id: "local-conv-new-1" },
      });

      await expect(pending).rejects.toThrow(/no usable .conversation\.id./);
    });

    it("a conversation_list entry with no id is dropped with a warning, not printed as undefined", async () => {
      server = new MockAppServer({
        conversations: [
          { id: "c-1", agent_id: AGENT, archived: false, updated_at: "y" },
          { thread_id: "c-2", agent_id: AGENT },
        ],
      });
      url = await server.start();
      const { core, warnings } = await makeCore();
      await core.start();

      const list = await core.conversationList();
      expect(list.map((c) => c.id)).toEqual(["c-1"]);
      expect(warnings.some((w) => /no string `id`/.test(w))).toBe(true);
    });
  });

  // ── stream integrity ─────────────────────────────────────────────────────

  it("an unknown frame type with a poisoned event_seq cannot latch the watermark", async () => {
    // validateInboundFrame rejects an out-of-range event_seq on every frame type it KNOWS, but
    // unknown types pass through for forward compatibility and still carry an event_seq into the
    // assembler. One such frame with MAX_SAFE_INTEGER silences the client permanently: connected,
    // accepting input, rendering nothing, reporting nothing, with no reset short of a reconnect.
    server = new MockAppServer();
    url = await server.start();
    const { core, events } = await makeCore();
    await core.start();

    server.sendRaw({
      type: "update_something_we_have_never_heard_of",
      runtime: RUNTIME,
      event_seq: Number.MAX_SAFE_INTEGER,
    });
    await sleep(80);

    core.send("still there?");
    await waitFor(() => events.some((e) => e.type === "turn_finished"), 3000);
  });
});
