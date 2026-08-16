/**
 * Registry + state-db properties: persistence, hot-set versioning, broken-row visibility, the
 * created-conversations-only rule (C1 S3), and the integrity-degrade protocol — the controller
 * must never boot with a silently empty authority.
 */

import {
  chmodSync,
  existsSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Registry, RegistryError } from "../src/registry.js";
import { DB_FILENAME, openStateDb, openStateDbReadOnly } from "../src/state/db.js";
import { Journal } from "../src/state/journal.js";

function freshDir(): string {
  return mkdtempSync(join(tmpdir(), "continuity-ctrl-"));
}

describe("registry", () => {
  it("upsert → list/hotRows round-trips and bumps hotset_version", () => {
    const { db } = openStateDb(freshDir());
    const registry = new Registry(db);
    expect(registry.hotsetVersion()).toBe(0);

    registry.upsert({
      agent_id: "ag-1",
      conversation_id: "local-conv-1",
      label: "kinara",
      temp: "hot",
    });
    registry.upsert({
      agent_id: "ag-2",
      conversation_id: "local-conv-2",
      label: "docs",
      temp: "cold",
    });

    expect(registry.list()).toHaveLength(2);
    expect(registry.hotRows().map((r) => r.conversation_id)).toEqual(["local-conv-1"]);
    expect(registry.hotsetVersion()).toBe(2);
  });

  it("REFUSES a `default` conversation row — the alias severs transcript reconciliation", () => {
    const { db } = openStateDb(freshDir());
    const registry = new Registry(db);
    expect(() => registry.upsert({ agent_id: "ag-1", conversation_id: "default" })).toThrowError(
      RegistryError,
    );
    expect(registry.list()).toHaveLength(0);
  });

  it("markBroken removes the row from the hot set VISIBLY (reason kept) and bumps the version", () => {
    const { db } = openStateDb(freshDir());
    const registry = new Registry(db);
    registry.upsert({ agent_id: "ag-1", conversation_id: "local-conv-1" });
    const v = registry.hotsetVersion();

    registry.markBroken(
      { agent_id: "ag-1", conversation_id: "local-conv-1" },
      "Conversation not found",
    );

    expect(registry.hotRows()).toHaveLength(0);
    expect(registry.get({ agent_id: "ag-1", conversation_id: "local-conv-1" })?.broken).toBe(
      "Conversation not found",
    );
    expect(registry.hotsetVersion()).toBe(v + 1);
    // Re-upserting HEALS the row: a re-created conversation re-enters the hot set.
    registry.upsert({ agent_id: "ag-1", conversation_id: "local-conv-1" });
    expect(registry.hotRows()).toHaveLength(1);
  });

  it("state persists across a re-open (the worker's kill -9 recovery path)", () => {
    const dir = freshDir();
    {
      const { db } = openStateDb(dir);
      new Registry(db).upsert({ agent_id: "ag-1", conversation_id: "local-conv-1", label: "x" });
      new Journal(db).append("worker_boot", {});
      db.close();
    }
    const { db, degraded } = openStateDb(dir);
    expect(degraded).toBeNull();
    expect(new Registry(db).list()).toHaveLength(1);
    expect(new Journal(db).tail().map((r) => r.kind)).toContain("worker_boot");
  });

  it("read-only handle serves the anchor and throws when the worker has never booted", () => {
    const dir = freshDir();
    expect(() => openStateDbReadOnly(dir)).toThrowError(/worker creates it/);
    const { db } = openStateDb(dir);
    new Registry(db).upsert({ agent_id: "ag-1", conversation_id: "local-conv-1" });
    const ro = openStateDbReadOnly(dir);
    expect(new Registry(ro).hotRows()).toHaveLength(1);
  });

  it("state dir is 0700 and the db file 0600", () => {
    const dir = freshDir();
    openStateDb(dir);
    expect(statSync(dir).mode & 0o777).toBe(0o700);
    expect(statSync(join(dir, DB_FILENAME)).mode & 0o777).toBe(0o600);
  });

  it("a corrupt db DEGRADES VISIBLY: preserved aside, fresh authority, non-null degraded", () => {
    const dir = freshDir();
    {
      const { db } = openStateDb(dir);
      new Registry(db).upsert({ agent_id: "ag-1", conversation_id: "local-conv-1" });
      db.close();
    }
    // Corrupt the file header in place — the classic torn-write shape.
    const path = join(dir, DB_FILENAME);
    chmodSync(path, 0o600);
    writeFileSync(path, Buffer.from("not a sqlite file at all — torn beyond recognition"));

    const { db, degraded } = openStateDb(dir);
    expect(degraded).not.toBeNull();
    expect(degraded).toMatch(/REBUILT/);
    // The damaged authority was SET ASIDE, never deleted.
    const aside = readdirSync(dir).filter((f) => f.includes(".corrupt-"));
    expect(aside).toHaveLength(1);
    expect(readFileSync(join(dir, aside[0] as string), "utf8")).toMatch(/torn beyond recognition/);
    // The rebuilt authority works and is empty — visibly so, not silently so.
    expect(new Registry(db).list()).toHaveLength(0);
    expect(existsSync(path)).toBe(true);
  });
});
