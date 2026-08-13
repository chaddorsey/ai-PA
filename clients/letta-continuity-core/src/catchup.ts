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

import {
  type MessagesListResponseFrame,
  type Runtime,
  type ServerFrame,
  buildConversationMessagesList,
} from "./protocol.js";

/** Extract the stable id from a snapshot message entry. */
function messageId(entry: { id?: unknown; [k: string]: unknown }): string | undefined {
  return typeof entry.id === "string" ? entry.id : undefined;
}

export interface CatchupSnapshot {
  /** Ordered historical messages from the snapshot, to (re)paint the transcript. */
  messages: Array<{ id?: string; [k: string]: unknown }>;
  /** Set of message ids already known — the dedup watermark for the live resume. */
  seenMessageIds: Set<string>;
}

/**
 * Build the `conversation_messages_list` request frame + its RPC request id lives with the
 * caller (ws.request assigns it). This helper just shapes the frame via protocol.ts.
 */
export function messagesListRequest(requestId: string, runtime: Runtime): ServerFrame {
  return buildConversationMessagesList(requestId, runtime);
}

/** Turn a `conversation_messages_list_response` into a dedup watermark. */
export function snapshotFromResponse(resp: MessagesListResponseFrame): CatchupSnapshot {
  const seen = new Set<string>();
  const messages: Array<{ id?: string; [k: string]: unknown }> = [];
  for (const m of resp.messages) {
    const id = messageId(m);
    const entry: { id?: string; [k: string]: unknown } = { ...m };
    if (id !== undefined) {
      entry.id = id;
      seen.add(id);
    }
    messages.push(entry);
  }
  return { messages, seenMessageIds: seen };
}

/**
 * Live-frame gate for the replay↔live seam. Feed the `delta.id` of each incoming live
 * `stream_delta` after a reconnect. Returns true if it should be RENDERED (a message NOT in
 * the snapshot), false if it's a replay of a message already in the snapshot (drop).
 *
 * The watermark is the IMMUTABLE snapshot id set. A single new message streams many deltas
 * that all share one `delta.id` (only `seq_id`/`event_seq` advance), so we must NOT add
 * newly-seen live ids to the drop-set — that would drop every delta after the first of a
 * genuinely new message. Intra-connection duplicate frames are already dropped by the
 * StreamAssembler's monotonic `event_seq` watermark, so this gate only rejects snapshot replays.
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

  get watermarkSize(): number {
    return this.snapshotIds.size;
  }
}
