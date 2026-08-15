/**
 * The test double must speak the protocol, not a copy of it.
 *
 * WHY THIS EXISTS. `mockServer.ts` was a second, unversioned transcription of the wire vocabulary
 * bound to `protocol.ts` by nothing at all — 29+ raw literals, three of which
 * (`SENDING_API_REQUEST`, `EXECUTING_CLIENT_SIDE_TOOL`, `tool_call_message`) did not appear in
 * `protocol.ts` in any form. The consequence was measured, not theorised: renaming the double's
 * `tool_call_message` left the entire suite green. So the suite could certify agreement between
 * the client and a double that no longer resembled the server, which is the specific way a
 * "verified" round ships a silent mis-parse.
 *
 * `protocol.ts` is declared the single home of every wire string. This test is what makes that a
 * rule rather than an aspiration: every string literal in the double must either BE a value
 * exported by `protocol.ts`, or be listed below as deliberately not a wire value. There is no
 * third option, so adding a new wire string to the double without adding it to `protocol.ts` fails
 * here — by construction, rather than by someone noticing in review.
 *
 * SCOPE, STATED HONESTLY. This gates wire *values*. Field *names* (`delta.message_type`,
 * `loop_status.status`) are unquoted object keys and invisible to it; those are gated by
 * `validateInboundFrame` and the live contract tests instead. The `check:live` leg remains the
 * only thing that can prove `protocol.ts` matches the SERVER — this proves the double matches
 * `protocol.ts`, which is the half that was previously proven by nothing.
 */

import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import * as protocol from "../src/protocol.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const DOUBLE_PATH = join(HERE, "helpers", "mockServer.ts");

/**
 * Strings in the double that are deliberately NOT wire vocabulary.
 *
 * Every entry is here because it is a fixture detail, a Node/ws API string, or a mock-only knob —
 * never because adding it to `protocol.ts` was inconvenient. If a new entry is a value the SERVER
 * sends or receives, it belongs in `protocol.ts` instead; that is the whole decision this list
 * forces someone to make out loud.
 */
const NOT_WIRE_VOCABULARY: ReadonlySet<string> = new Set([
  // `typeof` guards.
  "string",
  "function",
  "object",
  // A TypeScript indexed-access type (`ConnState["runtime"]`), not a value on any frame.
  "runtime",
  // Module specifiers.
  "node:net",
  "ws",
  "../../src/protocol.js",
  "../../src/ws.js",
  // Node and `ws` event names / bind address — this side of the socket, not the protocol.
  "listening",
  "connection",
  "close",
  "error",
  "127.0.0.1",
  // Mock-only option values (`MockServerOptions.erroredTurn`).
  "deltas",
  "turn-finished",
  // Human-readable text the server would generate, not tokens a client switches on.
  "server going away",
  "Approval request is no longer pending",
  "Error code: 404 - model `openai/gpt-slop-1` not found or not accessible",
  // Fixture payload data.
  "mock-agent",
  "local-conv-1",
  "OK",
  "Bash",
  "echo hi",
  "",
]);

/** ISO timestamps used as fixture dates. Values, not vocabulary. */
const FIXTURE_DATE = /^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/;

/**
 * Every string value `protocol.ts` exports, however it is packaged — a bare constant, a frozen
 * lookup object, a Set, or an array. Walking the module rather than naming the containers means a
 * NEW vocabulary group is covered the moment it is exported, with no second list to maintain.
 */
function protocolStringValues(): Set<string> {
  const out = new Set<string>();
  const absorb = (value: unknown): void => {
    if (typeof value === "string") {
      out.add(value);
      return;
    }
    if (value instanceof Set || Array.isArray(value)) {
      for (const v of value) absorb(v);
      return;
    }
    // Plain lookup objects (`Inbound`, `DeltaMessageTypes`, `RpcResponseFor`, …). Classes and
    // functions are skipped: `typeof` is "function", so they never reach here.
    if (value && typeof value === "object") {
      for (const v of Object.values(value)) absorb(v);
    }
  };
  for (const exported of Object.values(protocol)) absorb(exported);
  return out;
}

/** Double-quoted string literals in `source`, with comments removed first. */
function stringLiterals(source: string): string[] {
  const withoutComments = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  return [...withoutComments.matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => m[1] ?? "");
}

describe("the test double's fidelity to protocol.ts", () => {
  it("invents no wire vocabulary of its own", async () => {
    const source = await readFile(DOUBLE_PATH, "utf-8");
    const known = protocolStringValues();

    const unexplained = [
      ...new Set(
        stringLiterals(source).filter(
          (lit) => !known.has(lit) && !NOT_WIRE_VOCABULARY.has(lit) && !FIXTURE_DATE.test(lit),
        ),
      ),
    ];

    // Naming them in the failure is the point: the fix is either "add it to protocol.ts" or
    // "declare it non-wire", and the reader should not have to work out which strings are meant.
    expect(
      unexplained,
      [
        "mockServer.ts contains string literals that are neither exported by protocol.ts nor declared non-wire.",
        "If these are values the server sends or receives, add them to protocol.ts (its single-home rule).",
        "If they are fixture data, add them to NOT_WIRE_VOCABULARY in this file.",
        `Unexplained: ${JSON.stringify(unexplained)}`,
      ].join("\n"),
    ).toEqual([]);
  });

  it("sources the three strings it used to invent from protocol.ts", async () => {
    // Named explicitly because these three are the measured hole: they existed ONLY in the double,
    // so there was no shared definition for a rename to break. A generic "no unexplained literals"
    // check would also pass if someone deleted the frames that use them.
    const source = await readFile(DOUBLE_PATH, "utf-8");
    const literals = new Set(stringLiterals(source));

    for (const invented of [
      protocol.LoopStatuses.sendingApiRequest,
      protocol.LoopStatuses.executingClientSideTool,
      protocol.DeltaMessageTypes.toolCall,
    ]) {
      expect(literals.has(invented)).toBe(false);
      expect(source).toContain(invented.length > 0 ? "protocol.js" : "");
    }

    // And they are reachable as protocol values, so the double and the client cannot disagree.
    expect(protocol.LoopStatuses.sendingApiRequest).toBe("SENDING_API_REQUEST");
    expect(protocol.LoopStatuses.executingClientSideTool).toBe("EXECUTING_CLIENT_SIDE_TOOL");
    expect(protocol.DeltaMessageTypes.toolCall).toBe("tool_call_message");
  });

  it("names the error deltas an errored turn is carried on", async () => {
    // B1's vocabulary. Both are on the wire and both were dropped, so a provider outage rendered
    // as an empty successful turn. They are asserted here so that deleting them from protocol.ts
    // fails loudly rather than silently reverting the renderer to dropping them.
    expect(protocol.DeltaMessageTypes.loopError).toBe("loop_error");
    expect(protocol.DeltaMessageTypes.errorMessage).toBe("error_message");
    expect([...protocol.ERROR_DELTA_TYPES].sort()).toEqual(["error_message", "loop_error"]);
    // `loop_error` is a CONTROL delta: it carries no `delta.id`, so requiring the watermark would
    // make `validateInboundFrame` reject the real frame as drift and drop it before the renderer
    // ever sees it — which would leave B1 fixed in the renderer and still broken end to end.
    expect(protocol.CONTROL_DELTA_TYPES.has("loop_error")).toBe(true);
  });
});
