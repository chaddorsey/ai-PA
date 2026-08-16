/**
 * journal.ts (state layer) — the append-only controller journal.
 *
 * C3 ships the WRITER and the minimal event vocabulary the skeleton needs (boot, degrade,
 * broken registry rows, exposure windows, liveness faults). C4 builds the full turn-event
 * reducer on top of this table; nothing here anticipates that shape beyond "append-only rows,
 * never updated, never silently absent".
 */

import type { DatabaseSync } from "node:sqlite";

export interface JournalRow {
  id: number;
  at: string;
  kind: string;
  payload: Record<string, unknown>;
}

export class Journal {
  constructor(private readonly db: DatabaseSync) {}

  append(kind: string, payload: Record<string, unknown> = {}): number {
    const result = this.db
      .prepare("INSERT INTO journal (at, kind, payload) VALUES (?, ?, ?)")
      .run(new Date().toISOString(), kind, JSON.stringify(payload));
    return Number(result.lastInsertRowid);
  }

  tail(limit = 50): JournalRow[] {
    const rows = this.db
      .prepare("SELECT id, at, kind, payload FROM journal ORDER BY id DESC LIMIT ?")
      .all(limit) as Array<{ id: number; at: string; kind: string; payload: string }>;
    return rows.reverse().map((r) => ({
      id: r.id,
      at: r.at,
      kind: r.kind,
      payload: JSON.parse(r.payload) as Record<string, unknown>,
    }));
  }
}
