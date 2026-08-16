/**
 * Unit C1 platform spike — the load-bearing assumptions of the Continuity Controller
 * (docs/plans/2026-08-15-006-feat-continuity-controller-plan.md), each as a live scenario
 * against a CLONE backend. Findings: docs/plans/2026-08-15-006-controller-spike-findings.md.
 *
 *   node tools/capture-controller-spike.mjs smoke    <agent-id>              # model + tool sanity
 *   node tools/capture-controller-spike.mjs s1       <agent-id>              # detach w/ 2nd subscriber (P1)
 *   node tools/capture-controller-spike.mjs s1proc   <agent-id>              # same, B in a separate process
 *   node tools/capture-controller-spike.mjs s2       <agent-id>              # late-subscribing anchor
 *   node tools/capture-controller-spike.mjs s3       <agent-id>              # local queue + otid recoverability
 *   node tools/capture-controller-spike.mjs s4server <agent-id>              # server-queued msg dies w/ socket
 *   node tools/capture-controller-spike.mjs s4local  <agent-id>              # locally-queued msg survives
 *   node tools/capture-controller-spike.mjs s5       <agent-id>              # external tool orphaned by registrar death
 *   node tools/capture-controller-spike.mjs s6       <agent-id>              # 2 runtimes (convs), 1 socket
 *   node tools/capture-controller-spike.mjs s6b      <agent-id> <agent-id-2> # 2 runtimes (agents), 1 socket
 *
 * Every scenario writes raw frames to docs/followups/captures/controller-spike-<name>.jsonl
 * (CAPTURE_OUT overrides). Frames are stamped with elapsed ms and the CONNECTION they arrived
 * on, because "who was subscribed when" is the whole question in half of these.
 *
 * SAFETY: refuses the live sole-owner (:4577) unless SPIKE_ALLOW_LIVE=1. Run against the clone:
 *   SPIKE_WS_URL=ws://127.0.0.1:4599/ws   (default)
 * with agents minted by tools/scratch-agent.mjs on that clone.
 */
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(new URL("../letta-continuity-core/package.json", import.meta.url));
const { WebSocket } = require("ws");

const URL_ = process.env.SPIKE_WS_URL ?? "ws://127.0.0.1:4599/ws";
if (URL_.includes(":4577") && process.env.SPIKE_ALLOW_LIVE !== "1") {
  console.error("refusing to run the spike against :4577 (live sole-owner). Set SPIKE_ALLOW_LIVE=1 to override.");
  process.exit(2);
}
const [scenario, agentId, agentId2] = process.argv.slice(2);
if (!scenario || !agentId) {
  console.error("usage: node capture-controller-spike.mjs <smoke|s1|s1proc|s2|s3|s4server|s4local|s5|s6|s6b|subscribe-hold> <agent-id> [agent-id-2]");
  process.exit(2);
}

const __filename = fileURLToPath(import.meta.url);
const CAPTURE_DIR = path.resolve(path.dirname(__filename), "../../docs/followups/captures");
const OUT = process.env.CAPTURE_OUT ?? path.join(CAPTURE_DIR, `controller-spike-${scenario}.jsonl`);

const t0 = Date.now();
const log = [];
function record(conn, direction, frame) {
  const entry = { ms: Date.now() - t0, conn, direction, type: frame.type, frame };
  log.push(entry);
  const summary =
    frame.type === "update_loop_status"
      ? `status=${frame.loop_status?.status} active=${JSON.stringify(frame.loop_status?.active_run_ids ?? [])}`
      : frame.type === "input_accepted"
        ? `accepted=${frame.accepted} disposition=${frame.disposition ?? "-"} req=${frame.request_id}`
        : frame.type === "update_queue"
          ? `queue=${JSON.stringify((frame.queue ?? []).map((q) => q.client_message_id))} removed=${JSON.stringify(frame.removed ?? [])}`
          : frame.type === "stream_delta"
            ? `msg_type=${frame.delta?.message_type}${frame.subagent_id ? " SUBAGENT" : ""} run=${frame.delta?.run_id ?? "-"}${frame.delta?.message_type === "stop_reason" ? ` stop=${frame.delta?.stop_reason}` : ""}`
            : frame.type === "turn_finished"
              ? `stop=${frame.stop_reason} run=${frame.run_id ?? "-"} seq=${frame.event_seq}`
              : frame.type === "external_tool_call_request"
                ? `tool=${frame.tool_name} call=${frame.tool_call_id} req=${frame.request_id}`
                : frame.type === "control_request"
                  ? `subtype=${frame.request?.subtype} tool=${frame.request?.tool_name} req=${frame.request_id}`
                  : "";
  console.log(`${String(entry.ms).padStart(7)}ms [${conn}] ${direction === "in" ? "<-" : "->"} ${frame.type}  ${summary}`);
}

function connect(label) {
  const ws = new WebSocket(URL_);
  ws.spikeLabel = label;
  ws.on("error", (e) => console.error(`[${label}] WS error: ${e.message}`));
  ws.on("message", (d) => {
    const frame = JSON.parse(d.toString());
    record(label, "in", frame);
    ws.emit("frame", frame);
  });
  return new Promise((resolve) => ws.on("open", () => resolve(ws)));
}

function send(ws, frame) {
  record(ws.spikeLabel, "out", frame);
  ws.send(JSON.stringify(frame));
}

let rpcN = 0;
function rpc(ws, frame, responseType, ms = 30_000) {
  const request_id = frame.request_id ?? `rpc-${++rpcN}`;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      ws.off("frame", onFrame);
      reject(new Error(`timeout waiting for ${responseType} (${request_id})`));
    }, ms);
    const onFrame = (f) => {
      if (f.type !== responseType || f.request_id !== request_id) return;
      clearTimeout(timer);
      ws.off("frame", onFrame);
      resolve(f);
    };
    ws.on("frame", onFrame);
    send(ws, { ...frame, request_id });
  });
}

/** runtime_start with the controller's intended posture; returns {resp, runtime}. */
async function hello(ws, agent, extra = {}) {
  const resp = await rpc(
    ws,
    { type: "runtime_start", agent_id: agent, conversation_id: extra.create_conversation ? undefined : (extra.conversation_id ?? "default"), mode: "unrestricted", ...extra },
    "runtime_start_response",
    60_000,
  );
  if (!resp.success) throw new Error(`runtime_start failed on [${ws.spikeLabel}]: ${resp.error}`);
  return { resp, runtime: resp.runtime };
}

let msgN = 0;
function input(ws, runtime, text, cmId) {
  const n = ++msgN;
  const client_message_id = cmId ?? `cm-${scenario}-${n}`;
  send(ws, {
    type: "input",
    request_id: `rpc-in-${n}`,
    runtime,
    payload: {
      kind: "create_message",
      client_message_id,
      exclude_interactive_tools: true,
      messages: [{ role: "user", content: text, client_message_id }],
    },
  });
  return client_message_id;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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

/**
 * The terminality disjunction under test: per-run stop_reason delta | loop_error.is_terminal |
 * turn_finished — with subagent frames filtered. A run only terminalizes ONCE globally: the
 * smoke capture showed `turn_finished` for run N arriving after run N's stop_reason delta (and
 * after a subsequent submit), so without the dedup a later wait would latch the PREVIOUS turn's
 * tail — exactly the trap C4's state machine must not fall into.
 */
const terminalRuns = new Set();
function waitTerminal(ws, runtime, ms, label) {
  const sameRuntime = (f) =>
    !f.runtime || (f.runtime.agent_id === runtime.agent_id && f.runtime.conversation_id === runtime.conversation_id);
  const freshRun = (runId) => {
    const key = runId ?? "unknown-run";
    if (terminalRuns.has(key)) return false;
    terminalRuns.add(key);
    return true;
  };
  return waitFor(
    ws,
    (f) => {
      if (!sameRuntime(f)) return false;
      if (f.type === "stream_delta" && !f.subagent_id) {
        if (f.delta?.message_type === "stop_reason" && f.delta?.stop_reason !== "requires_approval")
          return freshRun(f.delta?.run_id);
        if (f.delta?.message_type === "loop_error" && f.delta?.is_terminal) return freshRun(f.delta?.run_id);
      }
      if (f.type === "turn_finished") return freshRun(f.run_id);
      return false;
    },
    ms,
    label ?? "a terminal signal",
  );
}

function dump() {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, log.map((e) => JSON.stringify(e)).join("\n") + "\n");
  console.log(`raw frames -> ${OUT}`);
}

function finish(code = 0) {
  dump();
  console.log(`\n=== ${log.length} frames captured ===`);
  process.exit(code);
}

/**
 * Text visible in captured deltas since index `from` — completion evidence. Assistant/tool text
 * arrives CHUNKED across deltas (the smoke capture split "spike-smoke-ok" mid-token), so the
 * needle is searched in the concatenation, not per-frame.
 */
function sawText(needle, from = 0) {
  const joined = log
    .slice(from)
    .filter((e) => e.type === "stream_delta")
    .map((e) => {
      const d = e.frame.delta ?? {};
      const c = d.content ?? d.tool_return ?? d.text ?? "";
      if (typeof c === "string") return c;
      if (Array.isArray(c)) return c.map((p) => (typeof p === "string" ? p : (p?.text ?? ""))).join("");
      return JSON.stringify(c);
    })
    .join("");
  return joined.includes(needle);
}

function eventSeqReport() {
  const perConn = new Map();
  for (const e of log) {
    if (e.direction !== "in") continue;
    const seq = e.frame.event_seq;
    if (typeof seq !== "number") continue;
    if (!perConn.has(e.conn)) perConn.set(e.conn, []);
    perConn.get(e.conn).push(seq);
  }
  for (const [conn, seqs] of perConn) {
    let monotonic = true;
    for (let i = 1; i < seqs.length; i++) if (seqs[i] <= seqs[i - 1]) monotonic = false;
    console.log(`  event_seq[${conn}]: ${seqs.length} frames, strictly increasing = ${monotonic}`);
  }
}

/**
 * A deterministic long FOREGROUND tool execution. Not `sleep`: the agent-side harness blocks
 * foreground sleep ("Foreground `sleep` is blocked") and the model then improvises with
 * background tasks — nondeterministic. `caffeinate -t N` is quote-free, harmless, and holds
 * EXECUTING_CLIENT_SIDE_TOOL for exactly N seconds.
 */
const LONG_TOOL_TURN = (tag, secs = 25) =>
  `Run this exact shell command with the Bash tool, as a single foreground command: caffeinate -t ${secs}; echo spike-finished-${tag}`;

async function main() {
  // ---- hidden helper: a pure subscriber in its own PROCESS (used by s1proc) ----
  if (scenario === "subscribe-hold") {
    const holdMs = Number(process.env.SPIKE_HOLD_MS ?? 60_000);
    const ws = await connect("Bproc");
    await hello(ws, agentId);
    console.log(`SUBSCRIBE-HOLD: watching ${holdMs}ms`);
    const terminal = await waitTerminal(ws, { agent_id: agentId, conversation_id: "default" }, holdMs, "terminal signal in child");
    const completed = terminal != null && sawText("spike-finished-s1proc");
    console.log(`SUBSCRIBE-HOLD-RESULT: terminal=${terminal?.type ?? "none"} stop=${terminal?.frame?.stop_reason ?? terminal?.stop_reason ?? "-"} completed=${completed}`);
    finish(0);
  }

  if (scenario === "smoke") {
    const ws = await connect("A");
    const { runtime } = await hello(ws, agentId);
    input(ws, runtime, "Reply with exactly: spike-smoke-ok");
    const terminal = await waitTerminal(ws, runtime, 90_000);
    console.log(`\nSMOKE: terminal=${terminal?.type} saw-reply=${sawText("spike-smoke-ok")}`);
    console.log("--- now a Bash tool turn (5s sleep) to prove tool execution on the clone ---");
    input(ws, runtime, LONG_TOOL_TURN("smoke", 5));
    const t2 = await waitTerminal(ws, runtime, 90_000);
    console.log(`\nSMOKE-TOOL: terminal=${t2?.type} saw-tool-output=${sawText("spike-finished-smoke")}`);
    ws.close();
    finish(terminal && t2 ? 0 : 1);
  }

  // ---- S1: the P1 question. A runs a long tool turn, B stays subscribed, A detaches. ----
  if (scenario === "s1") {
    const A = await connect("A");
    const B = await connect("B");
    const { runtime } = await hello(A, agentId);
    await hello(B, agentId);
    console.log("\n--- A starts a 25s tool turn; B is the anchor stand-in ---");
    input(A, runtime, LONG_TOOL_TURN("s1"));
    const executing = await waitFor(
      A,
      (f) => f.type === "update_loop_status" && f.loop_status?.status === "EXECUTING_CLIENT_SIDE_TOOL",
      60_000,
      "the tool to start executing",
    );
    if (!executing) { console.log("NEVER SAW the tool execute — scenario void."); finish(1); }
    console.log("\n--- tool executing; DROPPING A (the submitter) while B stays subscribed ---");
    const before = log.length;
    A.terminate();
    const terminal = await waitTerminal(B, runtime, 60_000, "terminal signal on B");
    const completed = terminal != null && sawText("spike-finished-s1", before);
    console.log(`\nS1 RESULT: terminal-on-B=${terminal?.type ?? "NONE"} completion-output-seen=${completed}`);
    console.log(`S1 ANSWER: ${completed ? "GO — a second subscriber HOLDS a detached turn alive (anchor premise confirmed)" : "NO-GO — the turn did not complete on B; anchor premise fails"}`);
    B.close();
    finish(0);
  }

  // ---- S1proc: same, but the survivor is a separate OS process (the anchor is one). ----
  if (scenario === "s1proc") {
    const child = spawn(process.execPath, [__filename, "subscribe-hold", agentId], {
      env: { ...process.env, SPIKE_HOLD_MS: "70000", CAPTURE_OUT: path.join(CAPTURE_DIR, "controller-spike-s1proc-child.jsonl") },
      stdio: ["ignore", "pipe", "inherit"],
    });
    let childOut = "";
    child.stdout.on("data", (d) => { childOut += d.toString(); process.stdout.write(`[child] ${d}`); });
    await sleep(4000); // let the child subscribe
    const A = await connect("A");
    const { runtime } = await hello(A, agentId);
    console.log("\n--- A starts a 25s tool turn; child process B holds the subscription ---");
    input(A, runtime, LONG_TOOL_TURN("s1proc"));
    const executing = await waitFor(
      A,
      (f) => f.type === "update_loop_status" && f.loop_status?.status === "EXECUTING_CLIENT_SIDE_TOOL",
      60_000,
      "the tool to start executing",
    );
    if (!executing) { console.log("NEVER SAW the tool execute — scenario void."); child.kill(); finish(1); }
    console.log("\n--- DROPPING A; the separate-process subscriber must hold the turn ---");
    A.terminate();
    await new Promise((r) => child.on("exit", r));
    const m = childOut.match(/SUBSCRIBE-HOLD-RESULT: (.*)/);
    console.log(`\nS1PROC RESULT (from child): ${m ? m[1] : "NO RESULT LINE"}`);
    console.log(`S1PROC ANSWER: ${m && m[1].includes("completed=true") ? "GO — separate-process subscriber holds the turn" : "NO-GO or void — see child capture"}`);
    finish(0);
  }

  // ---- S2: late anchor — B subscribes only AFTER the turn started. ----
  if (scenario === "s2") {
    const A = await connect("A");
    const { runtime } = await hello(A, agentId);
    console.log("\n--- A starts a 25s tool turn ALONE ---");
    input(A, runtime, LONG_TOOL_TURN("s2"));
    const executing = await waitFor(
      A,
      (f) => f.type === "update_loop_status" && f.loop_status?.status === "EXECUTING_CLIENT_SIDE_TOOL",
      60_000,
      "the tool to start executing",
    );
    if (!executing) { console.log("NEVER SAW the tool execute — scenario void."); finish(1); }
    console.log("\n--- turn is mid-flight; B subscribes LATE, then A drops ---");
    const B = await connect("B");
    await hello(B, agentId);
    const before = log.length;
    A.terminate();
    const terminal = await waitTerminal(B, runtime, 60_000, "terminal signal on late-B");
    const completed = terminal != null && sawText("spike-finished-s2", before);
    console.log(`\nS2 RESULT: terminal-on-B=${terminal?.type ?? "NONE"} completion-output-seen=${completed}`);
    console.log(`S2 ANSWER: ${completed ? "late subscriber CAN take over a running turn (anchor may attach lazily)" : "late subscription does NOT rescue a turn — anchor must subscribe BEFORE submission"}`);
    B.close();
    finish(0);
  }

  // ---- S3: controller-style local queue on one socket + client_message_id recoverability. ----
  if (scenario === "s3") {
    const ws = await connect("A");
    // A CREATED conversation, not `default`: conversation_messages_list cannot resolve the
    // `default` alias at all ("Agent agent-local-default not found") — a first-class gotcha
    // for C4, demonstrated at the end of this scenario. Real ids (`local-conv-N`) work.
    const { resp, runtime } = await hello(ws, agentId, { create_conversation: { body: {} } });
    const conversationId = resp.conversation?.id ?? runtime.conversation_id;
    console.log(`\n--- resolved conversation: ${conversationId} ---`);
    console.log("--- message 1; submit 2 ONLY on 1's terminality (controller local queue) ---");
    const cm1 = input(ws, runtime, "Reply with exactly: spike-alpha", "cm-s3-1");
    const t1 = await waitTerminal(ws, runtime, 90_000, "turn 1 terminality");
    if (!t1) { console.log("turn 1 never terminal — void"); finish(1); }
    console.log(`--- turn 1 terminal via ${t1.type}; NOW submitting message 2 ---`);
    const cm2 = input(ws, runtime, "Reply with exactly: spike-beta", "cm-s3-2");
    const t2 = await waitTerminal(ws, runtime, 90_000, "turn 2 terminality");
    if (!t2) { console.log("turn 2 never terminal — void"); finish(1); }
    console.log("\n--- transcript check: is client_message_id recoverable from conversation_messages_list? ---");
    const list = await rpc(ws, { type: "conversation_messages_list", conversation_id: conversationId, query: { limit: 50 } }, "conversation_messages_list_response", 30_000);
    const rows = list.messages ?? [];
    console.log(`fetched ${rows.length} transcript messages`);
    const findings = [];
    for (const cm of [cm1, cm2]) {
      const hits = rows.filter((r) => JSON.stringify(r).includes(cm));
      findings.push({ cm, hits: hits.map((h) => ({ id: h.id, message_type: h.message_type, otid: h.otid ?? null, field: h.otid === cm ? "otid" : "elsewhere-in-json" })) });
    }
    const otidNull = rows.filter((r) => r.otid == null).map((r) => r.message_type);
    console.log(`\nS3 MAPPING: ${JSON.stringify(findings, null, 2)}`);
    console.log(`S3 message classes with null otid: ${JSON.stringify([...new Set(otidNull)])}`);
    const recoverable = findings.every((f) => f.hits.length > 0);
    console.log(`S3 ANSWER: serialization clean (t1=${t1.type}, t2=${t2.type}); client_message_id ${recoverable ? "IS recoverable from the transcript" : "is NOT recoverable — C4 reconciliation seam UNBUILDABLE as designed"}`);
    console.log("\n--- the default-alias gotcha, on the record ---");
    const dflt = await rpc(ws, { type: "conversation_messages_list", conversation_id: "default", query: { limit: 5 } }, "conversation_messages_list_response", 15_000);
    console.log(`S3 DEFAULT-ALIAS: success=${dflt.success} error=${JSON.stringify(dflt.error ?? null)} — the controller must reconcile via REAL conversation ids only`);
    ws.close();
    finish(0);
  }

  // ---- S4server: the Q3 hazard — a message queued AT THE SERVER dies with its socket. ----
  if (scenario === "s4server") {
    const A = await connect("A");
    const B = await connect("B");
    const { runtime } = await hello(A, agentId);
    await hello(B, agentId);
    console.log("\n--- A starts a 20s tool turn; B injects behind it (server-side queue) ---");
    input(A, runtime, LONG_TOOL_TURN("s4server", 20));
    await sleep(1500);
    input(B, runtime, "Reply with exactly: spike-s4-server-ran", "cm-s4-server");
    const queued = await waitFor(
      B,
      (f) => f.type === "update_queue" && (f.queue ?? []).some((q) => q.client_message_id === "cm-s4-server"),
      30_000,
      "cm-s4-server to appear in the server queue",
    );
    if (!queued) {
      console.log("\nS4SERVER: message never visibly queued (deferred-ack path?) — recording as-is.");
    } else {
      console.log("\n--- cm-s4-server is queued AT THE SERVER; killing B's socket ---");
      B.terminate();
    }
    const before = log.length;
    await waitTerminal(A, runtime, 60_000, "turn 1 terminality on A");
    console.log("--- turn 1 done; watching 25s: does the server still run cm-s4-server? ---");
    await sleep(25_000);
    const ran = sawText("spike-s4-server-ran", before);
    const removals = log.filter((e) => e.type === "update_queue").flatMap((e) => e.frame.removed ?? []);
    console.log(`\nS4SERVER RESULT: queued=${!!queued} ran-after-owner-death=${ran} removals=${JSON.stringify(removals)}`);
    console.log(`S4SERVER ANSWER: ${ran ? "server-queued message SURVIVED its socket (hazard absent on this build)" : "server-queued message DIED with its socket — Q3 hazard confirmed; controller-local queue is load-bearing"}`);
    A.close();
    finish(0);
  }

  // ---- S4local: same shape, but the second message lives in a CONTROLLER-STYLE local queue. ----
  if (scenario === "s4local") {
    const A = await connect("A");
    const B = await connect("B");
    const { runtime } = await hello(A, agentId);
    await hello(B, agentId);
    console.log("\n--- A starts a 15s tool turn; B HOLDS its message locally (never submits) ---");
    input(A, runtime, LONG_TOOL_TURN("s4local", 15));
    const heldMessage = { text: "Reply with exactly: spike-s4-local-ran", cm: "cm-s4-local" }; // the local queue
    await sleep(1500);
    console.log("--- B dies with the message still local (this is the crash under test) ---");
    B.terminate();
    await waitTerminal(A, runtime, 60_000, "turn 1 terminality");
    console.log("--- B's replacement (B2) comes up, still holding the local queue, and submits ---");
    const B2 = await connect("B2");
    await hello(B2, agentId);
    const before = log.length;
    input(B2, runtime, heldMessage.text, heldMessage.cm);
    const t = await waitTerminal(B2, runtime, 90_000, "held message's turn terminality");
    const ran = t != null && sawText("spike-s4-local-ran", before);
    console.log(`\nS4LOCAL RESULT: submitted-after-recovery=${ran}`);
    console.log(`S4LOCAL ANSWER: ${ran ? "locally-queued message SURVIVES socket death and runs after recovery — closes Q3" : "local queue recovery FAILED — investigate before C4"}`);
    A.close(); B2.close();
    finish(0);
  }

  // ---- S5: external tool registered by A; A dies mid-call; B holds the turn. Then A2 re-registers. ----
  if (scenario === "s5") {
    const TOOL = {
      name: "controller_probe",
      description: "Report a short note to the controller. When the user asks you to call controller_probe, call this tool.",
      parameters: { type: "object", properties: { note: { type: "string" } }, required: ["note"] },
    };
    const A = await connect("A");
    const B = await connect("B");
    const { runtime } = await hello(A, agentId, { external_tools: [{ tools: [TOOL] }] });
    await hello(B, agentId);
    console.log("\n--- A (tool registrar) asks for a controller_probe call; B is the anchor ---");
    input(A, runtime, "Call the controller_probe tool with note set to 'first'. You MUST use the tool.");
    const call = await waitFor(A, (f) => f.type === "external_tool_call_request", 90_000, "external_tool_call_request on A");
    if (!call) {
      console.log("\nS5: the model never called the external tool — scenario void (check smoke/tooling).");
      finish(1);
    }
    console.log("\n--- tool call in flight; KILLING A (registrar + submitter) without responding ---");
    const before = log.length;
    A.terminate();
    console.log("--- watching B 60s: fate of the orphaned in-flight tool call ---");
    const terminal = await waitTerminal(B, runtime, 60_000, "any terminal signal on B");
    const statuses = [...new Set(log.slice(before).filter((e) => e.type === "update_loop_status").map((e) => e.frame.loop_status?.status))];
    console.log(`\nS5 ORPHAN FATE: terminal=${terminal ? `${terminal.type} (stop=${terminal.frame?.stop_reason ?? terminal.stop_reason ?? "-"})` : "NONE within 60s (hang)"} statuses-seen=${JSON.stringify(statuses)}`);
    console.log("\n--- A2 reconnects and RE-REGISTERS the tool; can a fresh call succeed? ---");
    const A2 = await connect("A2");
    await hello(A2, agentId, { external_tools: [{ tools: [TOOL] }] });
    const before2 = log.length;
    input(A2, runtime, "Call the controller_probe tool again, with note set to 'second'. You MUST use the tool.");
    const call2 = await waitFor(A2, (f) => f.type === "external_tool_call_request", 90_000, "external_tool_call_request on A2");
    if (call2) {
      send(A2, { type: "external_tool_call_response", request_id: call2.request_id, result: { content: [{ type: "text", text: "controller ack: second" }] } });
      const t2 = await waitTerminal(A2, runtime, 60_000, "post-re-registration turn terminality");
      console.log(`\nS5 RE-REGISTRATION: call-arrived=${!!call2} turn-completed=${t2 != null}`);
    } else {
      console.log(`\nS5 RE-REGISTRATION: no tool call arrived after re-registration (${log.length - before2} frames) — record and investigate`);
    }
    console.log("S5 ANSWER: see ORPHAN FATE + RE-REGISTRATION above — shapes C3's reconnect contract and C4's FAILED-VISIBLE marking.");
    B.close(); A2.close();
    finish(0);
  }

  // ---- S6: two runtimes on ONE socket — per-runtime or per-socket serialization? ----
  if (scenario === "s6" || scenario === "s6b") {
    const ws = await connect("A");
    let r1, r2;
    if (scenario === "s6") {
      ({ runtime: r1 } = await hello(ws, agentId));
      const h2 = await hello(ws, agentId, { create_conversation: { body: {} } });
      r2 = h2.runtime;
      console.log(`\n--- one agent, two conversations: ${r1.conversation_id} vs ${r2.conversation_id} ---`);
    } else {
      if (!agentId2) { console.error("s6b needs a second agent id"); process.exit(2); }
      ({ runtime: r1 } = await hello(ws, agentId));
      ({ runtime: r2 } = await hello(ws, agentId2));
      console.log(`\n--- two agents on one socket: ${r1.agent_id} vs ${r2.agent_id} ---`);
    }
    console.log("--- back-to-back 15s tool turns into BOTH runtimes on the ONE socket ---");
    const tSubmit = Date.now();
    input(ws, r1, LONG_TOOL_TURN(`${scenario}-r1`, 15), `cm-${scenario}-r1`);
    input(ws, r2, LONG_TOOL_TURN(`${scenario}-r2`, 15), `cm-${scenario}-r2`);
    const acks = [];
    await waitFor(ws, (f) => { if (f.type === "input_accepted") acks.push({ ms: Date.now() - tSubmit, req: f.request_id, disposition: f.disposition, accepted: f.accepted }); return acks.length >= 2; }, 45_000, "both input acks");
    const term1 = waitTerminal(ws, r1, 120_000, "runtime 1 terminality");
    const term2 = waitTerminal(ws, r2, 120_000, "runtime 2 terminality");
    const [t1, t2] = await Promise.all([term1, term2]);
    // tool_return_message only — the user_message echo of the prompt also contains the marker,
    // and matching it once produced a bogus "completed in 1.3s" stamp for a 15s sleep.
    const toolDone = (tag) =>
      log.find(
        (e) =>
          e.type === "stream_delta" &&
          e.frame.delta?.message_type === "tool_return_message" &&
          JSON.stringify(e.frame.delta.tool_return ?? "").includes(tag),
      );
    const done1 = toolDone(`spike-finished-${scenario}-r1`);
    const done2 = toolDone(`spike-finished-${scenario}-r2`);
    console.log(`\n${scenario.toUpperCase()} ACKS: ${JSON.stringify(acks)}`);
    console.log(`completion stamps: r1@${done1?.ms ?? "-"}ms r2@${done2?.ms ?? "-"}ms (both submitted @0; 15s sleeps)`);
    console.log("event_seq integrity on the shared socket:");
    eventSeqReport();
    const concurrent = done1 && done2 && Math.abs(done1.ms - done2.ms) < 10_000;
    console.log(`\n${scenario.toUpperCase()} ANSWER: ${acks.length >= 2 && acks.every((a) => a.disposition === "started") && concurrent
      ? "both runtimes ran CONCURRENTLY on one socket — serialization is PER-RUNTIME (no sharding needed)"
      : concurrent
        ? "turns overlapped but acks were deferred/queued — inspect capture before deciding sharding"
        : "turns were SERIALIZED across runtimes on one socket — head-of-line blocking is real; decide sharding before C3"}`);
    console.log(`terminality: r1=${t1?.type ?? "none"} r2=${t2?.type ?? "none"}`);
    ws.close();
    finish(0);
  }

  console.error(`unknown scenario: ${scenario}`);
  process.exit(2);
}

main().catch((e) => {
  console.error(e);
  dump();
  process.exit(1);
});
