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
});
