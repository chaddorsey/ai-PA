/**
 * Contract test — the server-upgrade gate.
 *
 * Round-trips a canonical fixture of EVERY frame the client uses through parse + validate +
 * the extractors, then proves that a DRIFTED frame (renamed/removed field) fails LOUDLY.
 * If a `letta` binary bump renames a field, updating the fixtures here is the deliberate,
 * reviewed step that unblocks the upgrade — silent mis-parse is impossible.
 *
 * The fixtures are the empirically-captured 0.30.19 shapes (Unit 4 live captures).
 */

import { describe, expect, it } from "vitest";
import {
  CONTROL_DELTA_TYPES,
  DeltaMessageTypes,
  Inbound,
  LoopStatuses,
  Outbound,
  ProtocolError,
  RpcResponseFor,
  type ServerFrame,
  StopReasons,
  VALIDATED_SERVER_VERSIONS,
  __resetRequestCounter,
  assertServerIdentity,
  buildApprovalDeny,
  buildConversationCreate,
  buildConversationList,
  buildConversationMessagesList,
  buildInput,
  buildRuntimeStart,
  controlRequestToolName,
  deltaMessageId,
  deltaMessageType,
  deltaText,
  frameEventSeq,
  isControlRequest,
  isLoopStatus,
  isQueue,
  isStreamDelta,
  isSubagentState,
  isTurnFinished,
  newClientNonce,
  nextRequestId,
  parseFrame,
  queueDepth,
  queueRemovals,
  subagentCount,
  validateInboundFrame,
} from "../src/protocol.js";

const RT = { agent_id: "agent-local-abc", conversation_id: "local-conv-xyz" };
const meta = { runtime: RT, emitted_at: "2026-08-13T00:00:00.000Z", idempotency_key: "k:1:u" };

const FIXTURES = {
  runtime_start_response: {
    type: "runtime_start_response",
    request_id: "rt-1",
    success: true,
    runtime: RT,
    agent: { id: RT.agent_id, name: "mock" },
    conversation: RT.conversation_id,
    created: { agent: false, conversation: false },
  },
  stream_delta: {
    type: "stream_delta",
    delta: {
      id: "letta-msg-14519",
      date: "2026-08-13T00:00:00.000Z",
      agent_id: RT.agent_id,
      conversation_id: RT.conversation_id,
      message_type: "assistant_message",
      otid: "otid-1",
      content: "OK",
      run_id: "local-run-125",
      seq_id: 1,
      type: "message",
    },
    ...meta,
    event_seq: 11,
  },
  stream_delta_reasoning: {
    type: "stream_delta",
    delta: {
      id: "letta-msg-14519",
      agent_id: RT.agent_id,
      conversation_id: RT.conversation_id,
      message_type: "reasoning_message",
      reasoning: "The",
      run_id: "local-run-125",
      seq_id: 1,
      type: "message",
    },
    ...meta,
    event_seq: 12,
  },
  turn_finished: {
    type: "turn_finished",
    turn_id: "batch-direct-1",
    stop_reason: "end_turn",
    run_id: "local-run-125",
    ...meta,
    event_seq: 35,
  },
  update_loop_status: {
    type: "update_loop_status",
    loop_status: { status: "WAITING_ON_INPUT", active_run_ids: [], executing_tool_call_ids: [] },
    ...meta,
    event_seq: 2,
  },
  // POPULATED on purpose. The previous fixture had empty arrays, so QueueItem and QueueRemoval —
  // the shapes run attribution keys on — were never round-tripped at all.
  update_queue: {
    type: "update_queue",
    queue: [
      {
        id: "q-1",
        client_message_id: "cm-abc123-4",
        kind: "message",
        source: "user",
        content: "queued text",
        enqueued_at: "2026-08-13T00:00:00.000Z",
      },
    ],
    removed: [{ client_message_id: "cm-abc123-4", disposition: "dequeued" }],
    ...meta,
    event_seq: 3,
  },
  input_accepted_started: {
    type: "input_accepted",
    request_id: "input-abc123-3",
    runtime: RT,
    accepted: true,
    disposition: "started",
  },
  input_accepted_queued: {
    type: "input_accepted",
    request_id: "input-abc123-9",
    runtime: RT,
    accepted: true,
    disposition: "queued",
  },
  // An approval_response ack. `disposition` is a message-QUEUE concept, so it is absent here:
  // the server's own typedef declares it optional and `acknowledgeInput(handled, ...)` on the
  // approval path passes no third argument. Captured from the 0.30.20 bundle.
  input_accepted_approval_ack: {
    type: "input_accepted",
    request_id: "appr-abc123-7",
    runtime: RT,
    accepted: true,
  },
  input_rejected: {
    type: "input_accepted",
    request_id: "input-abc123-11",
    runtime: RT,
    accepted: false,
    error: "Runtime is no longer active",
  },
  update_subagent_state: { type: "update_subagent_state", subagents: [], ...meta, event_seq: 4 },
  update_device_status: {
    type: "update_device_status",
    device_status: { is_online: true, is_processing: false },
    ...meta,
    event_seq: 1,
  },
  stream_delta_stop_reason: {
    type: "stream_delta",
    delta: {
      message_type: "stop_reason",
      stop_reason: "end_turn",
      run_id: "local-run-125",
      seq_id: 21,
      type: "message",
    },
    ...meta,
    event_seq: 31,
  },
  stream_delta_usage: {
    type: "stream_delta",
    delta: {
      id: "letta-msg-14520",
      message_type: "usage_statistics",
      run_id: "local-run-125",
      seq_id: 20,
      type: "message",
    },
    ...meta,
    event_seq: 30,
  },
  // Captured from the 0.30.20 bundle (requestApprovalOverWS / the can_use_tool control request).
  // This is the ACTIONABLE approval request — broadcast to every subscriber.
  control_request: {
    type: "control_request",
    request_id: "perm-toolu_01ABC",
    request: {
      subtype: "can_use_tool",
      tool_name: "Bash",
      input: { command: "echo hi" },
      tool_call_id: "toolu_01ABC",
      permission_suggestions: [],
      blocked_path: null,
    },
    agent_id: RT.agent_id,
    conversation_id: RT.conversation_id,
  },
  conversation_list_response: {
    type: "conversation_list_response",
    request_id: "cl-1",
    success: true,
    conversations: [
      {
        id: "local-conv-1954",
        agent_id: RT.agent_id,
        archived: false,
        archived_at: null,
        created_at: "2026-08-12T23:07:13.003Z",
        updated_at: "2026-08-12T23:07:13.003Z",
      },
    ],
  },
  conversation_create_response: {
    type: "conversation_create_response",
    request_id: "cc-1",
    success: true,
    conversation: { id: "local-conv-new-1", agent_id: RT.agent_id },
  },
  conversation_messages_list_response: {
    type: "conversation_messages_list_response",
    request_id: "cml-1",
    success: true,
    messages: [{ id: "letta-msg-1" }, { id: "letta-msg-2" }],
    next_before: null,
    has_more: false,
    error: null,
  },
} satisfies Record<string, ServerFrame>;

describe("contract: inbound frames round-trip through parse + validate", () => {
  for (const [name, fixture] of Object.entries(FIXTURES)) {
    it(`${name} parses and validates`, () => {
      const parsed = parseFrame(JSON.stringify(fixture));
      expect(parsed.type).toBe(fixture.type);
      expect(() => validateInboundFrame(parsed)).not.toThrow();
    });
  }

  it("stream_delta extractors read the pinned fields", () => {
    const f = parseFrame(JSON.stringify(FIXTURES.stream_delta));
    expect(isStreamDelta(f)).toBe(true);
    if (!isStreamDelta(f)) throw new Error("guard");
    expect(deltaMessageId(f)).toBe("letta-msg-14519");
    expect(deltaMessageType(f)).toBe("assistant_message");
    expect(deltaText(f)).toBe("OK");
    expect(frameEventSeq(f)).toBe(11);
  });

  it("reasoning delta text comes from `reasoning`", () => {
    const f = parseFrame(JSON.stringify(FIXTURES.stream_delta_reasoning));
    if (!isStreamDelta(f)) throw new Error("guard");
    expect(deltaText(f)).toBe("The");
  });

  it("assistant content can be a block array", () => {
    const f = parseFrame(
      JSON.stringify({
        ...FIXTURES.stream_delta,
        delta: {
          ...(FIXTURES.stream_delta.delta as object),
          content: [{ text: "he" }, { text: "llo" }],
        },
      }),
    );
    if (!isStreamDelta(f)) throw new Error("guard");
    expect(deltaText(f)).toBe("hello");
  });

  it("turn_finished / loop_status / queue / subagent / approval guards + seq", () => {
    const tf = parseFrame(JSON.stringify(FIXTURES.turn_finished));
    expect(isTurnFinished(tf)).toBe(true);
    expect(frameEventSeq(tf)).toBe(35);
    expect(isLoopStatus(parseFrame(JSON.stringify(FIXTURES.update_loop_status)))).toBe(true);
    expect(isQueue(parseFrame(JSON.stringify(FIXTURES.update_queue)))).toBe(true);
    expect(isSubagentState(parseFrame(JSON.stringify(FIXTURES.update_subagent_state)))).toBe(true);
  });
});

describe("contract: frameEventSeq gates what may latch the ordering watermark", () => {
  // Both conditions in `frameEventSeq` were flagged as equivalent mutants — on the PRODUCTION
  // path they are, because `validateInboundFrame` has already applied the same range check to
  // exactly the six ordered types before any frame reaches the stream layer. That makes the
  // guard unreachable *through the pipeline*, and the round-4 review was right that no
  // pipeline-level test could ever fail on reverting it.
  //
  // It is bound HERE instead of retired, because unlike the reverts that were retired (ids 6, 21)
  // this one is an EXPORTED function: its contract belongs to every caller, not just to the one
  // call site in stream.ts. The coupling that makes it redundant today is also invisible — add a
  // type to ORDERED_BROADCAST_TYPES that the validator does not range-check, and the guard is
  // load-bearing again with nothing to say so. The watermark is a one-way latch, so the cost of
  // being wrong is a client that is connected, accepting input, and permanently silent.

  it("refuses a counter that is not a counter, even on an ordered type", () => {
    for (const notACounter of [
      Number.NaN,
      Number.POSITIVE_INFINITY,
      -1,
      1.5,
      Number.MAX_SAFE_INTEGER + 1,
      "3",
      null,
      undefined,
      {},
    ]) {
      const frame = { type: Inbound.streamDelta, event_seq: notACounter } as unknown as ServerFrame;
      expect(frameEventSeq(frame)).toBeUndefined();
    }
    // …and a real one still passes through, or the guard would be a blanket refusal.
    expect(frameEventSeq({ type: Inbound.streamDelta, event_seq: 0 } as ServerFrame)).toBe(0);
    expect(frameEventSeq({ type: Inbound.streamDelta, event_seq: 12 } as ServerFrame)).toBe(12);
  });

  it("excludes frames that take no part in the ordered stream", () => {
    // An RPC response carrying an event_seq must not raise the watermark…
    expect(
      frameEventSeq({
        type: Inbound.conversationListResponse,
        event_seq: 99,
      } as unknown as ServerFrame),
    ).toBeUndefined();
    // …and neither may a forward-compatible type this client does not even render. This is the
    // case the allowlist exists for: one unknown frame carrying MAX_SAFE_INTEGER would otherwise
    // silence the connection for good.
    expect(
      frameEventSeq({
        type: "some_future_broadcast",
        event_seq: Number.MAX_SAFE_INTEGER,
      } as unknown as ServerFrame),
    ).toBeUndefined();
  });
});

describe("contract: the approval control request", () => {
  const CR = FIXTURES.control_request;

  it("is recognised, and exposes the tool call the user needs to see", () => {
    const f = parseFrame(JSON.stringify(CR));
    expect(isControlRequest(f)).toBe(true);
    if (!isControlRequest(f)) throw new Error("guard");
    expect(controlRequestToolName(f)).toBe("Bash");
    expect(f.request_id).toBe("perm-toolu_01ABC");
  });

  it("the deny response carries the request_id and a deny decision with a message", () => {
    const f = buildApprovalDeny("appr-1", RT, "perm-toolu_01ABC", "denied by policy") as Record<
      string,
      unknown
    >;
    expect(f.type).toBe("input");
    const payload = f.payload as Record<string, unknown>;
    expect(payload.kind).toBe("approval_response");
    expect(payload.request_id).toBe("perm-toolu_01ABC");
    // Server validator: deny REQUIRES a string message.
    expect(payload.decision).toEqual({ behavior: "deny", message: "denied by policy" });
  });

  it("M1 is deny-only: no builder can construct an allow decision", () => {
    // Enforced by type — buildApprovalDeny takes no decision parameter, so reintroducing allow
    // at the rail milestone requires a visible signature change rather than a one-word edit.
    const f = buildApprovalDeny("a", RT, "perm-x", "m") as Record<string, unknown>;
    const json = JSON.stringify(f);
    expect(json).not.toContain("allow");
  });

  it("a control_request missing its request_id or tool_call_id fails loudly", () => {
    const noReq = { ...CR } as Record<string, unknown>;
    noReq.request_id = undefined;
    expect(() => validateInboundFrame(parseFrame(JSON.stringify(noReq)))).toThrow(ProtocolError);

    const noTool = { ...CR, request: { ...CR.request, tool_call_id: undefined } };
    expect(() => validateInboundFrame(parseFrame(JSON.stringify(noTool)))).toThrow(/tool_call_id/);
  });
});

describe("contract: the wire vocabulary lives here, so a rename fails the gate", () => {
  // These strings used to be re-declared in the terminal's renderer, outside the reach of both
  // validateInboundFrame and this test. A server-side rename would have passed every check and
  // the terminal would simply have rendered nothing: connected, accepting input, no output, no
  // error. Pinning them here is what converts that into a failing test.
  it("delta message types match the shapes the fixtures carry", () => {
    expect(DeltaMessageTypes.assistant).toBe(FIXTURES.stream_delta.delta.message_type);
    expect(DeltaMessageTypes.reasoning).toBe(FIXTURES.stream_delta_reasoning.delta.message_type);
    expect(DeltaMessageTypes.usage).toBe(FIXTURES.stream_delta_usage.delta.message_type);
    expect(DeltaMessageTypes.stopReason).toBe(FIXTURES.stream_delta_stop_reason.delta.message_type);
  });

  it("stop reasons and loop statuses match the fixtures", () => {
    expect(StopReasons.endTurn).toBe(FIXTURES.turn_finished.stop_reason);
    expect(LoopStatuses.waitingOnInput).toBe(FIXTURES.update_loop_status.loop_status.status);
  });

  it("the control-delta allowlist is expressed in the same vocabulary", () => {
    expect(CONTROL_DELTA_TYPES.has(DeltaMessageTypes.stopReason)).toBe(true);
    expect(CONTROL_DELTA_TYPES.has(DeltaMessageTypes.assistant)).toBe(false);
  });

  it("typed accessors read the queue and subagent payloads", () => {
    const q = parseFrame(JSON.stringify(FIXTURES.update_queue));
    if (!isQueue(q)) throw new Error("guard");
    expect(queueDepth(q)).toBe(1);

    const sub = parseFrame(JSON.stringify(FIXTURES.update_subagent_state));
    if (!isSubagentState(sub)) throw new Error("guard");
    expect(subagentCount(sub)).toBe(0);
  });
});

describe("contract: DRIFT fails loudly (the upgrade gate)", () => {
  it("renamed event_seq → stream_delta rejected", () => {
    const drifted = { ...FIXTURES.stream_delta } as Record<string, unknown>;
    drifted.eventSeq = drifted.event_seq;
    drifted.event_seq = undefined;
    expect(() => validateInboundFrame(parseFrame(JSON.stringify(drifted)))).toThrow(ProtocolError);
  });

  it("removed delta.id → stream_delta rejected (loses the catch-up watermark)", () => {
    const delta = { ...(FIXTURES.stream_delta.delta as Record<string, unknown>) };
    delta.id = undefined;
    expect(() =>
      validateInboundFrame(parseFrame(JSON.stringify({ ...FIXTURES.stream_delta, delta }))),
    ).toThrow(/delta\.id/);
  });

  it("the CONTROL allowlist is a narrow exemption, not a hole in the watermark guard", () => {
    // This slot previously held a byte-identical copy of the test above. What it should assert is
    // the OTHER side of the allowlist: a control delta without an id is accepted, while the
    // allowlist stays narrow enough that content types can never slip into it.
    expect(() =>
      validateInboundFrame(parseFrame(JSON.stringify(FIXTURES.stream_delta_stop_reason))),
    ).not.toThrow();
    expect(CONTROL_DELTA_TYPES.has("assistant_message")).toBe(false);
    expect(CONTROL_DELTA_TYPES.has("reasoning_message")).toBe(false);
    expect(CONTROL_DELTA_TYPES.has("usage_statistics")).toBe(false);
  });

  it("update_queue drift: a renamed client_message_id or disposition fails loudly", () => {
    // These two fields decide whether a claim arms or is dropped, so a rename silently re-routes
    // attribution — the failure mode with no visible symptom.
    const noId = {
      ...FIXTURES.update_queue,
      removed: [{ otid: "cm-abc123-4", disposition: "dequeued" }],
    };
    expect(() => validateInboundFrame(parseFrame(JSON.stringify(noId)))).toThrow(
      /client_message_id/,
    );

    const noDisp = {
      ...FIXTURES.update_queue,
      removed: [{ client_message_id: "cm-abc123-4", outcome: "dequeued" }],
    };
    expect(() => validateInboundFrame(parseFrame(JSON.stringify(noDisp)))).toThrow(/disposition/);
  });

  it("an accepted ack with NO disposition validates — the approval-response shape", () => {
    // This assertion is inverted from what it was. The old rule ("an accepted ack MUST carry a
    // disposition") pinned the client's misreading as the contract: the server's typedef declares
    // `disposition?: "started" | "queued"` and both the approval path and the teleport path ack
    // without one. Requiring it meant every approval this client answered raised a false
    // ProtocolError AND had its ack dropped — poisoning the very drift signal this file exists to
    // provide, on the one path with no live capture to check against.
    expect(() =>
      validateInboundFrame(parseFrame(JSON.stringify(FIXTURES.input_accepted_approval_ack))),
    ).not.toThrow();

    const noAccepted = { ...FIXTURES.input_accepted_started } as Record<string, unknown>;
    noAccepted.accepted = undefined;
    expect(() => validateInboundFrame(parseFrame(JSON.stringify(noAccepted)))).toThrow(/accepted/);
  });

  it("an out-of-range event_seq fails loudly instead of poisoning the stream", () => {
    // StreamAssembler latches its watermark to whatever arrives and drops everything at or below
    // it, so ONE absurd counter silently wedges the connection for its whole life: connected,
    // accepting input, rendering nothing, reporting nothing. `typeof === "number"` let all of
    // these through.
    for (const bad of [
      Number.MAX_SAFE_INTEGER + 1,
      Number.POSITIVE_INFINITY,
      Number.NaN,
      -1,
      1.5,
    ]) {
      const frame = { ...FIXTURES.stream_delta, event_seq: bad };
      expect(() => validateInboundFrame(parseFrame(JSON.stringify(frame)))).toThrow(/event_seq/);
    }
    // MAX_SAFE_INTEGER itself is in range and must still pass — the bound is on plausibility,
    // not on being small.
    const ok = { ...FIXTURES.stream_delta, event_seq: Number.MAX_SAFE_INTEGER };
    expect(() => validateInboundFrame(parseFrame(JSON.stringify(ok)))).not.toThrow();
  });

  it("a queue removal with no disposition is not narrowed as if it had one", () => {
    // queueRemovals() asserted `r is QueueRemoval` — which declares a required disposition —
    // while only checking client_message_id. The consumer then read the absent field and its
    // `dequeued ? arm : drop` branch destroyed the claim as though the server had cancelled it.
    const frame = {
      ...FIXTURES.update_queue,
      removed: [{ client_message_id: "cm-abc123-4" }],
    };
    expect(queueRemovals(parseFrame(JSON.stringify(frame)) as never)).toEqual([]);
  });

  it("an UNKNOWN delta type with no id fails loudly (not silently allowed)", () => {
    const frame = {
      ...FIXTURES.stream_delta,
      delta: { message_type: "some_future_control_type", type: "message" },
    };
    expect(() => validateInboundFrame(parseFrame(JSON.stringify(frame)))).toThrow(/delta\.id/);
  });

  it("renamed conversations → conversation_list_response rejected", () => {
    const drifted = { ...FIXTURES.conversation_list_response } as Record<string, unknown>;
    drifted.threads = drifted.conversations;
    drifted.conversations = undefined;
    expect(() => validateInboundFrame(parseFrame(JSON.stringify(drifted)))).toThrow(ProtocolError);
  });

  it("turn_finished missing stop_reason rejected", () => {
    const drifted = { ...FIXTURES.turn_finished } as Record<string, unknown>;
    drifted.stop_reason = undefined;
    expect(() => validateInboundFrame(parseFrame(JSON.stringify(drifted)))).toThrow(/stop_reason/);
  });

  it("non-JSON and typeless frames throw at parse", () => {
    expect(() => parseFrame("not json")).toThrow(ProtocolError);
    expect(() => parseFrame(JSON.stringify({ no: "type" }))).toThrow(ProtocolError);
  });
});

describe("contract: outbound builders shape the pinned frames", () => {
  it("runtime_start / input", () => {
    expect(buildRuntimeStart("r1", RT)).toEqual({
      type: "runtime_start",
      request_id: "r1",
      agent_id: RT.agent_id,
      conversation_id: RT.conversation_id,
    });
    const input = buildInput(RT, "hi", {
      requestId: "in-1",
      clientMessageId: "cm-1",
    }) as Record<string, unknown>;
    expect(input.type).toBe("input");
    // request_id is REQUIRED for correlation: without it the server sends no input_accepted
    // ack at all, and run ownership (ownership.ts) has nothing to bind a claim to.
    expect(input.request_id).toBe("in-1");
    expect(input.payload).toEqual({
      kind: "create_message",
      client_message_id: "cm-1",
      // Leg 1 of the approval policy: the server excludes AskUserQuestion-class tools from the
      // turn, so the inherently-blocking tool class cannot be selected on a shared conversation.
      exclude_interactive_tools: true,
      messages: [{ role: "user", content: "hi", client_message_id: "cm-1" }],
    });
  });

  it("conversation RPC builders + response map", () => {
    expect((buildConversationList("c1", "a") as Record<string, unknown>).type).toBe(
      "conversation_list",
    );
    expect(
      (buildConversationMessagesList("c3", RT) as Record<string, unknown>).conversation_id,
    ).toBe(RT.conversation_id);
    expect(RpcResponseFor[Outbound.conversationList]).toBe(Inbound.conversationListResponse);
    expect(RpcResponseFor[Outbound.conversationCreate]).toBe(Inbound.conversationCreateResponse);
  });

  /**
   * OUTBOUND envelope gate. These predicates are transcribed from the server's own command
   * guards in letta.js (isConversationListCommand / isConversationCreateCommand /
   * isConversationMessagesListCommand) and verified live on 0.30.19 + 0.30.20.
   *
   * They matter because the server drops a guard-failing frame SILENTLY — no error, no
   * response, just an RPC timeout. Asserting only "the builder set some field" (as the
   * original test did) let `conversation_create` ship with the wrong envelope entirely.
   */
  describe("outbound envelopes satisfy the server's command guards", () => {
    const isRecord = (v: unknown): v is Record<string, unknown> =>
      typeof v === "object" && v !== null && !Array.isArray(v);

    it("conversation_list: request_id + optional `query` OBJECT (agent filter lives in query)", () => {
      const f = buildConversationList("c1", "agent-x") as Record<string, unknown>;
      expect(f.type).toBe("conversation_list");
      expect(typeof f.request_id).toBe("string");
      expect(f.query === undefined || isRecord(f.query)).toBe(true);
      // A top-level agent_id is IGNORED by the server → the filter must be inside query.
      expect(isRecord(f.query) && f.query.agent_id).toBe("agent-x");
      expect(f.agent_id).toBeUndefined();
    });

    it("conversation_create: request_id + a `body` OBJECT carrying agent_id", () => {
      const f = buildConversationCreate("c2", "agent-x", "T") as Record<string, unknown>;
      expect(f.type).toBe("conversation_create");
      expect(typeof f.request_id).toBe("string");
      // The guard REQUIRES body to be an object; without it the RPC is silently dropped.
      expect(isRecord(f.body)).toBe(true);
      expect(isRecord(f.body) && f.body.agent_id).toBe("agent-x");
      expect(isRecord(f.body) && f.body.title).toBe("T");
      expect(f.agent_id).toBeUndefined();
    });

    it("conversation_create: title is optional and omitted cleanly", () => {
      const f = buildConversationCreate("c2", "agent-x") as Record<string, unknown>;
      expect(isRecord(f.body) && "title" in f.body).toBe(false);
      expect(isRecord(f.body) && f.body.agent_id).toBe("agent-x");
    });

    it("conversation_messages_list: top-level conversation_id + optional `query` OBJECT", () => {
      const f = buildConversationMessagesList("c3", RT) as Record<string, unknown>;
      expect(f.type).toBe("conversation_messages_list");
      expect(typeof f.request_id).toBe("string");
      expect(typeof f.conversation_id).toBe("string");
      expect(f.query === undefined || isRecord(f.query)).toBe(true);
    });
  });
});

describe("contract: correlation ids are unique across client PROCESSES", () => {
  it("the same counter position yields different ids under different nonces", () => {
    // The shipped generator was a module-global counter, so every process emitted the identical
    // sequence rpc-1, rt-2, input-3, cm-4. Two surfaces on one conversation therefore minted the
    // same client_message_id — observed in the server's persisted state, where otid "cm-4"
    // appears twice from two independent client processes. Since update_queue is broadcast, each
    // client then recognised the other's dequeue notice as its own.
    __resetRequestCounter();
    const a = [nextRequestId("input", "aaaaaa"), nextRequestId("cm", "aaaaaa")];
    __resetRequestCounter();
    const b = [nextRequestId("input", "bbbbbb"), nextRequestId("cm", "bbbbbb")];

    expect(a).not.toEqual(b);
    expect(a.filter((id) => b.includes(id))).toEqual([]);
  });

  it("ids stay monotonic and greppable within one instance", () => {
    __resetRequestCounter();
    expect(nextRequestId("input", "abc123")).toBe("input-abc123-1");
    expect(nextRequestId("cm", "abc123")).toBe("cm-abc123-2");
  });

  it("omitting the nonce keeps the legacy shape (used where uniqueness is not needed)", () => {
    __resetRequestCounter();
    expect(nextRequestId("req")).toBe("req-1");
  });

  it("newClientNonce yields distinct values across calls", () => {
    const nonces = new Set(Array.from({ length: 50 }, () => newClientNonce()));
    // Collisions are possible in principle; a run of 50 landing on one value is not.
    expect(nonces.size).toBeGreaterThan(40);
  });
});

describe("contract: server-identity assertion via app_server_info", () => {
  /** Captured verbatim from the live 0.30.19 sole-owner App Server on :4577. */
  const INFO_0_30_19 = {
    type: "app_server_info_response",
    request_id: "probe-1",
    success: true,
    backend: "local",
    letta_code_version: "0.30.19",
    protocol_version: 1,
    capabilities: {
      agent_management: true,
      conversation_management: true,
      memory_management: true,
      runtime_start: true,
      runtime_external_tools_update: true,
      split_channels: false,
    },
  };

  it("pinned version + protocol + capabilities → verified", () => {
    const res = assertServerIdentity(INFO_0_30_19);
    expect(res.verified).toBe(true);
    expect(res.actual).toBe("0.30.19");
    expect(res.protocolVersion).toBe(1);
    expect(res.missingCapabilities).toEqual([]);
  });

  it("the live fixture validates as an inbound frame", () => {
    expect(() => validateInboundFrame(INFO_0_30_19)).not.toThrow();
  });

  it("every contract-verified version passes (0.30.19 and 0.30.20 are both live-validated)", () => {
    for (const v of VALIDATED_SERVER_VERSIONS) {
      const res = assertServerIdentity({ ...INFO_0_30_19, letta_code_version: v });
      expect(res.verified).toBe(true);
      expect(res.actual).toBe(v);
    }
  });

  it("an UNvalidated version + warn policy → warns, no throw", () => {
    const warns: string[] = [];
    const res = assertServerIdentity(
      { ...INFO_0_30_19, letta_code_version: "0.31.0" },
      { policy: "warn", onWarn: (m) => warns.push(m) },
    );
    expect(res.verified).toBe(false);
    expect(res.actual).toBe("0.31.0");
    expect(warns[0]).toMatch(/letta_code_version 0\.31\.0 not in validated set/);
  });

  it("an UNvalidated version + refuse policy → throws", () => {
    expect(() =>
      assertServerIdentity({ ...INFO_0_30_19, letta_code_version: "0.31.0" }, { policy: "refuse" }),
    ).toThrow(ProtocolError);
  });

  it("bumped protocol_version is caught even when the binary version still matches", () => {
    const warns: string[] = [];
    const res = assertServerIdentity(
      { ...INFO_0_30_19, protocol_version: 2 },
      { onWarn: (m) => warns.push(m) },
    );
    expect(res.verified).toBe(false);
    expect(res.protocolVersion).toBe(2);
    expect(warns[0]).toMatch(/protocol_version 2 != pinned 1/);
  });

  it("a required capability advertised false ALWAYS throws, even under warn policy", () => {
    const info = {
      ...INFO_0_30_19,
      capabilities: { ...INFO_0_30_19.capabilities, conversation_management: false },
    };
    expect(() => assertServerIdentity(info, { policy: "warn" })).toThrow(ProtocolError);
    expect(() => assertServerIdentity(info, { policy: "warn" })).toThrow(/conversation_management/);
  });

  it("a capability we do not require being false is not a failure (split_channels)", () => {
    expect(assertServerIdentity(INFO_0_30_19).verified).toBe(true);
  });

  it("absent version field → unverifiable (warn, no throw) — older server, contract test gates", () => {
    const warns: string[] = [];
    const { letta_code_version, ...noVersion } = INFO_0_30_19;
    const res = assertServerIdentity(noVersion, { onWarn: (m) => warns.push(m) });
    expect(res.verified).toBe(false);
    expect(res.actual).toBeNull();
    expect(warns[0]).toMatch(/unverifiable/);
  });
});
