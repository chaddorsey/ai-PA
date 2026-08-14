/**
 * ownership.ts — which runs on the shared conversation are OURS.
 *
 * The approval policy (M1) is "the injecting client auto-denies; observers stay silent".
 * That needs an exact answer to "is this approval for a turn I started?" — a bare
 * outstanding-turn counter cannot answer it, because on a shared conversation a FOREIGN
 * turn's `turn_finished` decrements the same counter. The two failure modes are symmetric
 * and both bad: zeroing early means we do NOT deny our own approval and the turn hangs both
 * surfaces; staying non-zero means we DO deny a foreign approval (a duplicate deny).
 *
 * The server gives us everything needed to do this exactly (verified live on 0.30.19):
 *
 *   send `input` with a `request_id` + `client_message_id`
 *     → `input_accepted{request_id, accepted, disposition}`
 *         disposition "started"  → our turn is the one beginning now; claim the next new run
 *         disposition "queued"   → we sit behind another turn; our `client_message_id` appears
 *                                  in `update_queue.queue`, and when it leaves as
 *                                  `removed:[{client_message_id, disposition:"dequeued"}]`
 *                                  our turn is the one beginning next → claim the next new run
 *         accepted:false         → nothing of ours will run; drop the claim
 *     → the claimed `run_id` is owned until its `turn_finished` arrives
 *
 * Claims are FIFO: the server runs one turn at a time per {agent, conversation}, so the
 * order in which our claims arm is the order our runs start.
 *
 * LOAD-BEARING ASSUMPTION: an armed claim takes the next new run id it sees. This is sound
 * only because the server serializes turns per {agent, conversation} (Unit 1) — "started"
 * means OUR run is the active one, so no foreign run can begin before it. If that
 * serialization guarantee ever changes, this attribution breaks and the approval policy has
 * to be rebuilt on an explicit run id in the ack instead.
 *
 * `client_message_id`s are broadcast to every client, so a peer sees ours and we see theirs —
 * but each only ever matches its OWN values, which is what makes the attribution safe.
 */

export type ClaimState = "awaiting-ack" | "queued" | "armed";

interface Claim {
  requestId: string;
  clientMessageId: string;
  state: ClaimState;
}

export interface OwnershipSnapshot {
  owned: string[];
  pending: number;
  degraded: boolean;
}

export class RunOwnership {
  /** Claims not yet bound to a run, in submission order. */
  private readonly claims: Claim[] = [];
  /** run_id → the request_id that produced it. */
  private readonly owned = new Map<string, string>();
  /** Every run_id ever attributed, so "new run" means genuinely new. */
  private readonly seenRuns = new Set<string>();
  /**
   * True when a reconnect may have hidden the frames that would have resolved a claim.
   * While degraded with claims outstanding we fall back to fail-CLOSED behaviour: treat an
   * unattributable approval as ours and deny it. Over-denying is recoverable; a hung turn
   * on every surface is not.
   */
  private degraded = false;

  /** Record a send. Call with the same ids used to build the `input` frame. */
  beginSend(requestId: string, clientMessageId: string): void {
    this.claims.push({ requestId, clientMessageId, state: "awaiting-ack" });
  }

  /** Apply an `input_accepted` ack. Unknown request_ids (a peer's) are ignored. */
  onInputAccepted(requestId: string, accepted: boolean, disposition?: string): void {
    const claim = this.claims.find((c) => c.requestId === requestId);
    if (!claim) return;
    if (!accepted) {
      this.drop(claim);
      return;
    }
    // "started" and "submitting" both mean a run is beginning for us now, so both arm.
    // Only the explicit "queued" waits for a dequeue notice. An UNKNOWN (future) disposition
    // also arms, deliberately: arming risks over-claiming a run and over-denying an approval,
    // which is recoverable, whereas failing to arm risks not denying our own approval and
    // hanging every surface. The M1 policy prefers the recoverable failure.
    claim.state = disposition === "queued" ? "queued" : "armed";
  }

  /** Apply `update_queue.removed`. Our dequeue arms the claim; a cancel drops it. */
  onQueueRemovals(removals: Array<{ client_message_id: string; disposition: string }>): void {
    for (const removal of removals) {
      const claim = this.claims.find((c) => c.clientMessageId === removal.client_message_id);
      if (!claim) continue; // a peer's message
      if (removal.disposition === "dequeued") claim.state = "armed";
      else this.drop(claim); // "cancelled" (or anything else): it will never run
    }
  }

  /**
   * Attribute a run id seen on the stream. The first sighting of a new run claims the oldest
   * armed claim; later sightings of the same run are no-ops.
   */
  onRunObserved(runId: string): void {
    if (this.seenRuns.has(runId)) return;
    this.seenRuns.add(runId);
    const index = this.claims.findIndex((c) => c.state === "armed");
    if (index === -1) return; // a foreign turn
    const [claim] = this.claims.splice(index, 1);
    if (claim) this.owned.set(runId, claim.requestId);
  }

  /** Release a finished run. Foreign run ids are ignored. */
  onTurnFinished(runId: string): void {
    this.seenRuns.add(runId);
    this.owned.delete(runId);
    if (this.owned.size === 0 && this.claims.length === 0) this.degraded = false;
  }

  /**
   * Should THIS client respond to an approval for `runId`?
   *
   * Exact when the run is attributable. When the run id is absent or unknown AND we are
   * degraded with work outstanding, answer true — fail closed, per the M1 policy that an
   * approval-gated turn must resolve to a bounded deny rather than hang every surface.
   */
  shouldRespondToApproval(runId: string | undefined): boolean {
    if (runId !== undefined && this.owned.has(runId)) return true;
    if (runId !== undefined && this.seenRuns.has(runId)) return false; // attributed elsewhere
    return this.degraded && this.hasOutstanding();
  }

  owns(runId: string): boolean {
    return this.owned.has(runId);
  }

  hasOutstanding(): boolean {
    return this.owned.size > 0 || this.claims.length > 0;
  }

  /**
   * A reconnect may have hidden an ack, a dequeue, or a turn_finished. Claims and owned runs
   * are KEPT (our turn may still be running server-side and its `turn_finished` will arrive
   * on the new connection), but attribution is no longer trustworthy, so unknown approvals
   * fail closed until everything outstanding drains.
   */
  onReconnect(): void {
    if (this.hasOutstanding()) this.degraded = true;
  }

  snapshot(): OwnershipSnapshot {
    return {
      owned: [...this.owned.keys()],
      pending: this.claims.length,
      degraded: this.degraded,
    };
  }

  private drop(claim: Claim): void {
    const index = this.claims.indexOf(claim);
    if (index !== -1) this.claims.splice(index, 1);
  }
}
