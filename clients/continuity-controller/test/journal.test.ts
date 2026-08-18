/**
 * TurnJournal: exactly-once is structural (INSERT OR IGNORE against the idempotency index),
 * ordering is insertion order, and the duplicate audit can never find anything.
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { TurnJournal } from "../src/journal.js";
import { openStateDb } from "../src/state/db.js";

const RUNTIME = { agent_id: "ag-1", conversation_id: "local-conv-1" };

function fresh(): TurnJournal {
  const { db } = openStateDb(mkdtempSync(join(tmpdir(), "continuity-journal-")));
  return new TurnJournal(db);
}

describe("TurnJournal", () => {
  it("a replayed frame with the same idempotency_key journals exactly once", () => {
    const journal = fresh();
    const input = {
      runtime: RUNTIME,
      eventSeq: 7,
      idempotencyKey: "stream_delta:7",
      kind: "assistant_message",
      payload: { text: "hello" },
    };
    expect(journal.record(input)).toBe(true);
    expect(journal.record(input)).toBe(false); // the replay — ignored structurally
    expect(journal.eventsFor(RUNTIME)).toHaveLength(1);
    expect(journal.duplicateCount()).toBe(0);
  });

  it("key-less events (controller-minted) always append", () => {
    const journal = fresh();
    expect(journal.record({ runtime: RUNTIME, kind: "turn_accepted" })).toBe(true);
    expect(journal.record({ runtime: RUNTIME, kind: "turn_accepted" })).toBe(true);
    expect(journal.eventsFor(RUNTIME)).toHaveLength(2);
  });

  it("the same idempotency_key on DIFFERENT runtimes is not a duplicate", () => {
    const journal = fresh();
    const other = { agent_id: "ag-2", conversation_id: "local-conv-2" };
    expect(journal.record({ runtime: RUNTIME, idempotencyKey: "k1", kind: "x" })).toBe(true);
    expect(journal.record({ runtime: other, idempotencyKey: "k1", kind: "x" })).toBe(true);
  });

  it("eventsFor returns insertion order", () => {
    const journal = fresh();
    for (const kind of ["a", "b", "c"]) journal.record({ runtime: RUNTIME, kind });
    expect(journal.eventsFor(RUNTIME).map((r) => r.kind)).toEqual(["a", "b", "c"]);
  });

  it("tailRows returns the NEWEST window ascending — a fresh attach must not replay the morning", () => {
    // Regression (2026-08-17, phone web slice): a null-cursor attach replayed from id 0
    // with an ASC LIMIT, freezing fresh surfaces on a busy thread's oldest rows.
    const journal = fresh();
    for (let i = 0; i < 700; i++) journal.record({ runtime: RUNTIME, kind: `k${i}` });
    const tail = journal.tailRows(RUNTIME, 500);
    expect(tail).toHaveLength(500);
    expect(tail[0]?.kind).toBe("k200"); // newest 500 of 700
    expect(tail.at(-1)?.kind).toBe("k699"); // …ending at the true tail
    const ids = tail.map((r) => r.id);
    expect([...ids].sort((a, b) => a - b)).toEqual(ids); // ascending for the renderer
  });

  it("rowsBefore returns the newest page strictly before the boundary, ascending", () => {
    const journal = fresh();
    for (let i = 0; i < 50; i++) journal.record({ runtime: RUNTIME, kind: `k${i}` });
    const all = journal.eventsFor(RUNTIME, 50);
    const boundary = all[40]?.id ?? 0; // oldest rendered row on the surface
    const page = journal.rowsBefore(RUNTIME, boundary, 10);
    expect(page).toHaveLength(10);
    expect(page.at(-1)?.id).toBeLessThan(boundary); // strictly before — no overlap
    expect(page.map((r) => r.kind)).toEqual(
      Array.from({ length: 10 }, (_, i) => `k${30 + i}`), // the 10 newest below it
    );
  });

  it("rowsSince pages forward chunk by chunk to the true tail (no silent 1000-row gap)", () => {
    const journal = fresh();
    for (let i = 0; i < 1200; i++) journal.record({ runtime: RUNTIME, kind: `k${i}` });
    const all: string[] = [];
    let cursor: number | null = 0;
    for (;;) {
      const chunk = journal.rowsSince(RUNTIME, cursor);
      all.push(...chunk.map((r) => r.kind));
      if (chunk.length < 1000) break;
      cursor = chunk.at(-1)?.id ?? cursor;
    }
    expect(all).toHaveLength(1200);
    expect(all.at(-1)).toBe("k1199");
  });
});
