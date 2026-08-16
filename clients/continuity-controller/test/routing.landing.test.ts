/**
 * Landing precedence (R13, first + last clauses): explicit tag → labeled row (a MISS is a
 * miss, never a silent fallback); else the default-stamped thread; else first healthy row.
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Registry } from "../src/registry.js";
import { resolveLanding } from "../src/routing/landing.js";
import { openStateDb } from "../src/state/db.js";

function registryWith(): Registry {
  const { db } = openStateDb(mkdtempSync(join(tmpdir(), "continuity-landing-")));
  const registry = new Registry(db);
  registry.upsert({
    agent_id: "ag-1",
    conversation_id: "local-conv-1",
    label: "ops",
    temp: "cold",
  });
  registry.upsert({
    agent_id: "ag-1",
    conversation_id: "local-conv-2",
    label: "main",
    origin: { default: true },
  });
  registry.upsert({ agent_id: "ag-1", conversation_id: "local-conv-3", label: "scratch" });
  registry.upsert({ agent_id: "ag-2", conversation_id: "local-conv-9", label: "other" });
  return registry;
}

describe("resolveLanding", () => {
  it("an explicit tag lands in exactly the labeled thread", () => {
    expect(resolveLanding(registryWith(), "ag-1", "ops")?.conversation_id).toBe("local-conv-1");
  });

  it("a tag that matches nothing is a MISS — never a silent fallback to somewhere unnamed", () => {
    expect(resolveLanding(registryWith(), "ag-1", "no-such-label")).toBeNull();
  });

  it("untagged lands in the default-stamped thread", () => {
    expect(resolveLanding(registryWith(), "ag-1", undefined)?.conversation_id).toBe("local-conv-2");
  });

  it("with no default stamped, the first HOT healthy row wins", () => {
    const registry = registryWith();
    registry.upsert({ agent_id: "ag-1", conversation_id: "local-conv-2", label: "main" }); // unstamp
    const landed = resolveLanding(registry, "ag-1", undefined);
    expect(landed?.temp).toBe("hot");
  });

  it("a broken row never lands anything; an unknown agent lands nowhere", () => {
    const registry = registryWith();
    registry.markBroken({ agent_id: "ag-1", conversation_id: "local-conv-1" }, "gone");
    expect(resolveLanding(registry, "ag-1", "ops")).toBeNull();
    expect(resolveLanding(registry, "ag-zzz", undefined)).toBeNull();
  });
});
