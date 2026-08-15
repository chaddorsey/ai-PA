/**
 * Live capture harness for the three questions the ownership/attribution design conversation
 * needs answered. Raw WS against the sole-owner App Server — a pure client, never a second
 * writer on the backend.
 *
 *   node tools/capture-ownership.mjs two-inputs     <agent-id>   # Q2
 *   node tools/capture-ownership.mjs queue-replay2  <agent-id>   # Q3 — peer's socket dropped
 *   node tools/capture-ownership.mjs queue-control  <agent-id>   # Q3 control — peer stays up
 *   node tools/capture-ownership.mjs approval-park  <agent-id>   # Q1
 *
 * `CAPTURE_OUT=<file>.jsonl` keeps the raw frames. Results and what they mean:
 * docs/followups/2026-08-15-continuity-ownership-live-captures.md
 *
 * Every frame is logged with an elapsed-ms stamp so ORDERING — which is the whole question in
 * two of the three — is readable rather than inferred.
 *
 * `queue-replay` (single-socket) is superseded by `queue-replay2` and kept only because it is
 * what demonstrated that a single socket NEVER queues: the server defers the second ack instead.
 * That negative result is half of Q2's answer, so the scenario that produced it stays.
 *
 * Always run against a DISPOSABLE agent (tools/scratch-agent.mjs) and delete it afterwards.
 */
import fs from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(
  "/Volumes/main-drive/ai-PA/clients/letta-continuity-core/package.json",
);
const { WebSocket } = require("ws");

const URL_ = process.env.LETTA_LIVE_WS_URL ?? "ws://127.0.0.1:4577/ws";
const [scenario, agentId] = process.argv.slice(2);
const CONVERSATION = process.env.CAPTURE_CONVERSATION ?? "default";
if (!scenario || !agentId) {
  console.error("usage: node capture.mjs <approval-park|two-inputs|queue-replay> <agent-id>");
  process.exit(2);
}
const runtime = { agent_id: agentId, conversation_id: CONVERSATION };

const t0 = Date.now();
const log = [];
function record(direction, frame) {
  const entry = { ms: Date.now() - t0, direction, type: frame.type, frame };
  log.push(entry);
  const summary =
    frame.type === "update_loop_status"
      ? `status=${frame.loop_status?.status} active=${JSON.stringify(frame.loop_status?.active_run_ids ?? [])}`
      : frame.type === "input_accepted"
        ? `accepted=${frame.accepted} disposition=${frame.disposition ?? "-"} req=${frame.request_id}`
        : frame.type === "update_queue"
          ? `queue=${JSON.stringify((frame.queue ?? []).map((q) => q.client_message_id))} removed=${JSON.stringify(frame.removed ?? [])}`
          : frame.type === "control_request"
            ? `subtype=${frame.request?.subtype} tool=${frame.request?.tool_name} req=${frame.request_id}`
            : frame.type === "stream_delta"
              ? `msg_type=${frame.delta?.message_type} run=${frame.delta?.run_id ?? "-"}`
              : frame.type === "turn_finished"
                ? `stop=${frame.stop_reason} run=${frame.run_id ?? "-"}`
                : "";
  console.log(`${String(entry.ms).padStart(7)}ms ${direction === "in" ? "<-" : "->"} ${frame.type}  ${summary}`);
}

function connect() {
  const ws = new WebSocket(URL_);
  ws.on("error", (e) => console.error(`WS error: ${e.message}`));
  ws.on("message", (d) => {
    const frame = JSON.parse(d.toString());
    record("in", frame);
    ws.emit("frame", frame);
  });
  return ws;
}

function send(ws, frame) {
  record("out", frame);
  ws.send(JSON.stringify(frame));
}

function hello(ws, requestId = "rpc-hello") {
  return new Promise((resolve) => {
    const onFrame = (f) => {
      if (f.type === "runtime_start_response" && f.request_id === requestId) {
        ws.off("frame", onFrame);
        resolve(f);
      }
    };
    ws.on("frame", onFrame);
    send(ws, { type: "runtime_start", request_id: requestId, ...runtime });
  });
}

function input(ws, text, n) {
  send(ws, {
    type: "input",
    request_id: `rpc-in-${n}`,
    runtime,
    payload: {
      kind: "create_message",
      client_message_id: `cm-${n}`,
      exclude_interactive_tools: true,
      messages: [{ role: "user", content: text, client_message_id: `cm-${n}` }],
    },
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Raw frames, so the design conversation reads evidence rather than my summary of it. */
function dump() {
  const out = process.env.CAPTURE_OUT;
  if (!out) return;
  fs.writeFileSync(out, log.map((e) => JSON.stringify(e)).join("\n"));
  console.log("raw frames -> " + out);
}

function waitFor(ws, predicate, ms, label) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      ws.off("frame", onFrame);
      console.log(`      … timed out after ${ms}ms waiting for ${label}`);
      resolve(null);
    }, ms);
    const onFrame = (f) => {
      if (!predicate(f)) return;
      clearTimeout(timer);
      ws.off("frame", onFrame);
      resolve(f);
    };
    ws.on("frame", onFrame);
  });
}

async function main() {
  const ws = connect();
  await new Promise((r) => ws.on("open", r));
  await hello(ws);

  if (scenario === "approval-park") {
    // Q1: does the runtime report WAITING_ON_INPUT while a turn is PARKED on an approval?
    // A6 says the one-shot exits 0 with the reply missing because it does. Deliberately do NOT
    // answer the control_request until the observation window has closed.
    console.log("\n--- asking for a tool the runtime must gate on ---");
    input(ws, "Run the shell command `echo continuity-probe` using the Bash tool.", 1);
    const cr = await waitFor(ws, (f) => f.type === "control_request", 90_000, "control_request");
    if (!cr) {
      console.log("\nRESULT: no control_request arrived — this runtime did not gate the tool.");
    } else {
      console.log(`\n--- control_request outstanding; watching 15s WITHOUT answering ---`);
      const before = log.length;
      await sleep(15_000);
      const during = log.slice(before).filter((e) => e.type === "update_loop_status");
      const idle = during.filter((e) => e.frame.loop_status?.status === "WAITING_ON_INPUT");
      console.log(
        `\nRESULT: while parked on the approval, ${during.length} loop_status frame(s), of which ` +
          `${idle.length} were WAITING_ON_INPUT.`,
      );
      console.log(`Q1 ANSWER: ${idle.length > 0 ? "YES — the runtime reports IDLE while parked (A6 CONFIRMED)" : "NO — no idle while parked (A6 killed on this path)"}`);
      // Release it so the scratch agent is not left holding a parked turn.
      console.log("\n--- denying to release the parked turn ---");
      send(ws, {
        type: "input",
        request_id: "rpc-deny-1",
        runtime,
        payload: {
          kind: "approval_response",
          request_id: cr.request_id,
          decision: { behavior: "deny", message: "capture probe: denied" },
        },
      });
      await sleep(4000);
    }
  }

  if (scenario === "two-inputs") {
    // Q2: can two `input` frames on ONE socket both be acked started/submitting? If they can,
    // "one armed claim at a time" is not a safe assumption for the Unit 6 bridge (A4/A8).
    console.log("\n--- two inputs, back to back, on one socket ---");
    input(ws, "Reply with exactly: one", 1);
    input(ws, "Reply with exactly: two", 2);
    await sleep(20_000);
    const acks = log.filter((e) => e.type === "input_accepted");
    console.log(`\nRESULT: ${acks.length} input_accepted frame(s):`);
    for (const a of acks) {
      console.log(`  req=${a.frame.request_id} accepted=${a.frame.accepted} disposition=${a.frame.disposition ?? "-"}`);
    }
    const live = acks.filter((a) => a.frame.disposition === "started" || a.frame.disposition === "submitting");
    console.log(`Q2 ANSWER: ${live.length >= 2 ? "YES — two concurrent inputs were BOTH acked live (queue is not the only path)" : "NO — the second was queued or refused; serialization holds"}`);
  }

  if (scenario === "detach-cancels") {
    // Does detaching the ONLY subscribed client cancel the running turn?
    //
    // The docs say: "If no other subscribed client can take over an active runtime, App Server
    // requests cancellation of its active turn." Our terminal prints the opposite on exit —
    // "detached (the conversation continues on the server)" — and its --help says Ctrl-C leaves
    // the client while "the conversation and any running turn continue". In M1 terminal usage the
    // terminal usually IS the only subscribed client, so if the docs are right that message is
    // false at the moment it is printed.
    console.log("\n--- starting a genuinely LONG turn as the only subscribed client ---");
    // A text-generation prompt is NOT long enough: measured, the model counted to 60 in 2.4s and
    // the turn was over before the socket could be dropped, which proves nothing. A sleeping
    // shell command holds the runtime in EXECUTING_CLIENT_SIDE_TOOL for a known duration, so the
    // drop is guaranteed to land mid-turn.
    input(ws, "Run this exact shell command with the Bash tool: sleep 25; echo finished", 1);
    await waitFor(
      ws,
      (f) =>
        f.type === "update_loop_status" &&
        f.loop_status?.status === "EXECUTING_CLIENT_SIDE_TOOL",
      45_000,
      "the tool to start executing",
    );
    console.log("\n--- tool is executing; DROPPING the only client mid-turn ---");
    ws.terminate();
    await sleep(6000);

    const ws2 = connect();
    await new Promise((r) => ws2.on("open", r));
    const before = log.length;
    record("out", { type: "runtime_start", request_id: "rpc-hello-2", ...runtime });
    ws2.send(JSON.stringify({ type: "runtime_start", request_id: "rpc-hello-2", ...runtime }));
    console.log("\n--- reconnected; watching 20s to see whether the turn survived ---");
    await sleep(20_000);

    const after = log.slice(before);
    const statuses = after
      .filter((e) => e.type === "update_loop_status")
      .map((e) => e.frame.loop_status?.status);
    const resumedDeltas = after.filter(
      (e) => e.type === "stream_delta" && e.frame.delta?.message_type === "assistant_message",
    ).length;
    const stillRunning = statuses.some((s) => s && s !== "WAITING_ON_INPUT");
    console.log(`\nRESULT: statuses after reconnect = ${JSON.stringify([...new Set(statuses)])}`);
    console.log(`        assistant deltas after reconnect = ${resumedDeltas}`);
    console.log(
      `ANSWER: ${
        stillRunning || resumedDeltas > 0
          ? "the turn SURVIVED the detach — our --help/exit message is correct"
          : "the turn did NOT survive — the runtime is idle, so detaching the only client ENDED it, and the shipped message is FALSE"
      }`,
    );
    ws2.close();
    dump();
    console.log(`\n=== ${log.length} frames captured ===`);
    process.exit(0);
  }

  if (scenario === "queue-control") {
    // CONTROL for the Q3 result: identical to queue-replay2 except B's socket is never dropped.
    // If cm-b is `dequeued` and runs here, then the `cancelled` seen in queue-replay2 was caused
    // by the socket going away — not by queueing itself.
    console.log("\n--- second peer attaches (control: B stays connected) ---");
    const wsB = connect();
    await new Promise((r) => wsB.on("open", r));
    await new Promise((resolve) => {
      const onFrame = (f) => {
        if (f.type === "runtime_start_response" && f.request_id === "rpc-hello-b") {
          wsB.off("frame", onFrame);
          resolve(f);
        }
      };
      wsB.on("frame", onFrame);
      record("out", { type: "runtime_start", request_id: "rpc-hello-b", ...runtime });
      wsB.send(JSON.stringify({ type: "runtime_start", request_id: "rpc-hello-b", ...runtime }));
    });

    input(ws, "Count slowly from 1 to 40, one number per line, with a short pause between each.", 1);
    await sleep(700);
    record("out", { type: "input", request_id: "rpc-in-b", note: "from peer B" });
    wsB.send(
      JSON.stringify({
        type: "input",
        request_id: "rpc-in-b",
        runtime,
        payload: {
          kind: "create_message",
          client_message_id: "cm-b",
          exclude_interactive_tools: true,
          messages: [{ role: "user", content: "Reply with exactly: BBB", client_message_id: "cm-b" }],
        },
      }),
    );
    await sleep(45_000);
    const removals = log
      .filter((e) => e.type === "update_queue")
      .flatMap((e) => e.frame.removed ?? []);
    console.log(`\nRESULT (control): removals seen = ${JSON.stringify(removals)}`);
    const dequeued = removals.some((r) => r.client_message_id === "cm-b" && r.disposition === "dequeued");
    console.log(
      `CONTROL ANSWER: ${dequeued ? "cm-b was DEQUEUED and ran — so `cancelled` in the drop run was caused by the SOCKET GOING AWAY" : "cm-b was NOT dequeued even with B connected — cancellation is not drop-specific"}`,
    );
    wsB.close();
    ws.close();
    dump();
    console.log(`\n=== ${log.length} frames captured ===`);
    process.exit(0);
  }

  if (scenario === "queue-replay2") {
    // Q3, on the shape that can actually produce a queue: TWO sockets. A single socket never
    // queues — the server defers the second ack instead (see the two-inputs capture) — so the
    // update_queue path only exists between peers, which is also the shape A8 is about.
    console.log("\n--- second peer attaches ---");
    const wsB = connect();
    await new Promise((r) => wsB.on("open", r));
    await new Promise((resolve) => {
      const onFrame = (f) => {
        if (f.type === "runtime_start_response" && f.request_id === "rpc-hello-b") {
          wsB.off("frame", onFrame);
          resolve(f);
        }
      };
      wsB.on("frame", onFrame);
      record("out", { type: "runtime_start", request_id: "rpc-hello-b", ...runtime });
      wsB.send(JSON.stringify({ type: "runtime_start", request_id: "rpc-hello-b", ...runtime }));
    });

    console.log("\n--- peer A starts a LONG turn; peer B injects behind it ---");
    input(ws, "Count slowly from 1 to 40, one number per line, with a short pause between each.", 1);
    await sleep(700);
    record("out", { type: "input", request_id: "rpc-in-b", note: "from peer B" });
    wsB.send(
      JSON.stringify({
        type: "input",
        request_id: "rpc-in-b",
        runtime,
        payload: {
          kind: "create_message",
          client_message_id: "cm-b",
          exclude_interactive_tools: true,
          messages: [{ role: "user", content: "Reply with exactly: BBB", client_message_id: "cm-b" }],
        },
      }),
    );

    const queued = await waitFor(
      wsB,
      (f) => f.type === "update_queue" && (f.queue ?? []).length > 0,
      45_000,
      "a non-empty update_queue on peer B",
    );
    if (!queued) {
      console.log("\nRESULT: B was never queued — the server deferred its ack instead.");
      console.log("Q3 ANSWER: NOT OBSERVABLE on this path — no queue entry means no removal to replay.");
    } else {
      console.log("\n--- B is queued; dropping B's socket before its removal arrives ---");
      wsB.terminate();
      await sleep(1200);
      const wsB2 = connect();
      await new Promise((r) => wsB2.on("open", r));
      const before = log.length;
      record("out", { type: "runtime_start", request_id: "rpc-hello-b2", ...runtime });
      wsB2.send(JSON.stringify({ type: "runtime_start", request_id: "rpc-hello-b2", ...runtime }));
      console.log("\n--- B reconnected; watching 40s for a replayed removal ---");
      await sleep(40_000);
      const after = log.slice(before);
      const removals = after.filter(
        (e) => e.type === "update_queue" && (e.frame.removed ?? []).length > 0,
      );
      console.log(`\nRESULT: after B's reconnect, ${removals.length} update_queue frame(s) carried removals.`);
      for (const r of removals) console.log(`  removed=${JSON.stringify(r.frame.removed)}`);
      console.log(
        `Q3 ANSWER: ${removals.length > 0 ? "YES — a removal IS delivered after the reconnect (A8 live)" : "NO — no removal replay observed after the reconnect"}`,
      );
      wsB2.close();
    }
    ws.close();
    dump();
    console.log(`\n=== ${log.length} frames captured ===`);
    process.exit(0);
  }

  if (scenario === "queue-replay") {
    // Q3: does the server re-broadcast update_queue REMOVALS after a reconnect? A8 says a
    // replayed removal re-arms a reconnect-demoted claim and then binds a peer's run.
    console.log("\n--- input A (runs), input B (should queue) ---");
    input(ws, "Count slowly from 1 to 20, one number per line.", 1);
    await sleep(1500);
    input(ws, "Reply with exactly: second", 2);
    const queued = await waitFor(
      ws,
      (f) => f.type === "update_queue" && (f.queue ?? []).length > 0,
      30_000,
      "a non-empty update_queue",
    );
    if (!queued) {
      console.log("\nRESULT: nothing ever queued — cannot observe a removal replay on this path.");
    } else {
      console.log("\n--- dropping the socket while B is queued ---");
      ws.terminate();
      await sleep(1500);
      const ws2 = connect();
      await new Promise((r) => ws2.on("open", r));
      const before = log.length;
      await hello(ws2, "rpc-hello-2");
      console.log("\n--- reconnected; watching 25s for a replayed removal ---");
      await sleep(25_000);
      const after = log.slice(before);
      const removals = after.filter((e) => e.type === "update_queue" && (e.frame.removed ?? []).length > 0);
      console.log(`\nRESULT: after the reconnect, ${removals.length} update_queue frame(s) carried removals.`);
      for (const r of removals) console.log(`  removed=${JSON.stringify(r.frame.removed)}`);
      console.log(`Q3 ANSWER: ${removals.length > 0 ? "YES — removals ARE re-broadcast after a reconnect (A8 CONFIRMED)" : "NO — no removal replay observed (A8 killed on this path)"}`);
      ws2.close();
      dump();
  console.log(`\n=== ${log.length} frames captured ===`);
      process.exit(0);
    }
  }

  ws.close();
  dump();
  console.log(`\n=== ${log.length} frames captured ===`);
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
