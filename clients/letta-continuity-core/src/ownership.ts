/**
 * ownership.ts — which runs on the shared conversation are OURS.
 *
 * SCOPE (narrowed 2026-08-13). This module used to decide whether to answer a tool approval. It
 * no longer does: the server broadcasts each approval to every subscriber and settles the race
 * itself, so answering is unconditional and needs no attribution
 * (docs/plans/2026-08-13-approval-contract-findings.md). What remains is still worth getting
 * right, but it is UX and bookkeeping, not safety:
 *   • labelling a turn as ours vs a peer's, which is the visible proof of cross-surface continuity
 *   • knowing whether we have work in flight, so state can be bounded
 *
 * How attribution works (frame shapes verified live on 0.30.19):
 *
 *   send `input` with a `request_id` + `client_message_id`
 *     → `input_accepted{request_id, accepted, disposition}`   (UNICAST — peers do not see ours)
 *         "started"/"submitting" → our run is beginning now; claim the next new run
 *         "queued"               → our `client_message_id` sits in `update_queue`; when it leaves
 *                                  as `removed:[{client_message_id, disposition:"dequeued"}]`
 *                                  our run is next
 *         accepted:false         → nothing of ours will run; drop the claim
 *     → the claimed `run_id` is owned until its `turn_finished`
 *
 * Claims are FIFO: the server runs one turn at a time per {agent, conversation}, so the order our
 * claims arm is the order our runs start.
 *
 * LOAD-BEARING ASSUMPTION: an armed claim takes the next new run id it sees. Sound only because
 * the server serializes turns — "started" means OUR run is the active one. Across a reconnect that
 * reasoning does not hold (an unknown number of runs may have begun and ended unseen), so armed
 * claims are demoted at the seam rather than carried.
 *
 * Attribution is INFERRED FROM STREAM POSITION, not read from the wire: no frame carries both our
 * `client_message_id` and a `run_id`. `conversation_messages_list` does echo our
 * `client_message_id` as `otid`, but with no `run_id`, so exact mapping is unavailable. This is an
 * accepted, bounded risk — the consequence of getting it wrong is now a mislabelled turn, not a
 * hung conversation.
 */

import { InputDispositions, QueueDispositions, StopReasons } from "./protocol.js";

/**
 * Upper bound on remembered run ids. Sets preserve insertion order, so the oldest is evicted
 * first. Attribution only needs recent runs; this is generous by orders of magnitude.
 */
const MAX_REMEMBERED_RUNS = 2_000;

export type ClaimState = "awaiting-ack" | "queued" | "armed" | "lost";

/** How a run relates to this client. See RunOwnership.attribute. */
export type Attribution = "mine" | "foreign" | "unknown";

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
   * client_message_ids whose queue transition we have already applied — replay detection.
   * Capped like seenRuns: this client is meant to sit attached for days, so "grows with the send
   * rate" is not a bound.
   */
  private readonly consumedMessageIds = new Set<string>();
  /** Runs positively attributed to a peer — seen while we held nothing outstanding. */
  private readonly foreignRuns = new Set<string>();
  private lastActivity: number;
  private readonly clock: () => number;
  /**
   * DIAGNOSTIC ONLY. True when something may have hidden the frames that would have resolved a
   * claim — a reconnect, or a queue disposition we do not understand — so `attribute()` should be
   * read as low-confidence until everything outstanding drains. No behaviour branches on it.
   *
   * It used to describe a fail-CLOSED approval fallback. That code is gone: approvals no longer
   * consult attribution at all, because the server broadcasts each request and settles the race
   * itself. Leaving the old wording here invited exactly the reintroduction that would hang every
   * surface.
   */
  private degraded = false;

  constructor(opts: { clock?: () => number } = {}) {
    this.clock = opts.clock ?? (() => Date.now());
    this.lastActivity = this.clock();
  }

  /** Record a send. Call with the same ids used to build the `input` frame. */
  beginSend(requestId: string, clientMessageId: string): void {
    this.touch();
    this.claims.push({ requestId, clientMessageId, state: "awaiting-ack" });
  }

  /** Drop a claim whose `input` never reached the wire (the send threw). */
  abandon(requestId: string): void {
    const claim = this.claims.find((c) => c.requestId === requestId);
    if (claim) this.drop(claim);
  }

  /** Apply an `input_accepted` ack. Unknown request_ids (a peer's) are ignored. */
  onInputAccepted(requestId: string, accepted: boolean, disposition?: string): void {
    // An ack is forward progress. Without this the idle reaper measures from the last stream
    // frame, so a send that is acked and then waits quietly in the queue looks idle.
    this.touch();
    const claim = this.claims.find((c) => c.requestId === requestId);
    if (!claim) return;
    if (!accepted) {
      this.drop(claim);
      return;
    }
    // "started" and "submitting" both mean a run is beginning for us now, so both arm; only
    // "queued" waits for a dequeue notice. An UNKNOWN disposition PARKS rather than arms. The
    // original rationale for arming was that failing to arm risked not denying our own approval —
    // but approvals no longer consult attribution at all, so arming now only risks binding a run
    // that is not ours and mislabelling it. Parking yields "unknown", which is the honest answer.
    claim.state =
      disposition === InputDispositions.started || disposition === InputDispositions.submitting
        ? "armed"
        : "queued";
  }

  /**
   * Apply `update_queue.removed`. Our dequeue arms the claim; an explicit cancel drops it.
   *
   * SINGLE-SHOT BY DESIGN. `update_queue` is broadcast to every subscriber, so our
   * `client_message_id` is on every peer's wire — unpredictable ids (protocol.newClientNonce)
   * stop accidental *collisions* but cannot stop a deliberate or accidental *replay*. A claim may
   * therefore leave `queued` exactly once: a removal naming a claim that is not currently queued
   * is ignored and reported as an anomaly rather than mutating state.
   *
   * The dangerous case this closes is a replayed `cancelled`, which previously deleted an already
   * armed or bound claim — so we would never own our run, never answer its approval, and hang the
   * turn. That is the non-recoverable side of the policy's asymmetry. It also hardens attribution
   * against benign frame redelivery on reconnect, which is the stronger everyday justification.
   */
  onQueueRemovals(
    removals: Array<{ client_message_id: string; disposition: string }>,
    onAnomaly?: (msg: string) => void,
  ): void {
    this.touch();
    for (const removal of removals) {
      const claim = this.claims.find((c) => c.clientMessageId === removal.client_message_id);
      if (!claim) {
        // Either a peer's message (overwhelmingly the common case) or a replay of one of ours
        // that we already consumed. Both are no-ops; only the latter is worth reporting, and we
        // can distinguish them because we remember the ids we minted.
        if (this.consumedMessageIds.has(removal.client_message_id)) {
          onAnomaly?.(
            `duplicate queue removal for ${removal.client_message_id} (${removal.disposition}) — ignored`,
          );
        }
        continue;
      }
      if (claim.state !== "queued") {
        onAnomaly?.(
          `queue removal for ${removal.client_message_id} arrived while the claim was "${claim.state}" — ignored`,
        );
        continue;
      }
      if (removal.disposition === QueueDispositions.dequeued) {
        this.consume(removal.client_message_id);
        claim.state = "armed";
      } else if (removal.disposition === QueueDispositions.cancelled) {
        this.consume(removal.client_message_id);
        this.drop(claim); // an explicit cancel: it will never run
      } else {
        // Anything else is drift, and `else = cancelled` was the wrong default: a renamed or
        // newly-added disposition would silently destroy a live claim, after which our own turns
        // render under the peer label. Hold the claim, say so, and let attribution degrade
        // honestly rather than confidently reporting the opposite of the truth.
        this.degraded = true;
        onAnomaly?.(
          `unknown queue disposition "${removal.disposition}" for ${removal.client_message_id} — claim held, attribution degraded`,
        );
      }
    }
  }

  /**
   * Attribute a run id seen on the stream. The first sighting of a new run claims the oldest
   * armed claim; later sightings of the same run are no-ops.
   */
  onRunObserved(runId: string): void {
    this.touch();
    if (this.seenRuns.has(runId)) return;
    this.remember(runId);
    const index = this.claims.findIndex((c) => c.state === "armed");
    if (index === -1) {
      // Only POSITIVELY foreign when we had nothing outstanding at all. If we hold a queued or
      // awaiting-ack claim this run may still turn out to be ours (the dequeue notice can be in
      // flight), so it stays "unknown" rather than being written off as a peer's.
      if (!this.hasOutstanding()) this.foreignRuns.add(runId);
      return;
    }
    const [claim] = this.claims.splice(index, 1);
    if (claim) this.owned.set(runId, claim.requestId);
  }

  /**
   * Release a finished run. Foreign run ids are ignored.
   *
   * `requires_approval` is NOT a finish. The server emits `turn_finished` with that stop reason
   * while the turn is still parked waiting on an approval, so releasing there would make a late
   * approval read as somebody else's and would let expiry reap a run that is very much alive.
   */
  onTurnFinished(runId: string, stopReason?: string): void {
    this.touch();
    if (stopReason === StopReasons.requiresApproval) return;
    this.remember(runId);
    this.owned.delete(runId);
    if (this.owned.size === 0 && this.claims.length === 0) this.degraded = false;
  }

  /**
   * Classify a run: ours, positively a peer's, or not attributable.
   *
   * `positivelyForeign` has an OBSERVABLE definition — a run first seen at a moment when we held
   * zero claims and zero owned runs, so nothing of ours could have been starting. "Seen while we
   * were queued" is emphatically NOT foreign: treating it that way is what previously made a lost
   * ack silently unattributable.
   */
  attribute(runId: string | undefined): Attribution {
    if (runId === undefined) return "unknown";
    if (this.owned.has(runId)) return "mine";
    if (this.foreignRuns.has(runId)) return "foreign";
    return "unknown";
  }

  owns(runId: string): boolean {
    return this.owned.has(runId);
  }

  /** Whether any of these queued client_message_ids is one of ours. */
  ownsAnyMessage(clientMessageIds: readonly string[]): boolean {
    return clientMessageIds.some((id) => this.claims.some((c) => c.clientMessageId === id));
  }

  hasOutstanding(): boolean {
    return this.owned.size > 0 || this.claims.length > 0;
  }

  /**
   * A reconnect may have hidden an ack, a dequeue, or a turn_finished. Claims and owned runs
   * are KEPT (our turn may still be running server-side and its `turn_finished` will arrive
   * on the new connection), but attribution is no longer trustworthy, so runs are reported as
   * low-confidence until everything outstanding drains.
   */
  onReconnect(): void {
    this.touch();
    if (this.hasOutstanding()) this.degraded = true;
    // An armed claim means "take the NEXT new run". That reasoning depends on an uninterrupted
    // stream; across a gap an unknown number of runs may have started and finished, so the next
    // run we see could easily be a peer's. Demote rather than carry: the claim still counts as
    // outstanding (so nothing is silently forgotten) but it will no longer bind a run.
    for (const claim of this.claims) {
      if (claim.state === "armed") claim.state = "lost";
    }
  }

  /**
   * Expire claims and owned runs that have seen no stream activity for `idleMs`.
   *
   * Keyed on observed INACTIVITY, not elapsed time since submission. Turns in this system run
   * 51s-600s, so any wall-clock budget short enough to bound a stuck claim is short enough to
   * reap a live one. This follows the same forward-progress principle the App Server's own
   * watchdog uses. Returns what was reaped so the caller can surface it.
   */
  reapIdle(idleMs: number, now: number): { claims: number; runs: number } {
    if (now - this.lastActivity < idleMs) return { claims: 0, runs: 0 };
    const claims = this.claims.length;
    const runs = this.owned.size;
    this.claims.length = 0;
    this.owned.clear();
    if (claims || runs) this.degraded = false;
    return { claims, runs };
  }

  /** Record a consumed message id, evicting oldest-first so the set cannot grow without bound. */
  private consume(clientMessageId: string): void {
    this.consumedMessageIds.add(clientMessageId);
    while (this.consumedMessageIds.size > MAX_REMEMBERED_RUNS) {
      const oldest = this.consumedMessageIds.values().next().value;
      if (oldest === undefined) break;
      this.consumedMessageIds.delete(oldest);
    }
  }

  /** Mark stream activity; expiry is measured from here. */
  private touch(): void {
    this.lastActivity = this.clock();
  }

  snapshot(): OwnershipSnapshot {
    return {
      owned: [...this.owned.keys()],
      pending: this.claims.length,
      degraded: this.degraded,
    };
  }

  /**
   * Record a run id, evicting the oldest once the cap is reached.
   *
   * `seenRuns` previously grew for the life of the process. This client is meant to sit attached
   * to a constant-on runtime for days, and every turn from every surface adds an entry. The cap
   * is far beyond the reordering window attribution actually needs — it only has to cover runs
   * that might still be referenced by an in-flight frame.
   */
  private remember(runId: string): void {
    this.seenRuns.add(runId);
    while (this.seenRuns.size > MAX_REMEMBERED_RUNS) {
      const oldest = this.seenRuns.values().next().value;
      if (oldest === undefined) break;
      this.seenRuns.delete(oldest);
      this.foreignRuns.delete(oldest);
    }
  }

  private drop(claim: Claim): void {
    const index = this.claims.indexOf(claim);
    if (index !== -1) this.claims.splice(index, 1);
  }
}
