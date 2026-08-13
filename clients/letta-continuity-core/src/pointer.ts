/**
 * pointer.ts — read (and write) the durable `{agent, conversation}` state file.
 *
 * M1 targets ONE fixed conversation. The UUID is created once (Unit 8, via the
 * `conversation_create` WS RPC) and recorded in a small out-of-band JSON file that every
 * surface reads at startup — the file-sized precursor to the rail's `conversation_meta`.
 *
 * Targeting is deliberately NOT by recency (enrichment/agent turns pollute it) and NOT the
 * literal `"default"` (auto-creates + is the legacy `~/bin/letta-*` wrapper target → cross-talk).
 */

import { readFile, writeFile } from "node:fs/promises";

export interface ContinuityPointer {
  agentId: string;
  conversationId: string;
  /** Optional human label / provenance; ignored by the client. */
  label?: string;
}

interface PointerFileShape {
  agent_id?: unknown;
  conversation_id?: unknown;
  label?: unknown;
}

export class PointerError extends Error {
  override name = "PointerError";
}

/** Read and validate the durable pointer file. Throws PointerError with an actionable message. */
export async function readPointer(path: string): Promise<ContinuityPointer> {
  let text: string;
  try {
    text = await readFile(path, "utf-8");
  } catch (e) {
    throw new PointerError(
      `cannot read continuity pointer at ${path}: ${(e as Error).message}. Seed it at cutover (Unit 8) via the conversation_create WS RPC.`,
    );
  }
  let parsed: PointerFileShape;
  try {
    parsed = JSON.parse(text) as PointerFileShape;
  } catch (e) {
    throw new PointerError(
      `continuity pointer at ${path} is not valid JSON: ${(e as Error).message}`,
    );
  }
  if (typeof parsed.agent_id !== "string" || parsed.agent_id.length === 0) {
    throw new PointerError(`continuity pointer at ${path} is missing a non-empty \`agent_id\``);
  }
  if (typeof parsed.conversation_id !== "string" || parsed.conversation_id.length === 0) {
    throw new PointerError(
      `continuity pointer at ${path} is missing a non-empty \`conversation_id\``,
    );
  }
  if (parsed.conversation_id === "default") {
    throw new PointerError(
      `continuity pointer at ${path} points at "default" — use a dedicated conversation UUID (the default conversation is the legacy wrapper target and causes cross-talk)`,
    );
  }
  const pointer: ContinuityPointer = {
    agentId: parsed.agent_id,
    conversationId: parsed.conversation_id,
  };
  if (typeof parsed.label === "string") pointer.label = parsed.label;
  return pointer;
}

/** Write the durable pointer file (used by the cutover seed step, Unit 8). */
export async function writePointer(path: string, pointer: ContinuityPointer): Promise<void> {
  const body: PointerFileShape = {
    agent_id: pointer.agentId,
    conversation_id: pointer.conversationId,
  };
  if (pointer.label !== undefined) body.label = pointer.label;
  await writeFile(path, `${JSON.stringify(body, null, 2)}\n`, "utf-8");
}
