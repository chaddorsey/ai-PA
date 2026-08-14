/**
 * stream.ts — one ordered event stream keyed by per-connection `event_seq`.
 *
 * Unit 1 proved a SINGLE `/ws` connection receives ALL broadcasts for its subscribed
 * `{agent, conversation}` — own turns, foreign turns, and subagent state — each frame
 * carrying a monotonic `event_seq`. So there is no second observer connection and no
 * cross-stream merge: render in `event_seq` order off the one stream. `turn_finished`
 * (which arrives for ALL turns on raw WS, unlike the SDK) plus `loop_status` mark boundaries.
 *
 * `event_seq` is PER-CONNECTION and resets on reconnect — this assembler only orders WITHIN
 * one connection. The replay↔live seam across a reconnect is deduped on message-id by
 * catchup.ts, not here. Call `reset()` when a new connection is established.
 */

import { fanOut } from "./fanout.js";
import {
  LoopStatuses,
  type ServerFrame,
  deltaMessageId,
  deltaMessageType,
  deltaText,
  frameEventSeq,
  isLoopStatus,
  isQueue,
  isStreamDelta,
  isSubagentState,
  isTurnFinished,
} from "./protocol.js";

export type RenderEventType =
  | "delta"
  | "subagent_state"
  | "queue"
  | "loop_status"
  | "turn_start"
  | "turn_finished";

export interface RenderEvent {
  type: RenderEventType;
  eventSeq: number;
  runId?: string;
  /** delta only */
  messageId?: string;
  messageType?: string;
  text?: string;
  /** loop_status only */
  status?: string;
  /** turn_finished only */
  stopReason?: string;
  /** the raw frame, for consumers that need more */
  frame: ServerFrame;
}

export type RenderListener = (event: RenderEvent) => void;

export class StreamAssembler {
  /** Highest event_seq delivered on the current connection; drops late/duplicate frames. */
  private lastEventSeq = -1;
  /** run_id of the turn currently rendering, if any (used to emit turn_start once). */
  private activeRunId: string | null = null;
  private readonly listeners = new Set<RenderListener>();

  onRender(listener: RenderListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** New connection → per-connection `event_seq` restarts; forget the ordering watermark. */
  reset(): void {
    this.lastEventSeq = -1;
    this.activeRunId = null;
  }

  /**
   * Feed one parsed broadcast frame. Non-broadcast frames (RPC responses) are ignored here.
   * Returns the emitted RenderEvent, or null if the frame was dropped (late/dup/non-ordered).
   */
  ingest(frame: ServerFrame): RenderEvent | null {
    const seq = frameEventSeq(frame);
    if (seq === undefined) return null; // RPC responses / hello — not part of the ordered stream
    // Drop out-of-order-old and duplicate frames: delivery is monotonic in event_seq.
    if (seq <= this.lastEventSeq) return null;
    this.lastEventSeq = seq;

    if (isStreamDelta(frame)) {
      const runId = typeof frame.delta.run_id === "string" ? frame.delta.run_id : undefined;
      this.maybeEmitTurnStart(seq, runId, frame);
      return this.emit({
        type: "delta",
        eventSeq: seq,
        runId,
        messageId: deltaMessageId(frame),
        messageType: deltaMessageType(frame),
        text: deltaText(frame),
        frame,
      });
    }
    if (isSubagentState(frame)) {
      return this.emit({ type: "subagent_state", eventSeq: seq, frame });
    }
    if (isQueue(frame)) {
      return this.emit({ type: "queue", eventSeq: seq, frame });
    }
    if (isLoopStatus(frame)) {
      const status = frame.loop_status.status;
      // Returning to WAITING_ON_INPUT closes any active turn (belt-and-suspenders with turn_finished).
      if (status === LoopStatuses.waitingOnInput) this.activeRunId = null;
      return this.emit({ type: "loop_status", eventSeq: seq, status, frame });
    }
    if (isTurnFinished(frame)) {
      const runId = typeof frame.run_id === "string" ? frame.run_id : undefined;
      this.activeRunId = null;
      return this.emit({
        type: "turn_finished",
        eventSeq: seq,
        runId,
        stopReason: frame.stop_reason,
        frame,
      });
    }
    // Other ordered broadcasts (e.g. update_device_status) are accepted for ordering but not rendered.
    return null;
  }

  private maybeEmitTurnStart(seq: number, runId: string | undefined, frame: ServerFrame): void {
    if (runId && runId !== this.activeRunId) {
      this.activeRunId = runId;
      this.emit({ type: "turn_start", eventSeq: seq, runId, frame });
    }
  }

  private emit(event: RenderEvent): RenderEvent {
    fanOut(this.listeners, [event]);
    return event;
  }
}
