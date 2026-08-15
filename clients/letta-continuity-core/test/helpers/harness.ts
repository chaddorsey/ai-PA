/**
 * Shared scaffolding for the socket-level tests: a temp pointer file, a poll-until predicate,
 * and a plain sleep. Nothing here decides behaviour — it only removes the copy of these three
 * helpers that every socket test would otherwise carry.
 */

import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { writePointer } from "../../src/pointer.js";

export const AGENT = "agent-local-3898b33a";
export const CONV = "local-conv-continuity-uuid";

export async function pointerFile(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "continuity-core-"));
  const path = join(dir, "pointer.json");
  await writePointer(path, { agentId: AGENT, conversationId: CONV, label: "MC" });
  return path;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function waitFor(pred: () => boolean, timeoutMs = 3000): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = (): void => {
      if (pred()) {
        resolve();
        return;
      }
      if (Date.now() - start > timeoutMs) {
        reject(new Error("waitFor timed out"));
        return;
      }
      setTimeout(tick, 10);
    };
    tick();
  });
}
