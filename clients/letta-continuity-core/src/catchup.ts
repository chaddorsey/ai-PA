/**
 * catchup.ts — reconnect snapshot + message-id watermark dedup.
 *
 * A watchdog stall-restart (Unit 3) drops ALL connections at once, so catch-up is the
 * PRIMARY recovery path, not a rare edge. On reconnect: reconnecting → runtime_start →
 * `conversation_messages_list` snapshot → resume live.
 *
 * Dedup MUST key on a CONVERSATION-STABLE coordinate — the message ids present in the
 * snapshot — NOT `event_seq`. `event_seq` is per-connection and resets on reconnect, so it
 * cannot bridge the replay↔live seam. A live `stream_delta` whose `delta.id` is already in
 * the snapshot is a replay of an already-rendered message → drop (no duplicate). A delta with
 * a message id NOT in the snapshot is genuinely new → render (no loss). This is exact whether
 * the message completed before the snapshot (in it → dropped) or was still in-flight at the
 * disconnect (absent → rendered).
 */

import type { MessagesListResponseFrame } from "./protocol.js";

/** Extract the stable id from a snapshot message entry. */
function messageId(entry: { id?: unknown; [k: string]: unknown }): string | undefined {
  return typeof entry.id === "string" ? entry.id : undefined;
}

export interface CatchupSnapshot {
  /**
   * Set of message ids already known — the dedup watermark for the live resume.
   *
   * This used to sit alongside a `messages` array documented as being "to (re)paint the
   * transcript". No client ever repainted, and nothing read the field, so every reconnect
   * shallow-copied the whole conversation history and threw it away. Repainting is real work for
   * M1 Unit 7 (which owns the catch-up proof); it should arrive with a consumer, not before one.
   */
  seenMessageIds: Set<string>;
}

/** Turn a `conversation_messages_list_response` into a dedup watermark. */
export function snapshotFromResponse(resp: MessagesListResponseFrame): CatchupSnapshot {
  const seen = new Set<string>();
  for (const m of resp.messages) {
    const id = messageId(m);
    if (id !== undefined) seen.add(id);
  }
  return { seenMessageIds: seen };
}

/**
 * Live-frame gate for the replay↔live seam. Feed the `delta.id` of each incoming live
 * `stream_delta` after a reconnect. Returns true if it should be RENDERED (a message NOT in
 * the snapshot), false if it's a replay of a message already in the snapshot (drop).
 *
 * The watermark is the IMMUTABLE snapshot id set: newly-seen live ids are never added to the
 * drop-set, so this gate only ever rejects snapshot replays. Intra-connection duplicates are
 * already dropped by the StreamAssembler's monotonic `event_seq` watermark.
 *
 * ⚠️ UNVERIFIED PREMISE (Unit 5 live capture, 2026-08-13). This was written believing that all
 * deltas of one message share a single `delta.id`. They do NOT — every chunk carries its own
 * (`letta-msg-26735`, `-26736`, …); `otid` is what stays constant per message. So whether a
 * replayed chunk's id is ever present in a snapshot of *messages* is an open question: if the
 * snapshot returns different ids, this gate silently matches nothing. Unit 7 must settle it
 * before the "no duplicated messages" criterion can be trusted — see
 * docs/followups/2026-08-13-continuity-core-approval-correlation.md finding #2.
 */
export class LiveDedup {
  private readonly snapshotIds: ReadonlySet<string>;

  constructor(snapshot: CatchupSnapshot) {
    this.snapshotIds = snapshot.seenMessageIds;
  }

  /** True → render this delta (message not in snapshot); false → drop (snapshot replay). */
  admit(deltaId: string): boolean {
    return !this.snapshotIds.has(deltaId);
  }
}
