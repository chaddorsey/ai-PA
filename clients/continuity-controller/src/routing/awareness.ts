/**
 * routing/awareness.ts — how the operator learns a turn happened (R13–R15).
 *
 * Levels: `interrupt` (raise on the focused surface — focus NEVER moves, R14: there is no
 * mechanism here that could move it), `badge` (the urgency-inferred default), `muted`
 * (deliberately silent — C8's digests use it). Delivery: attached notify-capable surfaces get
 * an awareness frame; with NOBODY attached the marker persists in `unseen` and is presented on
 * the next attach (THE 10:55 fix), where consumption clears it. Agents adjust the level via
 * the `notify_operator` external tool (worker-registered, re-registered on every reconnect;
 * uncapped by documented-risk decision 2026-08-15).
 */

import type { DatabaseSync } from "node:sqlite";
import type { TurnJournal } from "../journal.js";
import type { RuntimeRef } from "../registry.js";

export type AwarenessLevel = "interrupt" | "badge" | "muted";

export interface UnseenRow {
  kind: string;
  ref: string;
  created_at: string;
}

export interface AwarenessOptions {
  db: DatabaseSync;
  journal: TurnJournal;
  /** Deliver an awareness frame to notify-capable surfaces of the runtime. Returns reached. */
  broadcast: (runtime: RuntimeRef, level: AwarenessLevel, ref: string) => number;
  onWarn?: (msg: string) => void;
}

const LEVELS: ReadonlySet<string> = new Set(["interrupt", "badge", "muted"]);

export class AwarenessManager {
  /** Per-runtime level override set by notify_operator, applied to that runtime's next signal. */
  private readonly overrides = new Map<string, AwarenessLevel>();

  constructor(private readonly opts: AwarenessOptions) {}

  /** The notify_operator tool's entry point. Returns false on a level the taxonomy rejects. */
  setDirective(runtime: RuntimeRef, level: string): boolean {
    if (!LEVELS.has(level)) return false;
    this.overrides.set(`${runtime.agent_id}:${runtime.conversation_id}`, level as AwarenessLevel);
    this.opts.journal.record({
      runtime,
      kind: "awareness_directive",
      payload: { level, via: "notify_operator" },
    });
    return true;
  }

  /**
   * Signal one item (a delivered turn). `defaultLevel` is the sender's urgency-inferred
   * default; a standing notify_operator override wins. Muted signals notify nobody — that is
   * their meaning — but they are journaled, never silently absent.
   */
  signal(runtime: RuntimeRef, ref: string, defaultLevel: AwarenessLevel = "badge"): void {
    const key = `${runtime.agent_id}:${runtime.conversation_id}`;
    const level = this.overrides.get(key) ?? defaultLevel;
    this.overrides.delete(key);
    this.opts.journal.record({
      runtime,
      clientMessageId: ref,
      kind: "awareness_signal",
      payload: { level },
    });
    if (level === "muted") return;
    const reached = this.opts.broadcast(runtime, level, ref);
    if (reached === 0) {
      // THE 10:55 marker: nobody saw it arrive, so its arrival is durable state, not a memory.
      this.opts.db
        .prepare(
          `INSERT OR IGNORE INTO unseen (agent_id, conversation_id, kind, ref, created_at)
           VALUES (?, ?, 'turn', ?, ?)`,
        )
        .run(runtime.agent_id, runtime.conversation_id, ref, new Date().toISOString());
      this.opts.journal.record({
        runtime,
        clientMessageId: ref,
        kind: "unseen_marked",
        payload: { level },
      });
    }
  }

  /** What arrived while away, for the attach handshake. */
  unseenFor(runtime: RuntimeRef): UnseenRow[] {
    return this.opts.db
      .prepare(
        "SELECT kind, ref, created_at FROM unseen WHERE agent_id = ? AND conversation_id = ? ORDER BY created_at",
      )
      .all(runtime.agent_id, runtime.conversation_id) as unknown as UnseenRow[];
  }

  /**
   * Surface-consumption acknowledgment: an attach that received the replay HAS seen what it
   * contained. Approval markers are NOT cleared here — answering the approval clears those.
   */
  markSeen(runtime: RuntimeRef): void {
    this.opts.db
      .prepare(
        "DELETE FROM unseen WHERE agent_id = ? AND conversation_id = ? AND kind != 'approval'",
      )
      .run(runtime.agent_id, runtime.conversation_id);
  }
}
