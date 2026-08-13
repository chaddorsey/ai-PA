import { describe, expect, it } from "vitest";
import type { ServerFrame } from "../src/protocol.js";
import { type RenderEvent, StreamAssembler } from "../src/stream.js";

const RT = { agent_id: "a", conversation_id: "c" };

function delta(seq: number, runId: string, id: string, text: string): ServerFrame {
  return {
    type: "stream_delta",
    delta: { id, message_type: "assistant_message", content: text, run_id: runId, type: "message" },
    runtime: RT,
    event_seq: seq,
  };
}
function turnFinished(seq: number, runId: string): ServerFrame {
  return {
    type: "turn_finished",
    turn_id: `b-${runId}`,
    stop_reason: "end_turn",
    run_id: runId,
    runtime: RT,
    event_seq: seq,
  };
}
function loop(seq: number, status: string): ServerFrame {
  return { type: "update_loop_status", loop_status: { status }, runtime: RT, event_seq: seq };
}
function subagents(seq: number): ServerFrame {
  return { type: "update_subagent_state", subagents: [{ name: "x" }], runtime: RT, event_seq: seq };
}

function collect(): { events: RenderEvent[]; asm: StreamAssembler } {
  const asm = new StreamAssembler();
  const events: RenderEvent[] = [];
  asm.onRender((e) => events.push(e));
  return { events, asm };
}

describe("StreamAssembler ordered single stream", () => {
  it("renders a turn: turn_start → delta → turn_finished", () => {
    const { events, asm } = collect();
    asm.ingest(loop(1, "SENDING_API_REQUEST"));
    asm.ingest(delta(2, "run-1", "letta-msg-1", "OK"));
    asm.ingest(turnFinished(3, "run-1"));
    const types = events.map((e) => e.type);
    expect(types).toEqual(["loop_status", "turn_start", "delta", "turn_finished"]);
    const d = events.find((e) => e.type === "delta");
    expect(d?.text).toBe("OK");
    expect(d?.messageId).toBe("letta-msg-1");
  });

  it("renders a FOREIGN turn (different run_id) the same way — no distinction, no merge", () => {
    const { events, asm } = collect();
    asm.ingest(delta(1, "run-own", "letta-msg-1", "mine"));
    asm.ingest(turnFinished(2, "run-own"));
    asm.ingest(delta(3, "run-foreign", "letta-msg-2", "theirs"));
    asm.ingest(turnFinished(4, "run-foreign"));
    const deltas = events.filter((e) => e.type === "delta").map((e) => e.text);
    expect(deltas).toEqual(["mine", "theirs"]);
    const starts = events.filter((e) => e.type === "turn_start").map((e) => e.runId);
    expect(starts).toEqual(["run-own", "run-foreign"]);
  });

  it("renders update_subagent_state inline on the one ordered stream", () => {
    const { events, asm } = collect();
    asm.ingest(delta(1, "run-1", "letta-msg-1", "step"));
    asm.ingest(subagents(2));
    asm.ingest(turnFinished(3, "run-1"));
    expect(events.map((e) => e.type)).toContain("subagent_state");
  });

  it("drops out-of-order-old and duplicate frames (monotonic event_seq)", () => {
    const { events, asm } = collect();
    expect(asm.ingest(delta(5, "run-1", "m-5", "five"))).not.toBeNull();
    expect(asm.ingest(delta(3, "run-1", "m-3", "three"))).toBeNull(); // late
    expect(asm.ingest(delta(5, "run-1", "m-5", "five"))).toBeNull(); // duplicate
    const deltas = events.filter((e) => e.type === "delta").map((e) => e.text);
    expect(deltas).toEqual(["five"]);
  });

  it("ignores non-ordered frames (no event_seq)", () => {
    const { asm } = collect();
    expect(
      asm.ingest({
        type: "conversation_list_response",
        request_id: "x",
        success: true,
      } as ServerFrame),
    ).toBeNull();
  });

  it("reset() clears the per-connection watermark for a new connection", () => {
    const { events, asm } = collect();
    asm.ingest(delta(9, "run-1", "m-9", "old"));
    asm.reset();
    // A new connection restarts event_seq at low numbers — must be accepted after reset.
    expect(asm.ingest(delta(1, "run-2", "m-1", "new"))).not.toBeNull();
    expect(events.filter((e) => e.type === "delta").map((e) => e.text)).toEqual(["old", "new"]);
  });
});
