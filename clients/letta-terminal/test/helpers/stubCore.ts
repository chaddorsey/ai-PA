/**
 * A stand-in for ContinuityCore that lets a test drive the render loop frame by frame,
 * with no socket and no server. Frame shapes match the live 0.30.19 captures.
 */

import type { ApprovalEvent, ConnectionState, RenderEvent } from "@ai-pa/letta-continuity-core";
import type { SessionCore } from "../../src/session.js";

const RT = { agent_id: "agent-local-mc", conversation_id: "local-conv-1" };

export class StubCore implements SessionCore {
  private renderCbs: Array<(e: RenderEvent) => void> = [];
  private stateCbs: Array<(s: ConnectionState, prev: ConnectionState) => void> = [];
  private errorCbs: Array<(e: Error) => void> = [];
  private approvalCbs: Array<(e: ApprovalEvent) => void> = [];
  /** Mirrors the core: the previous state is part of the callback contract. */
  private lastState: ConnectionState = "disconnected";
  /** Runs this "client" started — drives ownsRun(), as real attribution would. */
  readonly ownedRuns = new Set<string>();
  /**
   * Runs positively attributed to a peer. Anything in NEITHER set is `unknown`, which is a real
   * outcome the stub must be able to produce: attribution is inferred from stream position and
   * cannot be made exact, and the renderer used to collapse unknown into "peer".
   */
  readonly foreignRuns = new Set<string>();
  readonly sent: string[] = [];
  private seq = 0;

  onRender(cb: (e: RenderEvent) => void): () => void {
    this.renderCbs.push(cb);
    return () => {
      this.renderCbs = this.renderCbs.filter((c) => c !== cb);
    };
  }
  onConnectionState(cb: (s: ConnectionState, prev: ConnectionState) => void): () => void {
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
  onApproval(cb: (e: ApprovalEvent) => void): () => void {
    this.approvalCbs.push(cb);
    return () => {
      this.approvalCbs = this.approvalCbs.filter((c) => c !== cb);
    };
  }
  approval(toolName: string | undefined, requestId = "perm-toolu-1"): void {
    for (const cb of this.approvalCbs) cb({ requestId, toolName, outcome: "denied" });
  }
  ownsRun(runId: string | undefined): boolean {
    return runId !== undefined && this.ownedRuns.has(runId);
  }
  attributeRun(runId: string | undefined): "mine" | "foreign" | "unknown" {
    if (runId === undefined) return "unknown";
    if (this.ownedRuns.has(runId)) return "mine";
    if (this.foreignRuns.has(runId)) return "foreign";
    return "unknown";
  }
  /** Overridable so a test can make the send fail the way a closed socket does. */
  sendImpl: ((text: string) => void) | null = null;
  send(text: string): void {
    if (this.sendImpl) {
      this.sendImpl(text);
      return;
    }
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
    const prev = this.lastState;
    this.lastState = state;
    for (const cb of this.stateCbs) cb(state, prev);
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
    // `own: false` means positively a PEER's, not merely unattributable. A test that wants the
    // unknown case adds the run to neither set.
    if (opts.own) this.ownedRuns.add(runId);
    else this.foreignRuns.add(runId);
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

  /** Set by `queueDepth`; drives the seam so a broadcast-only queue can be modelled. */
  queueMine = true;

  queueHasMine(): boolean {
    return this.queueMine;
  }

  /**
   * `mine` defaults true for the common case. Pass false to model the real broadcast shape: a
   * queue update that reaches a surface with nothing of its own waiting.
   */
  queueDepth(depth: number, mine = true): void {
    this.queueMine = mine;
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
