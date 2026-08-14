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
  Inbound,
  Outbound,
  ProtocolError,
  RpcResponseFor,
  type ServerFrame,
  VALIDATED_SERVER_VERSIONS,
  approvalRequestId,
  assertServerIdentity,
  buildApprovalSend,
  buildConversationCreate,
  buildConversationList,
  buildConversationMessagesList,
  buildInput,
  buildRuntimeStart,
  deltaMessageId,
  deltaMessageType,
  deltaText,
  frameEventSeq,
  isApprovalRequest,
  isLoopStatus,
  isQueue,
  isStreamDelta,
  isSubagentState,
  isTurnFinished,
  parseFrame,
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
  update_queue: { type: "update_queue", queue: [], removed: [], ...meta, event_seq: 3 },
  update_subagent_state: { type: "update_subagent_state", subagents: [], ...meta, event_seq: 4 },
  update_device_status: {
    type: "update_device_status",
    device_status: { is_online: true, is_processing: false },
    ...meta,
    event_seq: 1,
  },
  approval_request_message: {
    type: "approval_request_message",
    approval_request_id: "appr-1",
    run_id: "local-run-9",
    ...meta,
    event_seq: 20,
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
    const ap = parseFrame(JSON.stringify(FIXTURES.approval_request_message));
    expect(isApprovalRequest(ap)).toBe(true);
    if (!isApprovalRequest(ap)) throw new Error("guard");
    expect(approvalRequestId(ap)).toBe("appr-1");
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

  it("approval_send fails CLOSED with decision deny", () => {
    const f = buildApprovalSend("a1", RT, "appr-1", "deny") as Record<string, unknown>;
    expect(f.type).toBe(Outbound.approvalSend);
    expect(f.decision).toBe("deny");
    expect(f.approval_request_id).toBe("appr-1");
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
