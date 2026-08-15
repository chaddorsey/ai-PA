#!/usr/bin/env node
/**
 * Mint or remove a disposable agent on the sole-owner App Server.
 *
 * WHY THIS EXISTS. The live contract gate (`test/live.contract.test.ts`) and the manual end-to-end
 * both need SOME low-stakes agent to talk to. They default to the docs agent, and on 2026-08-14
 * that stopped working for a reason with nothing to do with the protocol: its model group
 * (`deepseek-v4-flash`) began answering 404 at the provider — "Model not found, inaccessible,
 * and/or not deployed" — so every turn ends `stop_reason: "error"` and three of the gate's four
 * checks fail while the server is behaving perfectly.
 *
 * A gate that cannot distinguish "the protocol drifted" from "one agent's model is down" is not a
 * gate. So the agent is now an input, and this mints a throwaway one to be that input.
 *
 *   node tools/scratch-agent.mjs                       # create; prints the agent id
 *   node tools/scratch-agent.mjs delete <agent-id>     # remove it again
 *   MODEL=lmstudio/gpt-5.2 node tools/scratch-agent.mjs
 *
 * Then:
 *   LETTA_LIVE_WS=1 LETTA_LIVE_WS_AGENT=<id> \
 *     LETTA_LIVE_WS_EXPECT_VERSION=<running version> npx vitest run test/live.contract.test.ts
 *
 * Delete it when you are done. Leaving scratch agents behind is how a fleet turns into a list of
 * things nobody dares remove.
 */

import { createRequire } from "node:module";

const require = createRequire(new URL("../letta-continuity-core/package.json", import.meta.url));
const { WebSocket } = require("ws");

const URL_ = process.env.LETTA_LIVE_WS_URL ?? "ws://127.0.0.1:4577/ws";
const MODEL = process.env.MODEL ?? "lmstudio/gpt-5.4-nano";
const [mode, target] = process.argv.slice(2);

if (mode === "delete" && !target) {
  console.error("usage: node tools/scratch-agent.mjs delete <agent-id>");
  process.exit(2);
}

const ws = new WebSocket(URL_);
ws.on("error", (err) => {
  console.error(`WS error: ${err.message}`);
  process.exit(1);
});

ws.on("open", () => {
  if (mode === "delete") {
    ws.send(JSON.stringify({ type: "agent_delete", request_id: "scratch-del", agent_id: target }));
    return;
  }
  ws.send(
    JSON.stringify({
      type: "agent_create",
      request_id: "scratch-new",
      body: {
        name: `continuity-e2e-scratch-${process.pid}`,
        model: MODEL,
        embedding: "letta/letta-free",
        tags: ["origin:letta-code", "continuity-e2e-scratch"],
      },
    }),
  );
});

ws.on("message", (data) => {
  const frame = JSON.parse(data.toString());
  if (frame.type === "agent_create_response") {
    if (!frame.success) {
      console.error(JSON.stringify(frame));
      process.exit(1);
    }
    console.log(frame.agent.id);
    ws.close();
    process.exit(0);
  }
  if (frame.type === "agent_delete_response") {
    console.log(frame.success ? `deleted ${target}` : JSON.stringify(frame));
    ws.close();
    process.exit(frame.success ? 0 : 1);
  }
});

setTimeout(() => {
  console.error("timed out waiting for the App Server");
  process.exit(1);
}, 60_000);
