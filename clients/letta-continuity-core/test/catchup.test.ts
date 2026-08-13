import { describe, expect, it } from "vitest";
import { LiveDedup, messagesListRequest, snapshotFromResponse } from "../src/catchup.js";
import type { MessagesListResponseFrame } from "../src/protocol.js";

function resp(ids: string[]): MessagesListResponseFrame {
  return {
    type: "conversation_messages_list_response",
    request_id: "cml-1",
    success: true,
    messages: ids.map((id) => ({ id })),
    next_before: null,
    has_more: false,
    error: null,
  };
}

describe("catchup snapshot + message-id watermark dedup", () => {
  it("snapshotFromResponse collects message ids into the watermark", () => {
    const snap = snapshotFromResponse(resp(["letta-msg-1", "letta-msg-2"]));
    expect(snap.seenMessageIds).toEqual(new Set(["letta-msg-1", "letta-msg-2"]));
    expect(snap.messages).toHaveLength(2);
  });

  it("drops replay of a snapshot message, admits a genuinely new message", () => {
    const dedup = new LiveDedup(snapshotFromResponse(resp(["letta-msg-A"])));
    expect(dedup.admit("letta-msg-A")).toBe(false); // replay → drop (no duplicate)
    expect(dedup.admit("letta-msg-B")).toBe(true); // new → render (no loss)
  });

  it("admits EVERY delta of a new message (deltas share one delta.id)", () => {
    const dedup = new LiveDedup(snapshotFromResponse(resp(["letta-msg-A"])));
    // A new message streams many deltas sharing one id — all must render.
    expect(dedup.admit("letta-msg-NEW")).toBe(true);
    expect(dedup.admit("letta-msg-NEW")).toBe(true);
    expect(dedup.admit("letta-msg-NEW")).toBe(true);
  });

  it("keeps dropping replays of a snapshot message across repeated frames", () => {
    const dedup = new LiveDedup(snapshotFromResponse(resp(["letta-msg-A"])));
    expect(dedup.admit("letta-msg-A")).toBe(false);
    expect(dedup.admit("letta-msg-A")).toBe(false);
  });

  it("messagesListRequest shapes the RPC frame from protocol.ts", () => {
    const f = messagesListRequest("cml-9", { agent_id: "a", conversation_id: "c" }) as Record<
      string,
      unknown
    >;
    expect(f.type).toBe("conversation_messages_list");
    expect(f.conversation_id).toBe("c");
  });
});
