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

export type JournalListener = (row: TurnEventRow) => void;

export class TurnJournal {
  private readonly listeners = new Set<JournalListener>();

  constructor(private readonly db: DatabaseSync) {}

  /** Live tap for the surface layer: fires ONLY for rows that actually inserted (post-dedup). */
  onRecord(listener: JournalListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Append one event. Returns false when the idempotency key made it a duplicate (ignored). */
  record(input: RecordEventInput): boolean {
    const at = new Date().toISOString();
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
        at,
      );
    if (result.changes > 0) {
      const row: TurnEventRow = {
        id: Number(result.lastInsertRowid),
        agent_id: input.runtime.agent_id,
        conversation_id: input.runtime.conversation_id,
        client_message_id: input.clientMessageId ?? null,
        event_seq: input.eventSeq ?? null,
        idempotency_key: input.idempotencyKey ?? null,
        kind: input.kind,
        payload: input.payload ?? {},
        at,
      };
      for (const listener of this.listeners) {
        try {
          listener(row);
        } catch {
          // A surface listener must never poison the journal write path.
        }
      }
    }
    return result.changes > 0;
  }

  /** Replay: rows for a runtime with id > cursor, oldest first. Gapless by construction. */
  rowsSince(runtime: RuntimeRef, cursor: number | null, limit = 1000): TurnEventRow[] {
    const rows = this.db
      .prepare(
        `SELECT * FROM turn_events WHERE agent_id = ? AND conversation_id = ? AND id > ?
         ORDER BY id ASC LIMIT ?`,
      )
      .all(runtime.agent_id, runtime.conversation_id, cursor ?? 0, limit) as Array<
      Record<string, unknown>
    >;
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

  /**
   * The NEWEST `limit` rows for a runtime, ascending. A cursor-less attach replays this
   * tail window — replaying from id 0 with an ASC LIMIT served a busy thread its OLDEST
   * rows and froze fresh surfaces in the morning (found live 2026-08-17, phone web slice).
   */
  tailRows(runtime: RuntimeRef, limit = 500): TurnEventRow[] {
    const rows = this.db
      .prepare(
        `SELECT * FROM (
           SELECT * FROM turn_events WHERE agent_id = ? AND conversation_id = ?
           ORDER BY id DESC LIMIT ?
         ) ORDER BY id ASC`,
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
