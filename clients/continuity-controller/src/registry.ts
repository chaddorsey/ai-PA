/**
 * registry.ts — the runtime registry: which `{agent_id, conversation_id}` scopes exist, which
 * are HOT (anchor+worker both subscribe), and which are broken (visible, never silently
 * skipped).
 *
 * C1 finding baked in as a RULE: controller-managed threads are always CREATED conversations
 * (`local-conv-N`), never the `default` alias — `conversation_messages_list` cannot resolve
 * the alias, so a `default` row would make C4's transcript reconciliation impossible for that
 * thread. `upsert` enforces it.
 *
 * Hot-set changes bump `meta.hotset_version`; the anchor (a separate, read-only process) polls
 * that single integer instead of diffing tables — near-zero logic by design.
 */

import type { DatabaseSync } from "node:sqlite";

export interface RegistryRow {
  agent_id: string;
  conversation_id: string;
  label: string;
  temp: "hot" | "cold";
  origin: Record<string, unknown>;
  broken: string | null;
  created_at: string;
  updated_at: string;
}

export interface RuntimeRef {
  agent_id: string;
  conversation_id: string;
}

const HOTSET_VERSION_KEY = "hotset_version";

export class RegistryError extends Error {
  override name = "RegistryError";
}

function toRow(raw: Record<string, unknown>): RegistryRow {
  return {
    agent_id: raw.agent_id as string,
    conversation_id: raw.conversation_id as string,
    label: raw.label as string,
    temp: raw.temp as "hot" | "cold",
    origin: JSON.parse(raw.origin as string) as Record<string, unknown>,
    broken: (raw.broken as string | null) ?? null,
    created_at: raw.created_at as string,
    updated_at: raw.updated_at as string,
  };
}

export class Registry {
  constructor(private readonly db: DatabaseSync) {}

  list(): RegistryRow[] {
    const rows = this.db
      .prepare("SELECT * FROM registry ORDER BY agent_id, conversation_id")
      .all() as Array<Record<string, unknown>>;
    return rows.map(toRow);
  }

  /** The subscription set: hot AND not broken. */
  hotRows(): RegistryRow[] {
    const rows = this.db
      .prepare(
        "SELECT * FROM registry WHERE temp = 'hot' AND broken IS NULL ORDER BY agent_id, conversation_id",
      )
      .all() as Array<Record<string, unknown>>;
    return rows.map(toRow);
  }

  get(ref: RuntimeRef): RegistryRow | null {
    const raw = this.db
      .prepare("SELECT * FROM registry WHERE agent_id = ? AND conversation_id = ?")
      .get(ref.agent_id, ref.conversation_id) as Record<string, unknown> | undefined;
    return raw ? toRow(raw) : null;
  }

  upsert(input: {
    agent_id: string;
    conversation_id: string;
    label?: string;
    temp?: "hot" | "cold";
    origin?: Record<string, unknown>;
  }): void {
    if (input.conversation_id === "default") {
      throw new RegistryError(
        "registry rows must reference CREATED conversations — the `default` alias is " +
          "unresolvable by conversation_messages_list (C1 S3), which would sever this thread " +
          "from transcript reconciliation",
      );
    }
    const now = new Date().toISOString();
    this.db
      .prepare(
        `INSERT INTO registry (agent_id, conversation_id, label, temp, origin, broken, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
         ON CONFLICT (agent_id, conversation_id) DO UPDATE SET
           label = excluded.label, temp = excluded.temp, origin = excluded.origin,
           broken = NULL, updated_at = excluded.updated_at`,
      )
      .run(
        input.agent_id,
        input.conversation_id,
        input.label ?? "",
        input.temp ?? "hot",
        JSON.stringify(input.origin ?? {}),
        now,
        now,
      );
    this.bumpHotsetVersion();
  }

  /** Mark a row broken with a visible reason. Removes it from the hot set → version bump. */
  markBroken(ref: RuntimeRef, reason: string): void {
    this.db
      .prepare(
        "UPDATE registry SET broken = ?, updated_at = ? WHERE agent_id = ? AND conversation_id = ?",
      )
      .run(reason, new Date().toISOString(), ref.agent_id, ref.conversation_id);
    this.bumpHotsetVersion();
  }

  setTemp(ref: RuntimeRef, temp: "hot" | "cold"): void {
    this.db
      .prepare(
        "UPDATE registry SET temp = ?, updated_at = ? WHERE agent_id = ? AND conversation_id = ?",
      )
      .run(temp, new Date().toISOString(), ref.agent_id, ref.conversation_id);
    this.bumpHotsetVersion();
  }

  hotsetVersion(): number {
    const raw = this.db.prepare("SELECT value FROM meta WHERE key = ?").get(HOTSET_VERSION_KEY) as
      | { value: string }
      | undefined;
    return raw ? Number.parseInt(raw.value, 10) : 0;
  }

  private bumpHotsetVersion(): void {
    this.db
      .prepare(
        `INSERT INTO meta (key, value) VALUES (?, '1')
         ON CONFLICT (key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)`,
      )
      .run(HOTSET_VERSION_KEY);
  }
}

/** The anchor's view: the same reads over a READ-ONLY handle, structurally unable to mutate. */
export class ReadOnlyRegistry {
  private readonly inner: Registry;
  constructor(db: DatabaseSync) {
    this.inner = new Registry(db);
  }
  hotRows(): RegistryRow[] {
    return this.inner.hotRows();
  }
  hotsetVersion(): number {
    return this.inner.hotsetVersion();
  }
}
