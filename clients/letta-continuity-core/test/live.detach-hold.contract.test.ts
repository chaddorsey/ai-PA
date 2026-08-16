/**
 * OPT-IN live contract check: a SECOND SUBSCRIBER HOLDS A DETACHED TURN ALIVE.
 *
 * This is C1 scenario S1 (docs/plans/2026-08-15-006-controller-spike-findings.md), promoted to
 * a permanent gate. The entire Continuity Controller anchor design rests on this platform
 * BEHAVIOUR: the App Server cancels a running turn only when its LAST subscribed client
 * detaches, so a resident anchor connection keeps turns alive across worker restarts. The
 * vendor-type binding cannot see this change — it is not a shape, it is what the server DOES —
 * so it is pinned here and re-run at every server version bump alongside the main live gate:
 *
 *   LETTA_LIVE_WS=1 LETTA_LIVE_WS_URL=ws://127.0.0.1:4599/ws \
 *     LETTA_LIVE_WS_AGENT=<scratch> LETTA_LIVE_WS_EXPECT_VERSION=<candidate> \
 *     npx vitest run test/live.detach-hold.contract.test.ts
 *
 * Run it against a CANDIDATE server on a CLONE backend with a scratch agent
 * (tools/scratch-agent.mjs) — the turn deliberately executes a 20s shell command.
 * If this test starts failing on a new server version, the anchor premise is dead: the
 * controller falls back to restart-cancels-turns with journal FAILED-VISIBLE marks (plan C1
 * fallback), and G2/G3 wording in the goals doc must change.
 */
import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";
import { PINNED_PROTOCOL_VERSION, PINNED_SERVER_VERSION } from "../src/protocol.js";

const require = createRequire(import.meta.url);
const { WebSocket } = require("ws") as typeof import("ws");

const LIVE = process.env.LETTA_LIVE_WS === "1";
const URL_ = process.env.LETTA_LIVE_WS_URL ?? "ws://127.0.0.1:4577/ws";
const EXPECT_VERSION = process.env.LETTA_LIVE_WS_EXPECT_VERSION ?? PINNED_SERVER_VERSION;
const DOCS_AGENT = "agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a";
const AGENT = process.env.LETTA_LIVE_WS_AGENT ?? DOCS_AGENT;

type Frame = { type: string } & Record<string, unknown>;

function open(label: string): Promise<import("ws").WebSocket> {
  const ws = new WebSocket(URL_);
  return new Promise((resolve, reject) => {
    ws.once("open", () => resolve(ws));
    ws.once("error", (e: Error) => reject(new Error(`[${label}] ${e.message}`)));
  });
}

function frameStream(ws: import("ws").WebSocket, sink: Frame[]): void {
  ws.on("message", (d) => {
    const frame = JSON.parse(d.toString()) as Frame;
    sink.push(frame);
    ws.emit("contract-frame", frame);
  });
}

function rpc(
  ws: import("ws").WebSocket,
  frame: Frame,
  responseType: string,
  ms = 15_000,
): Promise<Frame> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error(`timeout waiting for ${responseType} (${String(frame.request_id)})`)),
      ms,
    );
    const onFrame = (f: Frame) => {
      if (f.type !== responseType || f.request_id !== frame.request_id) return;
      clearTimeout(timer);
      ws.off("contract-frame", onFrame);
      resolve(f);
    };
    ws.on("contract-frame", onFrame);
    ws.send(JSON.stringify(frame));
  });
}

function waitFrame(
  ws: import("ws").WebSocket,
  predicate: (f: Frame) => boolean,
  ms: number,
  label: string,
): Promise<Frame | null> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      ws.off("contract-frame", onFrame);
      resolve(null);
    }, ms);
    const onFrame = (f: Frame) => {
      if (!predicate(f)) return;
      clearTimeout(timer);
      ws.off("contract-frame", onFrame);
      resolve(f);
    };
    ws.on("contract-frame", onFrame);
    void label;
  });
}

describe.skipIf(!LIVE)(`live detach-hold contract (opt-in, ${URL_}, agent ${AGENT})`, () => {
  it("a second subscriber holds a detached turn alive to a clean end_turn", async () => {
    const marker = `detach-hold-gate-${process.pid}`;
    const framesA: Frame[] = [];
    const framesB: Frame[] = [];

    // --- version gate first: this behaviour pin is only meaningful against a version we name ---
    const b = await open("B");
    frameStream(b, framesB);
    const info = await rpc(
      b,
      { type: "app_server_info", request_id: "dh-info" },
      "app_server_info_response",
    );
    expect(info.letta_code_version).toBe(EXPECT_VERSION);
    expect(info.protocol_version).toBe(PINNED_PROTOCOL_VERSION);

    // --- a scratch conversation so the long turn never lands in anyone's real thread ---
    const created = await rpc(
      b,
      {
        type: "conversation_create",
        request_id: "dh-conv",
        body: { agent_id: AGENT, title: "detach-hold-gate" },
      },
      "conversation_create_response",
    );
    expect(created.success).toBe(true);
    const convId = (created.conversation as { id?: string } | null)?.id;
    if (typeof convId !== "string") throw new Error("no conversation id from conversation_create");
    const runtime = { agent_id: AGENT, conversation_id: convId };

    const helloB = await rpc(
      b,
      { type: "runtime_start", request_id: "dh-hello-b", ...runtime, mode: "unrestricted" },
      "runtime_start_response",
      30_000,
    );
    expect(helloB.success).toBe(true);

    const a = await open("A");
    frameStream(a, framesA);
    try {
      const helloA = await rpc(
        a,
        { type: "runtime_start", request_id: "dh-hello-a", ...runtime, mode: "unrestricted" },
        "runtime_start_response",
        30_000,
      );
      expect(helloA.success).toBe(true);

      // A 20s FOREGROUND tool execution — `caffeinate`, not `sleep`: the agent harness blocks
      // foreground sleep and the model then improvises nondeterministically (C1 smoke capture).
      a.send(
        JSON.stringify({
          type: "input",
          request_id: "dh-in-1",
          runtime,
          payload: {
            kind: "create_message",
            client_message_id: "dh-cm-1",
            exclude_interactive_tools: true,
            messages: [
              {
                role: "user",
                content: `Run this exact shell command with the Bash tool, as a single foreground command: caffeinate -t 20; echo ${marker}`,
                client_message_id: "dh-cm-1",
              },
            ],
          },
        }),
      );
      const executing = await waitFrame(
        a,
        (f) =>
          f.type === "update_loop_status" &&
          (f.loop_status as { status?: string } | undefined)?.status ===
            "EXECUTING_CLIENT_SIDE_TOOL",
        60_000,
        "tool execution start",
      );
      expect(
        executing,
        "the tool never started executing — scenario void, check the agent/model",
      ).not.toBeNull();

      // THE CONTRACT UNDER TEST: drop the submitting socket mid-execution. B stays subscribed.
      a.terminate();

      const terminal = await waitFrame(
        b,
        (f) => {
          if (f.type === "turn_finished") return true;
          if (f.type === "stream_delta") {
            const delta = f.delta as { message_type?: string; stop_reason?: string } | undefined;
            return (
              delta?.message_type === "stop_reason" && delta.stop_reason !== "requires_approval"
            );
          }
          return false;
        },
        60_000,
        "terminal signal on B",
      );
      expect(
        terminal,
        "no terminal signal reached the surviving subscriber within 60s",
      ).not.toBeNull();

      const stop =
        terminal?.type === "turn_finished"
          ? (terminal.stop_reason as string)
          : (terminal?.delta as { stop_reason?: string } | undefined)?.stop_reason;
      expect(stop).toBe("end_turn");

      // Completion evidence, not just termination: the tool's output reached B after A died.
      const toolOutput = framesB
        .filter((f) => f.type === "stream_delta")
        .map((f) => f.delta as { message_type?: string; tool_return?: unknown } | undefined)
        .filter((d) => d?.message_type === "tool_return_message")
        .map((d) => JSON.stringify(d?.tool_return ?? ""))
        .join("");
      expect(toolOutput).toContain(marker);
    } finally {
      if (a.readyState === a.OPEN) a.close();
      b.close();
    }
  }, 150_000);
});
