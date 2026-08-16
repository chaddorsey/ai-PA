/**
 * journal.ts — the C4 turn journal: an append-only, exactly-once record of what each runtime's
 * turns actually did, reduced from the live frame stream plus transcript reconciliation.
 *
 * Exactly-once is STRUCTURAL, not best-effort: `idempotency_key` (documented per-broadcast
 * dedup key) is a partial UNIQUE index, and `record` uses INSERT OR IGNORE — a replayed frame
 * after a reconnect cannot produce a second row no matter what the caller does. Ordering is
 * `event_seq` within a connection generation (the key is per-connection, so generations are
 * first-class in the row, never inferred).
 */

import type { DatabaseSync } from "node:sqlite";
import type { RuntimeRef } from "./registry.js";

export interface TurnEventRow {
  id: number;
  agent_id: string;
  conversation_id: string;
  client_message_id: string | null;
  event_seq: number | null;
  idempotency_key: string | null;
  kind: string;
  payload: Record<string, unknown>;
  at: string;
}

export interface RecordEventInput {
  runtime: RuntimeRef;
  clientMessageId?: string | null;
  eventSeq?: number | null;
  idempotencyKey?: string | null;
  kind: string;
  payload?: Record<string, unknown>;
}

export class TurnJournal {
  constructor(private readonly db: DatabaseSync) {}

  /** Append one event. Returns false when the idempotency key made it a duplicate (ignored). */
  record(input: RecordEventInput): boolean {
    const result = this.db
      .prepare(
        `INSERT OR IGNORE INTO turn_events
           (agent_id, conversation_id, client_message_id, event_seq, idempotency_key, kind, payload, at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(
        input.runtime.agent_id,
        input.runtime.conversation_id,
        input.clientMessageId ?? null,
        input.eventSeq ?? null,
        input.idempotencyKey ?? null,
        input.kind,
        JSON.stringify(input.payload ?? {}),
        new Date().toISOString(),
      );
    return result.changes > 0;
  }

  eventsFor(runtime: RuntimeRef, limit = 500): TurnEventRow[] {
    const rows = this.db
      .prepare(
        `SELECT * FROM turn_events WHERE agent_id = ? AND conversation_id = ?
         ORDER BY id ASC LIMIT ?`,
      )
      .all(runtime.agent_id, runtime.conversation_id, limit) as Array<Record<string, unknown>>;
    return rows.map((r) => ({
      id: r.id as number,
      agent_id: r.agent_id as string,
      conversation_id: r.conversation_id as string,
      client_message_id: (r.client_message_id as string | null) ?? null,
      event_seq: (r.event_seq as number | null) ?? null,
      idempotency_key: (r.idempotency_key as string | null) ?? null,
      kind: r.kind as string,
      payload: JSON.parse(r.payload as string) as Record<string, unknown>,
      at: r.at as string,
    }));
  }

  /** Exactly-once audit: rows sharing an idempotency key within a runtime. Must always be 0. */
  duplicateCount(): number {
    const row = this.db
      .prepare(
        `SELECT COUNT(*) AS n FROM (
           SELECT agent_id, conversation_id, idempotency_key
           FROM turn_events WHERE idempotency_key IS NOT NULL
           GROUP BY agent_id, conversation_id, idempotency_key HAVING COUNT(*) > 1
         )`,
      )
      .get() as { n: number };
    return row.n;
  }
}
