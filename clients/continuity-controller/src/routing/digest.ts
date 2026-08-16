/**
 * routing/digest.ts — Kinara's ASYNC catch-up on direct-lane exchanges (R24, decided
 * 2026-08-15): recaps are REAL TURNS (there is no protocol operation that injects context
 * without producing one), **batched per Kinara conversation**, mapped to the thread whose
 * route or binding produced the exchange (never fanned out), submitted only when **no
 * operator message is pending for that runtime** (operator messages always preempt digests),
 * carrying a MUTED awareness posture (no signal at all — neither the digest nor Kinara's
 * acknowledgment badges the operator), and deduped against R12's direct inline cards by
 * shared item ids (each digest line carries the exchange's client_message_id).
 */

import type { DatabaseSync } from "node:sqlite";
import type { TurnJournal } from "../journal.js";
import type { RuntimeRef } from "../registry.js";
import type { TurnPipeline } from "../turns.js";

export interface DigestOptions {
  db: DatabaseSync;
  journal: TurnJournal;
  pipeline: TurnPipeline;
  onWarn?: (msg: string) => void;
}

export class DigestManager {
  constructor(private readonly opts: DigestOptions) {}

  /** Record one completed direct exchange for later recap in its route-origin Kinara thread. */
  enqueue(kinara: RuntimeRef, itemId: string, summary: string): void {
    this.opts.db
      .prepare(
        `INSERT OR IGNORE INTO digests
           (kinara_agent_id, kinara_conversation_id, item_id, summary, created_at)
         VALUES (?, ?, ?, ?, ?)`,
      )
      .run(kinara.agent_id, kinara.conversation_id, itemId, summary, new Date().toISOString());
    this.opts.journal.record({
      runtime: kinara,
      clientMessageId: itemId,
      kind: "digest_enqueued",
      payload: {},
    });
  }

  /**
   * One delivery sweep. For each Kinara thread with undelivered rows AND no pending operator
   * message in the queue (operator preemption), submit ONE batched muted recap turn. A failed
   * submission leaves the rows undelivered — retried next sweep, never silently dropped.
   */
  sweep(): void {
    const threads = this.opts.db
      .prepare(
        `SELECT DISTINCT kinara_agent_id, kinara_conversation_id FROM digests
         WHERE delivered_at IS NULL`,
      )
      .all() as Array<{ kinara_agent_id: string; kinara_conversation_id: string }>;
    for (const thread of threads) {
      const runtime = {
        agent_id: thread.kinara_agent_id,
        conversation_id: thread.kinara_conversation_id,
      };
      // OPERATOR MESSAGES ALWAYS PREEMPT: anything of the operator's still moving through the
      // queue for this runtime defers the digest to a later sweep.
      const pending = this.opts.pipeline
        .rows(["queued", "submitting", "submitted"])
        .filter(
          (r) =>
            r.agent_id === runtime.agent_id &&
            r.conversation_id === runtime.conversation_id &&
            (r.origin as { via?: string }).via !== "digest",
        );
      if (pending.length > 0) continue;

      const rows = this.opts.db
        .prepare(
          `SELECT id, item_id, summary FROM digests
           WHERE kinara_agent_id = ? AND kinara_conversation_id = ? AND delivered_at IS NULL
           ORDER BY id ASC`,
        )
        .all(runtime.agent_id, runtime.conversation_id) as Array<{
        id: number;
        item_id: string;
        summary: string;
      }>;
      if (rows.length === 0) continue;

      const text = [
        "Direct-lane digest (async catch-up; the operator has already seen these inline —",
        "do not repeat them back, just absorb the context):",
        ...rows.map((r) => `- [item ${r.item_id}] ${r.summary}`),
      ].join("\n");
      try {
        const clientMessageId = this.opts.pipeline.accept(runtime, text, {
          via: "digest",
          items: rows.map((r) => r.item_id),
          awareness: "muted",
        });
        const now = new Date().toISOString();
        const mark = this.opts.db.prepare("UPDATE digests SET delivered_at = ? WHERE id = ?");
        for (const r of rows) mark.run(now, r.id);
        this.opts.journal.record({
          runtime,
          clientMessageId,
          kind: "digest_delivered",
          payload: { items: rows.map((r) => r.item_id) },
        });
      } catch (e) {
        // Rows stay undelivered → retried next sweep. Journaled so the retry loop is visible.
        this.opts.journal.record({
          runtime,
          kind: "digest_deferred",
          payload: { reason: e instanceof Error ? e.message : String(e) },
        });
        this.opts.onWarn?.(
          `digest submission deferred: ${e instanceof Error ? e.message : String(e)}`,
        );
      }
    }
  }

  undeliveredCount(): number {
    const row = this.opts.db
      .prepare("SELECT COUNT(*) AS n FROM digests WHERE delivered_at IS NULL")
      .get() as { n: number };
    return row.n;
  }
}
