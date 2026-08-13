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
  approvalRequestId,
  assertServerVersion,
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
    const input = buildInput(RT, "hi") as Record<string, unknown>;
    expect(input.type).toBe("input");
    expect(input.payload).toEqual({
      kind: "create_message",
      messages: [{ role: "user", content: "hi" }],
    });
  });

  it("conversation RPC builders + response map", () => {
    expect((buildConversationList("c1", "a") as Record<string, unknown>).type).toBe(
      "conversation_list",
    );
    expect((buildConversationCreate("c2", "a", "T") as Record<string, unknown>).title).toBe("T");
    expect(
      (buildConversationMessagesList("c3", RT) as Record<string, unknown>).conversation_id,
    ).toBe(RT.conversation_id);
    expect(RpcResponseFor[Outbound.conversationList]).toBe(Inbound.conversationListResponse);
    expect(RpcResponseFor[Outbound.conversationCreate]).toBe(Inbound.conversationCreateResponse);
  });

  it("approval_send fails CLOSED with decision deny", () => {
    const f = buildApprovalSend("a1", RT, "appr-1", "deny") as Record<string, unknown>;
    expect(f.type).toBe(Outbound.approvalSend);
    expect(f.decision).toBe("deny");
    expect(f.approval_request_id).toBe("appr-1");
  });
});

describe("contract: server-version assertion at the hello", () => {
  it("absent version → unverifiable (warn, no throw) — relies on contract test", () => {
    const warns: string[] = [];
    const res = assertServerVersion(FIXTURES.runtime_start_response, {
      onWarn: (m) => warns.push(m),
    });
    expect(res).toEqual({ verified: false, actual: null, pinned: "0.30.19" });
    expect(warns[0]).toMatch(/unverifiable/);
  });

  it("matching version → verified", () => {
    const hello = { ...FIXTURES.runtime_start_response, server_version: "0.30.19" };
    expect(assertServerVersion(hello).verified).toBe(true);
  });

  it("mismatched version + refuse policy → throws", () => {
    const hello = { ...FIXTURES.runtime_start_response, server_version: "0.31.0" };
    expect(() => assertServerVersion(hello, { policy: "refuse" })).toThrow(ProtocolError);
  });

  it("mismatched version + warn policy → warns, no throw", () => {
    const hello = { ...FIXTURES.runtime_start_response, version: "0.31.0" };
    const warns: string[] = [];
    const res = assertServerVersion(hello, { policy: "warn", onWarn: (m) => warns.push(m) });
    expect(res.verified).toBe(false);
    expect(res.actual).toBe("0.31.0");
    expect(warns[0]).toMatch(/drift/);
  });
});
