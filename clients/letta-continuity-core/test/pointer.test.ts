import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { PointerError, readPointer, writePointer } from "../src/pointer.js";

const dirs: string[] = [];
async function tmpFile(name: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "continuity-ptr-"));
  dirs.push(dir);
  return join(dir, name);
}

afterAll(() => {
  // temp dirs are OS-reaped; nothing to force-clean deterministically.
});

describe("pointer read/write", () => {
  it("round-trips a written pointer", async () => {
    const path = await tmpFile("pointer.json");
    await writePointer(path, {
      agentId: "agent-local-abc",
      conversationId: "local-conv-uuid",
      label: "MC",
    });
    const p = await readPointer(path);
    expect(p).toEqual({
      agentId: "agent-local-abc",
      conversationId: "local-conv-uuid",
      label: "MC",
    });
  });

  it("throws an actionable error when the file is missing", async () => {
    const path = await tmpFile("nope.json");
    await expect(readPointer(path)).rejects.toBeInstanceOf(PointerError);
  });

  it("rejects malformed JSON", async () => {
    const path = await tmpFile("bad.json");
    await writeFile(path, "{ not json", "utf-8");
    await expect(readPointer(path)).rejects.toThrow(/not valid JSON/);
  });

  it("rejects a missing agent_id", async () => {
    const path = await tmpFile("noagent.json");
    await writeFile(path, JSON.stringify({ conversation_id: "c" }), "utf-8");
    await expect(readPointer(path)).rejects.toThrow(/agent_id/);
  });

  it('rejects the "default" conversation (legacy wrapper cross-talk)', async () => {
    const path = await tmpFile("default.json");
    await writeFile(path, JSON.stringify({ agent_id: "a", conversation_id: "default" }), "utf-8");
    await expect(readPointer(path)).rejects.toThrow(/default/);
  });
});
