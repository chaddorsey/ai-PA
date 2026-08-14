import { describe, expect, it } from "vitest";
import { LiveDedup, snapshotFromResponse } from "../src/catchup.js";
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
  });

  it("drops replay of a snapshot message, admits a genuinely new message", () => {
    const dedup = new LiveDedup(snapshotFromResponse(resp(["letta-msg-A"])));
    expect(dedup.admit("letta-msg-A")).toBe(false); // replay → drop (no duplicate)
    expect(dedup.admit("letta-msg-B")).toBe(true); // new → render (no loss)
  });

  it("admits a repeated id every time (never adds live ids to the drop-set)", () => {
    // RETITLED, deliberately. This used to be called "admits EVERY delta of a new message
    // (deltas share one delta.id)" and its comment asserted that premise as fact. Live capture
    // disproves it: every chunk of one message carries a DISTINCT delta.id (letta-msg-27370,
    // -27371, …); `otid` is what stays constant per message. The behaviour under test is still
    // correct and still worth pinning — newly-seen ids are never added to the drop-set — but it
    // must not be justified by a premise the code's own ⚠️ block records as false.
    const dedup = new LiveDedup(snapshotFromResponse(resp(["letta-msg-A"])));
    expect(dedup.admit("letta-msg-NEW")).toBe(true);
    expect(dedup.admit("letta-msg-NEW")).toBe(true);
    expect(dedup.admit("letta-msg-NEW")).toBe(true);
  });

  it("keeps dropping replays of a snapshot message across repeated frames", () => {
    const dedup = new LiveDedup(snapshotFromResponse(resp(["letta-msg-A"])));
    expect(dedup.admit("letta-msg-A")).toBe(false);
    expect(dedup.admit("letta-msg-A")).toBe(false);
  });
});
