/**
 * OPT-IN live contract check against a real App Server. THIS IS THE UPGRADE GATE.
 *
 * Skipped by default so the suite is deterministic and offline. Run it explicitly whenever
 * the `letta` binary moves, pointing it at a CANDIDATE server started on a CLONE backend
 * (never a second writer on the live one — R1):
 *
 *   LETTA_LIVE_WS=1 npx vitest run test/live.contract.test.ts                 # live :4577
 *   LETTA_LIVE_WS=1 LETTA_LIVE_WS_URL=ws://127.0.0.1:4599/ws \
 *     LETTA_LIVE_WS_EXPECT_VERSION=0.30.20 npx vitest run test/live.contract.test.ts
 *
 * Uses ONLY the low-stakes docs agent + `default` conversation + a benign no-tool prompt,
 * loopback — never MC or another agent. Every op is bounded; it cannot hang the suite.
 */

import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ContinuityCore } from "../src/index.js";
import { writePointer } from "../src/pointer.js";
import {
  type AppServerInfoResponseFrame,
  type ConversationCreateResponseFrame,
  type ConversationListResponseFrame,
  type MessagesListResponseFrame,
  Outbound,
  PINNED_PROTOCOL_VERSION,
  PINNED_SERVER_VERSION,
  REQUIRED_CAPABILITIES,
  type ServerFrame,
  buildAppServerInfo,
  buildConversationCreate,
  buildConversationList,
  buildConversationMessagesList,
  buildInput,
  buildRuntimeStart,
  isStreamDelta,
  isTurnFinished,
} from "../src/protocol.js";
import { WsConnection } from "../src/ws.js";

const LIVE = process.env.LETTA_LIVE_WS === "1";
const URL = process.env.LETTA_LIVE_WS_URL ?? "ws://127.0.0.1:4577/ws";
/** The version this run EXPECTS to find — defaults to the pin, override when vetting an upgrade. */
const EXPECT_VERSION = process.env.LETTA_LIVE_WS_EXPECT_VERSION ?? PINNED_SERVER_VERSION;
/**
 * Which agent to gate against. Defaults to the low-stakes docs agent, overridable because the
 * gate is about the SERVER's protocol contract and a hard-coded agent makes an unrelated fault
 * look like protocol drift.
 *
 * That is not hypothetical: on 2026-08-14 the docs agent's model group (`deepseek-v4-flash`)
 * began answering 404 at the provider — "Model not found, inaccessible, and/or not deployed" —
 * so every turn on it ends `stop_reason: "error"` and three of the four checks below fail with
 * nothing wrong at the protocol layer at all. Point this at any low-stakes agent on a working
 * model to gate the server; a disposable one can be minted over this same socket with
 * `agent_create`.
 */
const DOCS_AGENT = "agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a";
const AGENT = process.env.LETTA_LIVE_WS_AGENT ?? DOCS_AGENT;
const RUNTIME = { agent_id: AGENT, conversation_id: "default" };

describe.skipIf(!LIVE)(`live contract (opt-in, ${URL}, agent ${AGENT})`, () => {
  it("app_server_info reports the expected version, protocol, and required capabilities", async () => {
    const ws = new WsConnection({
      url: URL,
      runtime: RUNTIME,
      // Assert the reported identity below rather than failing the connect, so a drifted
      // server produces a readable diff instead of an opaque connect error.
      pinnedVersion: EXPECT_VERSION,
      versionPolicy: "warn",
      openTimeoutMs: 8000,
    });
    try {
      await ws.connect();
      // The gate ran during connect and recorded what it saw.
      expect(ws.identity?.actual).toBe(EXPECT_VERSION);
      expect(ws.identity?.protocolVersion).toBe(PINNED_PROTOCOL_VERSION);
      expect(ws.identity?.missingCapabilities).toEqual([]);

      // Re-issue the RPC to assert the full capability map, not just the required subset.
      const info = await ws.request<AppServerInfoResponseFrame>(
        buildAppServerInfo,
        Outbound.appServerInfo,
        8000,
      );
      expect(info.success).toBe(true);
      for (const cap of REQUIRED_CAPABILITIES) {
        expect(info.capabilities?.[cap]).toBe(true);
      }
    } finally {
      ws.close();
    }
  }, 30000);

  it("conversation_list + conversation_create + a benign streamed turn round-trip the pinned frames", async () => {
    const ws = new WsConnection({
      url: URL,
      runtime: RUNTIME,
      pinnedVersion: EXPECT_VERSION,
      versionPolicy: "warn",
      openTimeoutMs: 8000,
      helloTimeoutMs: 10000,
      rpcTimeoutMs: 10000,
    });
    const frames: ServerFrame[] = [];
    const protocolErrors: Error[] = [];
    ws.onFrame((f) => frames.push(f));
    // Without this the gate passes while the client silently DISCARDS a frame per turn — which is
    // exactly what happened before the id-less `stop_reason` delta was allowlisted.
    ws.onError((e) => protocolErrors.push(e));
    try {
      const hello = await ws.connect();
      expect(hello.success).toBe(true);

      const list = await ws.request<ConversationListResponseFrame>(
        (rid) => buildConversationList(rid, AGENT),
        Outbound.conversationList,
      );
      expect(Array.isArray(list.conversations)).toBe(true);

      // Mint a scratch conversation rather than assuming `default` exists — a clone-backend
      // candidate server has none, and Unit 8's cutover depends on this exact RPC working.
      // A guard-failing envelope is dropped silently, so this also proves the envelope.
      const created = await ws.request<ConversationCreateResponseFrame>(
        (rid) => buildConversationCreate(rid, AGENT, "contract-gate"),
        Outbound.conversationCreate,
      );
      expect(created.success).toBe(true);
      const convId = created.conversation?.id;
      expect(typeof convId).toBe("string");
      if (typeof convId !== "string") throw new Error("no conversation id");

      // Re-home this connection's runtime onto the scratch conversation before injecting.
      const rt = { agent_id: AGENT, conversation_id: convId };
      const hello2 = await ws.request<ServerFrame>(
        (rid) => buildRuntimeStart(rid, rt),
        Outbound.runtimeStart,
      );
      expect(hello2.success).toBe(true);

      const done = new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("no turn_finished within 60s")), 60000);
        ws.onFrame((f) => {
          if (isTurnFinished(f)) {
            clearTimeout(timer);
            resolve();
          }
        });
      });
      ws.send(
        buildInput(rt, "Reply with exactly: OK. No tools.", {
          requestId: "live-input-1",
          clientMessageId: "live-cm-1",
        }),
      );
      await done;

      expect(frames.some((f) => isStreamDelta(f))).toBe(true);
      const finished = frames.filter((f) => isTurnFinished(f));
      expect(finished.length).toBeGreaterThan(0);
      // A turn that errored out still emits turn_finished — assert it actually succeeded,
      // otherwise a broken candidate server passes the gate on shape alone.
      expect(finished.at(-1)?.stop_reason).not.toBe("error");

      // Exercise the reconnect path's RPC live. Its envelope had never been proven against a real
      // server, and its failure mode is silent (a guard-failing frame is dropped, so the client
      // just times out and resumes with no dedup).
      const snapshot = await ws.request<MessagesListResponseFrame>(
        (rid) => buildConversationMessagesList(rid, rt),
        Outbound.conversationMessagesList,
      );
      expect(snapshot.success).toBe(true);
      expect(Array.isArray(snapshot.messages)).toBe(true);
      expect(snapshot.messages.length).toBeGreaterThan(0);

      // PINS THE ANSWER to M1 Unit 7's open premise. Snapshot ids and live per-chunk delta ids
      // come from different namespaces (ui-msg-* vs letta-msg-*), so LiveDedup — which compares
      // them directly — can never match on a real server. Asserted rather than described so the
      // day it stops being true, this fails and Unit 7 is told.
      const liveIds = new Set(
        frames
          .filter(isStreamDelta)
          .map((f) => f.delta.id)
          .filter((id): id is string => !!id),
      );
      const snapshotIds = new Set(
        snapshot.messages.map((m) => (m as { id?: string }).id).filter((id): id is string => !!id),
      );
      const overlap = [...liveIds].filter((id) => snapshotIds.has(id));
      expect(liveIds.size).toBeGreaterThan(0);
      expect(snapshotIds.size).toBeGreaterThan(0);
      expect(overlap).toEqual([]);

      // No frame was discarded during a complete, healthy turn.
      expect(protocolErrors.map((e) => e.message)).toEqual([]);
    } finally {
      ws.close();
    }
  }, 90000);

  it("the runtime's permission mode is still the one the approval preconditions assume", async () => {
    // Leg 1b of the approval policy (docs/runbooks/continuity-conversation-preconditions.md).
    // The client cannot control permission mode, so it verifies it instead: under `unrestricted`
    // no permission-gated `can_use_tool` approval fires on the shared conversation. If this ever
    // changes, the client's approval responder becomes load-bearing rather than a backstop, and
    // that should surface as a failing check rather than as a hung conversation.
    const ws = new WsConnection({ url: URL, runtime: RUNTIME, versionPolicy: "warn" });
    const modes: string[] = [];
    ws.onFrame((f) => {
      const status = (f as { device_status?: { current_permission_mode?: string } }).device_status;
      if (f.type === "update_device_status" && status?.current_permission_mode) {
        modes.push(status.current_permission_mode);
      }
    });
    try {
      await ws.connect();
      const deadline = Date.now() + 10_000;
      while (Date.now() < deadline && modes.length === 0) {
        await new Promise((r) => setTimeout(r, 100));
      }
      expect(modes.length).toBeGreaterThan(0);
      expect(modes[0]).toBe("unrestricted");
    } finally {
      ws.close();
    }
  }, 30000);

  /**
   * End-to-end proof of run-ownership correlation (followup finding #1) against the real
   * server: two peers on ONE conversation both inject at once. The server serializes them,
   * and each core must claim exactly its own run — one via the `started` ack, the other via
   * its own `client_message_id` being `dequeued`.
   */
  it("two peers on one conversation each own exactly their own run", async () => {
    const seed = new WsConnection({ url: URL, runtime: RUNTIME, versionPolicy: "warn" });
    let convId: string;
    try {
      await seed.connect();
      const created = await seed.request<ConversationCreateResponseFrame>(
        (rid) => buildConversationCreate(rid, AGENT, "ownership-gate"),
        Outbound.conversationCreate,
      );
      if (!created.conversation?.id) throw new Error("no conversation id");
      convId = created.conversation.id;
    } finally {
      seed.close();
    }

    const dir = await mkdtemp(join(tmpdir(), "continuity-live-"));
    const cores: ContinuityCore[] = [];
    for (const name of ["a", "b"]) {
      const path = join(dir, `${name}.json`);
      await writePointer(path, { agentId: AGENT, conversationId: convId, label: name });
      cores.push(new ContinuityCore({ pointerPath: path, url: URL, versionPolicy: "warn" }));
    }
    const [a, b] = cores as [ContinuityCore, ContinuityCore];
    /**
     * Sampled AT turn_start, not polled.
     *
     * Ownership is released the moment the runtime reports itself idle, which on a fast model is
     * inside a single poll interval — so an interval sampler is a race, and it duly failed one run
     * in three while the property it was checking held perfectly. Every comment in ownership.ts
     * says to ask at turn_start and remember the answer; this test was the one place that did not.
     */
    const seenA = new Set<string>();
    const seenB = new Set<string>();
    const finishedRuns = new Set<string>();
    try {
      await a.start();
      await b.start();
      for (const [core, seen] of [
        [a, seenA],
        [b, seenB],
      ] as const) {
        core.onRender((e) => {
          if (e.type === "turn_start" && e.runId && core.ownsRun(e.runId)) seen.add(e.runId);
          if (e.type === "turn_finished" && e.runId) finishedRuns.add(e.runId);
        });
      }

      a.send("Reply with exactly: AAA. No tools.");
      b.send("Reply with exactly: BBB. No tools.");

      const deadline = Date.now() + 120_000;
      while (Date.now() < deadline && finishedRuns.size < 2) {
        await new Promise((r) => setTimeout(r, 100));
      }

      expect(finishedRuns.size).toBe(2); // the server serialized two distinct runs
      expect([...seenA]).toHaveLength(1);
      expect([...seenB]).toHaveLength(1);
      // The whole point: disjoint attribution — neither peer claimed the other's run. This also
      // pins the DEQUEUE ORDERING the offline suite cannot decide: b was queued behind a, so b
      // owning its own run means the dequeue notice arrived before the run it announced.
      expect([...seenA][0]).not.toBe([...seenB][0]);
      expect(a.ownershipSnapshot().degraded).toBe(false);
      expect(b.ownershipSnapshot().degraded).toBe(false);
    } finally {
      for (const c of cores) c.stop();
    }
  }, 150000);
});
