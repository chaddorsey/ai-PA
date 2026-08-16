/**
 * The terminality disjunction, arm by arm — including the two traps the C1 captures surfaced:
 * `requires_approval` fires on EVERY tool step (continuation, not terminality), and a run's
 * `turn_finished` can arrive after its own stop_reason delta (must not terminalize twice).
 */

import { describe, expect, it } from "vitest";
import { TerminalityTracker } from "../src/terminality.js";

const RUNTIME = { agent_id: "ag-1", conversation_id: "local-conv-1" };
const OTHER = { agent_id: "ag-2", conversation_id: "local-conv-9" };

function stopDelta(runId: string, stopReason: string, extra: Record<string, unknown> = {}) {
  return {
    type: "stream_delta",
    runtime: RUNTIME,
    event_seq: 1,
    delta: { message_type: "stop_reason", stop_reason: stopReason, run_id: runId },
    ...extra,
  };
}

describe("TerminalityTracker", () => {
  it("stop_reason end_turn terminates; requires_approval is a CONTINUATION", () => {
    const t = new TerminalityTracker();
    expect(t.observe(stopDelta("run-1", "requires_approval"), RUNTIME)).toBeNull();
    const signal = t.observe(stopDelta("run-1", "end_turn"), RUNTIME);
    expect(signal?.kind).toBe("stop_reason");
    expect(signal?.failed).toBe(false);
  });

  it("a run terminalizes AT MOST once: the late turn_finished after its stop_reason is absorbed", () => {
    const t = new TerminalityTracker();
    expect(t.observe(stopDelta("run-1", "end_turn"), RUNTIME)).not.toBeNull();
    const late = t.observe(
      { type: "turn_finished", runtime: RUNTIME, event_seq: 2, turn_id: "t", stop_reason: "end_turn", run_id: "run-1" },
      RUNTIME,
    );
    expect(late).toBeNull();
    // …and the NEXT run's terminality is untouched by the dedup.
    expect(t.observe(stopDelta("run-2", "end_turn"), RUNTIME)).not.toBeNull();
  });

  it("loop_error is terminal only when is_terminal, and reports failure", () => {
    const t = new TerminalityTracker();
    const nonTerminal = t.observe(
      {
        type: "stream_delta",
        runtime: RUNTIME,
        event_seq: 1,
        delta: { message_type: "loop_error", is_terminal: false, run_id: "run-1", message: "retrying" },
      },
      RUNTIME,
    );
    expect(nonTerminal).toBeNull();
    const terminal = t.observe(
      {
        type: "stream_delta",
        runtime: RUNTIME,
        event_seq: 2,
        delta: { message_type: "loop_error", is_terminal: true, run_id: "run-1", message: "provider 404" },
      },
      RUNTIME,
    );
    expect(terminal?.failed).toBe(true);
    expect(terminal?.errorMessage).toBe("provider 404");
  });

  it("subagent deltas never terminate the parent turn", () => {
    const t = new TerminalityTracker();
    expect(t.observe(stopDelta("run-sub", "end_turn", { subagent_id: "sub-1" }), RUNTIME)).toBeNull();
  });

  it("frames for a different runtime are ignored", () => {
    const t = new TerminalityTracker();
    expect(t.observe(stopDelta("run-1", "end_turn"), OTHER)).toBeNull();
  });

  it("turn_finished with stop_reason error reports failure", () => {
    const t = new TerminalityTracker();
    const signal = t.observe(
      { type: "turn_finished", runtime: RUNTIME, event_seq: 3, turn_id: "t", stop_reason: "error", run_id: "run-9" },
      RUNTIME,
    );
    expect(signal?.failed).toBe(true);
  });
});
