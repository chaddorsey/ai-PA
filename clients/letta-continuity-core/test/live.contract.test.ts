/**
 * OPT-IN live contract check against the real sole-owner App Server (`ws://127.0.0.1:4577/ws`).
 *
 * Skipped by default so the suite is deterministic and offline. Run explicitly on a server
 * upgrade to re-validate the wire protocol end-to-end:
 *
 *   LETTA_LIVE_WS=1 npx vitest run test/live.contract.test.ts
 *
 * Uses ONLY the low-stakes docs agent + `default` conversation + a benign no-tool prompt,
 * loopback — never MC or another agent. Every op is bounded; it cannot hang the suite.
 */

import { describe, expect, it } from "vitest";
import {
  type ConversationListResponseFrame,
  Outbound,
  type ServerFrame,
  buildConversationList,
  buildInput,
  isStreamDelta,
  isTurnFinished,
} from "../src/protocol.js";
import { WsConnection } from "../src/ws.js";

const LIVE = process.env.LETTA_LIVE_WS === "1";
const DOCS_AGENT = "agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a";
const RUNTIME = { agent_id: DOCS_AGENT, conversation_id: "default" };

describe.skipIf(!LIVE)("live contract (opt-in, :4577 docs agent)", () => {
  it("hello + conversation_list RPC + a benign streamed turn round-trip the pinned frames", async () => {
    const ws = new WsConnection({
      url: "ws://127.0.0.1:4577/ws",
      runtime: RUNTIME,
      openTimeoutMs: 8000,
      helloTimeoutMs: 10000,
      rpcTimeoutMs: 10000,
    });
    const frames: ServerFrame[] = [];
    ws.onFrame((f) => frames.push(f));
    try {
      const hello = await ws.connect();
      expect(hello.success).toBe(true);

      const list = await ws.request<ConversationListResponseFrame>(
        (rid) => buildConversationList(rid, DOCS_AGENT),
        Outbound.conversationList,
      );
      expect(Array.isArray(list.conversations)).toBe(true);

      const done = new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("no turn_finished within 60s")), 60000);
        ws.onFrame((f) => {
          if (isTurnFinished(f)) {
            clearTimeout(timer);
            resolve();
          }
        });
      });
      ws.send(buildInput(RUNTIME, "Reply with exactly: OK. No tools."));
      await done;

      expect(frames.some((f) => isStreamDelta(f))).toBe(true);
      expect(frames.some((f) => isTurnFinished(f))).toBe(true);
    } finally {
      ws.close();
    }
  }, 90000);
});
