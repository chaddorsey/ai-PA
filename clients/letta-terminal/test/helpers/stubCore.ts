/**
 * A stand-in for ContinuityCore that lets a test drive the render loop frame by frame,
 * with no socket and no server. Frame shapes match the live 0.30.19 captures.
 */

import type { ConnectionState, RenderEvent } from "@ai-pa/letta-continuity-core";
import type { SessionCore } from "../../src/session.js";

const RT = { agent_id: "agent-local-mc", conversation_id: "local-conv-1" };

export class StubCore implements SessionCore {
  private renderCbs: Array<(e: RenderEvent) => void> = [];
  private stateCbs: Array<(s: ConnectionState) => void> = [];
  private errorCbs: Array<(e: Error) => void> = [];
  /** Runs this "client" started — drives ownsRun(), as real attribution would. */
  readonly ownedRuns = new Set<string>();
  readonly sent: string[] = [];
  private seq = 0;

  onRender(cb: (e: RenderEvent) => void): () => void {
    this.renderCbs.push(cb);
    return () => {
      this.renderCbs = this.renderCbs.filter((c) => c !== cb);
    };
  }
  onConnectionState(cb: (s: ConnectionState) => void): () => void {
    this.stateCbs.push(cb);
    return () => {
      this.stateCbs = this.stateCbs.filter((c) => c !== cb);
    };
  }
  onError(cb: (e: Error) => void): () => void {
    this.errorCbs.push(cb);
    return () => {
      this.errorCbs = this.errorCbs.filter((c) => c !== cb);
    };
  }
  ownsRun(runId: string | undefined): boolean {
    return runId !== undefined && this.ownedRuns.has(runId);
  }
  send(text: string): void {
    this.sent.push(text);
  }

  // ── drivers ──────────────────────────────────────────────────────────────

  emit(event: Partial<RenderEvent> & { type: RenderEvent["type"] }): void {
    this.seq += 1;
    const full: RenderEvent = {
      eventSeq: this.seq,
      frame: { type: "stub" },
      ...event,
    } as RenderEvent;
    for (const cb of this.renderCbs) cb(full);
  }

  setState(state: ConnectionState): void {
    for (const cb of this.stateCbs) cb(state);
  }

  fail(message: string): void {
    for (const cb of this.errorCbs) cb(new Error(message));
  }

  /** A whole turn: start → assistant deltas → finish. `own` decides attribution. */
  turn(
    runId: string,
    chunks: string[],
    opts: { own: boolean; messageId?: string } = { own: true },
  ): void {
    if (opts.own) this.ownedRuns.add(runId);
    this.emit({ type: "turn_start", runId });
    // Each chunk gets its OWN message id, exactly as the live server does — a stub that
    // reused one id per message hid the bug where every chunk got its own labelled line.
    for (const [i, text] of chunks.entries()) {
      this.emit({
        type: "delta",
        runId,
        messageId: opts.messageId ?? `letta-msg-${runId}-${i}`,
        messageType: "assistant_message",
        text,
      });
    }
    this.ownedRuns.delete(runId); // released at turn end, exactly like the real core
    this.emit({ type: "turn_finished", runId, stopReason: "end_turn" });
  }

  queueDepth(depth: number): void {
    this.emit({
      type: "queue",
      frame: {
        type: "update_queue",
        queue: Array.from({ length: depth }, (_, i) => ({ id: `q-${i + 1}` })),
        removed: [],
        runtime: RT,
      },
    });
  }

  subagents(count: number): void {
    this.emit({
      type: "subagent_state",
      frame: {
        type: "update_subagent_state",
        subagents: Array.from({ length: count }, (_, i) => ({ id: `sub-${i}` })),
        runtime: RT,
      },
    });
  }
}
