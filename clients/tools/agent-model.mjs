#!/usr/bin/env node
/**
 * List or switch the model of local fleet agents, over the sole-owner App Server's WS
 * management tier (single-writer-safe: no process ever opens lc-local-backend directly).
 *
 *   node tools/agent-model.mjs                          # list agents: id, model, name
 *   node tools/agent-model.mjs set <agent-id> <model>   # switch (e.g. lmstudio/gpt-4.1-mini)
 *
 * Frame shapes verified against the 0.30.25 bundle: agent_list → {agents}, agent_update
 * takes {agent_id, body:{model}}. NOTE the model string must be one the runtime's provider
 * config resolves (the litellm "lmstudio/…" prefix family, or a native provider id) —
 * agent_update does not validate reachability; a bad id surfaces on the next turn.
 * A HOT runtime picks the change up on a later turn or restart — verify with a cheap turn.
 */

import { createRequire } from "node:module";

const require = createRequire(new URL("../letta-continuity-core/package.json", import.meta.url));
const { WebSocket } = require("ws");

const URL_ = process.env.LETTA_LIVE_WS_URL ?? "ws://127.0.0.1:4577/ws";
const [mode, agentId, model] = process.argv.slice(2);

if (mode === "set" && (!agentId || !model)) {
  console.error("usage: node tools/agent-model.mjs set <agent-id> <model>");
  process.exit(2);
}

const ws = new WebSocket(URL_);
const rpc = (frame) =>
  new Promise((resolve, reject) => {
    const request_id = `am-${Math.random().toString(36).slice(2, 10)}`;
    const timer = setTimeout(() => reject(new Error(`timeout waiting for ${frame.type}`)), 15_000);
    const onMsg = (d) => {
      const f = JSON.parse(d.toString());
      if (f.request_id !== request_id) return;
      clearTimeout(timer);
      ws.off("message", onMsg);
      resolve(f);
    };
    ws.on("message", onMsg);
    ws.send(JSON.stringify({ ...frame, request_id }));
  });

ws.on("error", (e) => {
  console.error("WS error:", e.message);
  process.exit(1);
});
ws.on("open", async () => {
  try {
    if (mode === "set") {
      const before = await rpc({ type: "agent_retrieve", agent_id: agentId });
      if (!before.success) throw new Error(before.error ?? "agent_retrieve failed");
      const resp = await rpc({ type: "agent_update", agent_id: agentId, body: { model } });
      if (!resp.success) throw new Error(resp.error ?? "agent_update failed");
      console.log(`${agentId}: ${before.agent?.model} → ${resp.agent?.model}`);
    } else {
      const resp = await rpc({ type: "agent_list" });
      if (!resp.success) throw new Error(resp.error ?? "agent_list failed");
      for (const a of resp.agents ?? [])
        console.log(`${a.id}  ${String(a.model ?? "?").padEnd(32)}  ${a.name ?? ""}`);
    }
    ws.close();
    process.exit(0);
  } catch (e) {
    console.error(e instanceof Error ? e.message : String(e));
    ws.close();
    process.exit(1);
  }
});
