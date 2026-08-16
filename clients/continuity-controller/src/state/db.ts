/**
 * db.ts — the controller's host-local SQLite authority (registry · journal · meta).
 *
 * A DELIBERATE deviation from the repo's Postgres-`pa_web` daemon convention (plan, Key
 * Technical Decisions): the controller must be up and journaling when Docker/supabase is down,
 * it is a single-writer daemon, and this is device-local operational state.
 *
 * Hardening required by the plan:
 *  - WAL mode; state dir 0700, db files 0600;
 *  - a boot integrity check that DEGRADES VISIBLY rather than silently starting with an empty
 *    authority: a corrupt db is set aside (never deleted), a fresh one is created, and the
 *    degradation is returned to the caller — the worker journals it and carries it in the
 *    liveness file, so an operator sees "authority rebuilt" instead of a quietly amnesiac
 *    controller.
 */

import { chmodSync, existsSync, mkdirSync, renameSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import type { DatabaseSync as DatabaseSyncType } from "node:sqlite";

// Loaded via createRequire, NOT a static import: vite/vitest's builtin list predates
// `node:sqlite` and tries (and fails) to bundle it. A runtime require is invisible to the
// transform and identical at runtime.
const require = createRequire(import.meta.url);
const { DatabaseSync } = require("node:sqlite") as typeof import("node:sqlite");
type DatabaseSync = DatabaseSyncType;

export interface StateDb {
  db: DatabaseSync;
  path: string;
  /**
   * Null when the store opened healthy. Otherwise a human-readable account of what was wrong
   * and where the damaged file was preserved — the caller MUST surface it (journal + liveness),
   * not log-and-forget.
   */
  degraded: string | null;
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS registry (
  agent_id        TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  label           TEXT NOT NULL DEFAULT '',
  temp            TEXT NOT NULL DEFAULT 'hot' CHECK (temp IN ('hot','cold')),
  origin          TEXT NOT NULL DEFAULT '{}',
  broken          TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  PRIMARY KEY (agent_id, conversation_id)
);
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  at      TEXT NOT NULL,
  kind    TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS turn_queue (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id          TEXT NOT NULL,
  conversation_id   TEXT NOT NULL,
  client_message_id TEXT NOT NULL UNIQUE,
  content           TEXT NOT NULL,
  origin            TEXT NOT NULL DEFAULT '{}',
  state             TEXT NOT NULL CHECK (state IN ('queued','submitting','submitted','terminal')),
  outcome           TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turn_events (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id          TEXT NOT NULL,
  conversation_id   TEXT NOT NULL,
  client_message_id TEXT,
  event_seq         INTEGER,
  idempotency_key   TEXT,
  kind              TEXT NOT NULL,
  payload           TEXT NOT NULL DEFAULT '{}',
  at                TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS turn_events_idem
  ON turn_events (agent_id, conversation_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS routes (
  alias           TEXT PRIMARY KEY,
  agent_id        TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  author          TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bindings (
  source_agent_id        TEXT NOT NULL,
  source_conversation_id TEXT NOT NULL,
  target_agent_id        TEXT NOT NULL,
  target_conversation_id TEXT NOT NULL,
  author                 TEXT NOT NULL,
  created_at             TEXT NOT NULL,
  PRIMARY KEY (source_agent_id, source_conversation_id)
);
CREATE TABLE IF NOT EXISTS digests (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  kinara_agent_id        TEXT NOT NULL,
  kinara_conversation_id TEXT NOT NULL,
  item_id                TEXT NOT NULL UNIQUE,
  summary                TEXT NOT NULL,
  created_at             TEXT NOT NULL,
  delivered_at           TEXT
);
CREATE TABLE IF NOT EXISTS unseen (
  agent_id        TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  kind            TEXT NOT NULL,
  ref             TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  PRIMARY KEY (agent_id, conversation_id, kind, ref)
);
`;

export const DB_FILENAME = "controller.sqlite3";

function openRaw(path: string, readOnly: boolean): DatabaseSync {
  const db = new DatabaseSync(path, { readOnly });
  if (!readOnly) {
    db.exec("PRAGMA journal_mode=WAL");
    db.exec("PRAGMA foreign_keys=ON");
  }
  return db;
}

function integrityOk(db: DatabaseSync): boolean {
  const row = db.prepare("PRAGMA integrity_check").get() as Record<string, unknown> | undefined;
  return row !== undefined && Object.values(row)[0] === "ok";
}

function restrictPerms(stateDir: string, path: string): void {
  chmodSync(stateDir, 0o700);
  for (const suffix of ["", "-wal", "-shm"]) {
    const p = `${path}${suffix}`;
    if (existsSync(p)) chmodSync(p, 0o600);
  }
}

/** Open (or create) the controller state db read-write, with the integrity/degrade protocol. */
export function openStateDb(stateDir: string): StateDb {
  mkdirSync(stateDir, { recursive: true, mode: 0o700 });
  const path = join(stateDir, DB_FILENAME);

  let db: DatabaseSync | null = null;
  let degraded: string | null = null;

  if (existsSync(path)) {
    try {
      const candidate = openRaw(path, false);
      if (integrityOk(candidate)) {
        db = candidate;
      } else {
        candidate.close();
        degraded = "integrity_check failed";
      }
    } catch (e) {
      degraded = `open failed: ${e instanceof Error ? e.message : String(e)}`;
    }
    if (db === null) {
      // Set the damaged authority ASIDE — never delete it; the journal inside may be the only
      // record of turns nobody saw, and C4's transcript reconciliation can mine it later.
      const aside = `${path}.corrupt-${new Date().toISOString().replace(/[:.]/g, "-")}`;
      renameSync(path, aside);
      degraded = `${degraded}; damaged db preserved at ${aside}; starting with a REBUILT (empty) authority`;
    }
  }

  if (db === null) db = openRaw(path, false);
  db.exec(SCHEMA);
  restrictPerms(stateDir, path);
  return { db, path, degraded };
}

/** Open the existing state db READ-ONLY (the anchor's registry view). Throws if absent. */
export function openStateDbReadOnly(stateDir: string): DatabaseSync {
  const path = join(stateDir, DB_FILENAME);
  if (!existsSync(path)) {
    throw new Error(
      `controller state db not found at ${path} — the worker creates it; start the worker first`,
    );
  }
  return openRaw(path, true);
}
