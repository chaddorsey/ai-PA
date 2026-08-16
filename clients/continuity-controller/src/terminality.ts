/**
 * terminality.ts — the turn-terminality DISJUNCTION (institutional learning, live-verified):
 *
 *   per-run `stop_reason` delta   — the live arm; `requires_approval` is a CONTINUATION
 *                                   (C1 smoke: it fires before every client-side tool step)
 * | `loop_error.is_terminal`      — the fault arm
 * | idle fallback                 — reconnect seams only, decided by the pipeline
 * | wall-clock timeout            — the backstop, coupled to abort (owned by turns.ts)
 *
 * with `subagent_id`-carrying deltas filtered (they journal under the parent, never
 * terminate it), and every run terminalized AT MOST ONCE — the C1 smoke capture showed run
 * N's `turn_finished` arriving after run N's stop_reason delta AND after the next input's
 * `queued` ack, so without per-run dedup a later wait latches the previous turn's tail.
 */

import type { protocol } from "@ai-pa/letta-continuity-core";

type ServerFrame = protocol.ServerFrame;

export interface TerminalSignal {
  kind: "stop_reason" | "loop_error" | "turn_finished";
  runId: string | null;
  /** `end_turn`, `error`, … — whatever the wire said. */
  stopReason: string | null;
  /** True when the signal itself denotes a fault (`loop_error` or stop_reason `error`). */
  failed: boolean;
  errorMessage?: string;
}

const MAX_TERMINALIZED_RUNS = 512;

function runtimeKey(frame: ServerFrame): string | null {
  const runtime = frame.runtime as { agent_id?: string; conversation_id?: string } | undefined;
  if (!runtime || typeof runtime.agent_id !== "string") return null;
  return `${runtime.agent_id}:${runtime.conversation_id}`;
}

export class TerminalityTracker {
  /** Runs that already produced a terminal signal — bounded FIFO per the eviction idiom. */
  private readonly terminalized = new Set<string>();

  /**
   * Classify one frame for one runtime. Returns a TerminalSignal when this frame ENDS the
   * runtime's active turn, null otherwise. Callers filter for the runtime they care about.
   */
  observe(
    frame: ServerFrame,
    runtime: { agent_id: string; conversation_id: string },
  ): TerminalSignal | null {
    const key = runtimeKey(frame);
    if (key !== null && key !== `${runtime.agent_id}:${runtime.conversation_id}`) return null;

    if (frame.type === "stream_delta") {
      if (typeof frame.subagent_id === "string") return null; // subagent activity never terminates the parent
      const delta = frame.delta as
        | {
            message_type?: string;
            stop_reason?: string;
            run_id?: string;
            is_terminal?: boolean;
            message?: string;
          }
        | undefined;
      if (!delta) return null;
      if (delta.message_type === "stop_reason") {
        if (delta.stop_reason === "requires_approval") return null; // continuation, not terminality
        if (!this.freshRun(delta.run_id)) return null;
        return {
          kind: "stop_reason",
          runId: delta.run_id ?? null,
          stopReason: delta.stop_reason ?? null,
          failed: delta.stop_reason === "error",
        };
      }
      if (delta.message_type === "loop_error" && delta.is_terminal === true) {
        if (!this.freshRun(delta.run_id)) return null;
        return {
          kind: "loop_error",
          runId: delta.run_id ?? null,
          stopReason: delta.stop_reason ?? "error",
          failed: true,
          errorMessage: delta.message,
        };
      }
      return null;
    }

    if (frame.type === "turn_finished") {
      const runId = typeof frame.run_id === "string" ? frame.run_id : null;
      if (!this.freshRun(runId ?? undefined)) return null;
      const stopReason = typeof frame.stop_reason === "string" ? frame.stop_reason : null;
      return { kind: "turn_finished", runId, stopReason, failed: stopReason === "error" };
    }

    return null;
  }

  private freshRun(runId: string | undefined): boolean {
    const key = runId ?? "unknown-run";
    if (this.terminalized.has(key)) return false;
    this.terminalized.add(key);
    if (this.terminalized.size > MAX_TERMINALIZED_RUNS) {
      const oldest = this.terminalized.values().next().value;
      if (oldest !== undefined) this.terminalized.delete(oldest);
    }
    return true;
  }
}
