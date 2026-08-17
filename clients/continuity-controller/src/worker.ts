/**
 * worker.ts — the feature-rich half of the controller: journaled subscriptions, registry
 * authority, and the forward-progress liveness probe.
 *
 * C3 scope: hold the worker's half of the dual subscription (with `wait_for_replay`), keep the
 * registry honest (broken rows visible, never skipped silently), and prove liveness by a
 * bounded `sync` round-trip — a bare endpoint ping stays flat during a stall (spike §C), so
 * liveness is an RPC the runtime must actually answer. A probe miss BOUNCES the connection;
 * the liveness file simply goes stale while unhealthy, which is exactly the signal the plist
 * watchdog consumes. Turn submission (C4) and the surface API (C5) build on this class.
 */

import { mkdirSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { DatabaseSync } from "node:sqlite";
import type { ReconnectPolicy } from "@ai-pa/letta-continuity-core/connection";
import {
  type AgentRetrieveResponseFrame,
  type ListModelsResponseFrame,
  Outbound,
  type UpdateModelResponseFrame,
  buildAgentRetrieve,
  buildAgentUpdate,
  buildAppServerInfo,
  buildListModels,
  buildSync,
  buildUpdateModel,
} from "@ai-pa/letta-continuity-core/protocol";
import type { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import { ApprovalArbiter } from "./approvals.js";
import { ConnectionLoop } from "./connection-loop.js";
import { subscribeRuntimes } from "./hotset.js";
import { IngressServer } from "./ingress/scheduler.js";
import { TurnJournal } from "./journal.js";
import type { Registry, RuntimeRef } from "./registry.js";
import { AwarenessManager } from "./routing/awareness.js";
import { DigestManager } from "./routing/digest.js";
import { RouteTable } from "./routing/routes.js";
import type { Journal } from "./state/journal.js";
import { ensureSurfaceToken } from "./surface/auth.js";
import { SurfaceServer } from "./surface/server.js";
import { TurnPipeline } from "./turns.js";

export interface WorkerOptions {
  url: string;
  db: DatabaseSync;
  registry: Registry;
  journal: Journal;
  livenessFile: string;
  livenessIntervalMs: number;
  livenessDeadlineMs: number;
  hotsetPollMs: number;
  /** How often the pipeline sweeps for externally-enqueued (CLI/ingress) queue rows. */
  queuePollMs: number;
  /** Wall-clock backstop per turn (C4). */
  turnTimeoutMs: number;
  /** Bound on the abort round-trip before a wedged turn bounces the connection. */
  abortConfirmMs: number;
  /** Degradation report from openStateDb — carried into journal + liveness, never dropped. */
  degraded: string | null;
  /**
   * Loopback surface-API port (C5). Undefined = surface disabled; 0 = ephemeral (tests).
   * Requires `stateDir` for the token file.
   */
  surfacePort?: number;
  stateDir?: string;
  /** Permission mode stamped on runtime_start (P5's flipped-clone scenario sets `standard`). */
  runtimeMode?: string;
  /** Scheduler-dialect ingress port (C7). Undefined = disabled; 0 = ephemeral (tests). */
  ingressPort?: number;
  /** Shared ingress secret — REQUIRED when ingressPort is set (Docker-wide reachability). */
  ingressSecret?: string;
  /** Digest delivery sweep cadence (C8). Only the cadence is tunable; the design is fixed. */
  digestSweepMs?: number;
  onWarn?: (msg: string) => void;
  onExhausted: () => void;
  reconnect?: ReconnectPolicy;
  makeConnection?: (url: string, onWarn: (msg: string) => void) => WsConnection;
}

const key = (r: RuntimeRef): string => `${r.agent_id}:${r.conversation_id}`;

/**
 * The C7 agent-facing awareness lever, registered on EVERY hot runtime's hello so a worker
 * reconnect re-registers it by construction. Uncapped per the documented-risk decision
 * 2026-08-15 (journal audit only).
 */
const NOTIFY_OPERATOR_TOOL = {
  name: "notify_operator",
  description:
    "Set how the operator is notified about this conversation's current activity: " +
    "'interrupt' (raise attention on their focused surface), 'badge' (default), or 'muted' " +
    "(deliberately silent). Use sparingly; 'interrupt' should mean it cannot wait.",
  parameters: {
    type: "object",
    properties: {
      level: { type: "string", enum: ["interrupt", "badge", "muted"] },
      note: { type: "string", description: "Optional short reason, journaled" },
    },
    required: ["level"],
  },
};

/** Kinara's route-authoring lever (R25). Journal audit only — documented-risk posture. */
const MANAGE_ROUTES_TOOL = {
  name: "manage_routes",
  description:
    "Manage the controller's direct-lane routes: set/delete an @alias pointing at a " +
    "registry-known specialist, or list current routes. Every mutation is journaled with " +
    "you as the author.",
  parameters: {
    type: "object",
    properties: {
      op: { type: "string", enum: ["set", "delete", "list"] },
      alias: { type: "string" },
      agent_id: { type: "string" },
      conversation_id: { type: "string" },
    },
    required: ["op"],
  },
};

export class WorkerDaemon {
  private readonly loop: ConnectionLoop;
  /** The C4 sole-submitter pipeline. Public: ingress adapters and tests accept through it. */
  readonly pipeline: TurnPipeline;
  /** The C5 approval arbitration layer. */
  readonly approvals: ApprovalArbiter;
  /** The C5 surface boundary; null until start() when surfacePort is set. */
  surface: SurfaceServer | null = null;
  /** Bound surface port after start (differs from surfacePort when 0/ephemeral). */
  surfaceBoundPort: number | null = null;
  /** The C7 awareness/unseen layer. */
  readonly awareness: AwarenessManager;
  /** The C8 direct-lane route table. */
  readonly routes: RouteTable;
  /** The C8 Kinara digest queue. */
  readonly digests: DigestManager;
  /** The scheduler-dialect ingress; null until start() when ingressPort is set. */
  ingress: IngressServer | null = null;
  ingressBoundPort: number | null = null;
  private readonly turnJournal: TurnJournal;
  private livenessTimer: ReturnType<typeof setInterval> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private queueTimer: ReturnType<typeof setInterval> | null = null;
  private digestTimer: ReturnType<typeof setInterval> | null = null;
  private subscribedKeys = new Set<string>();
  private seenHotsetVersion = -1;
  private passInFlight = false;
  private probeInFlight = false;

  constructor(private readonly opts: WorkerOptions) {
    this.turnJournal = new TurnJournal(opts.db);
    this.pipeline = new TurnPipeline({
      db: opts.db,
      journal: this.turnJournal,
      getConnection: () => this.loop.current,
      isSubscribed: (runtime) => this.subscribedKeys.has(key(runtime)),
      turnTimeoutMs: opts.turnTimeoutMs,
      abortConfirmMs: opts.abortConfirmMs,
      onWarn: opts.onWarn,
      onWedged: (runtime, detail) => {
        // An unconfirmed abort means the server may still be running the turn: bounce, and let
        // recovery reconcile its true fate from the transcript.
        this.loop.bounce(`wedged turn on ${key(runtime)}: ${detail}`);
      },
    });
    this.loop = new ConnectionLoop({
      url: opts.url,
      onWarn: opts.onWarn,
      onExhausted: opts.onExhausted,
      reconnect: opts.reconnect,
      makeConnection: opts.makeConnection,
      onConnected: async (conn) => {
        // New connection = new journal generation, opened BEFORE any of its frames can be
        // journaled (the replay arrives during subscription, not after recover()).
        this.pipeline.beginGeneration();
        this.approvals.onReconnect();
        // Frames flow into the pipeline from the FIRST hello: the wait_for_replay replay is
        // where a mid-flight turn's history arrives, and it must not be dropped on the floor.
        conn.onFrame((frame) => {
          if (frame.type === "external_tool_call_request") {
            this.onExternalToolCall(conn, frame as Record<string, unknown>);
            return;
          }
          if (this.approvals.onFrame(frame)) return;
          this.pipeline.onFrame(frame);
        });
        this.subscribedKeys = new Set();
        await this.subscribePass(conn, "connect");
        this.opts.journal.append("worker_connected", {
          url: this.opts.url,
          subscribed: [...this.subscribedKeys],
        });
        // Replay is complete (subscriptions resolved with wait_for_replay) — reconcile every
        // non-terminal queue row against transcript truth, then resume submissions.
        await this.pipeline.recover(conn);
      },
    });
    this.routes = new RouteTable(opts.db, opts.registry, this.turnJournal);
    this.digests = new DigestManager({
      db: opts.db,
      journal: this.turnJournal,
      pipeline: this.pipeline,
      onWarn: opts.onWarn,
    });
    // A COMPLETED direct-lane exchange becomes a digest row for its route-origin Kinara
    // thread (R24). Item id = the exchange's client_message_id — the same id R12's inline
    // card carried, which is what lets Kinara dedupe.
    this.turnJournal.onRecord((row) => {
      if (row.kind !== "turn_terminal" || !row.client_message_id) return;
      const queueRow = this.pipeline.rowFor(row.client_message_id);
      const origin = queueRow?.origin as { via?: string; origin_runtime?: RuntimeRef } | undefined;
      if (origin?.via !== "direct" || !origin.origin_runtime) return;
      const replyText = this.turnJournal
        .eventsFor({ agent_id: row.agent_id, conversation_id: row.conversation_id })
        .filter(
          (e) => e.client_message_id === row.client_message_id && e.kind === "assistant_message",
        )
        .map((e) => {
          const delta = (e.payload as { delta?: { content?: unknown } }).delta;
          const content = delta?.content;
          if (typeof content === "string") return content;
          if (Array.isArray(content))
            return content
              .map((c) => (typeof c === "string" ? c : ((c as { text?: string }).text ?? "")))
              .join("");
          return "";
        })
        .join("")
        .slice(0, 300);
      this.digests.enqueue(
        origin.origin_runtime,
        row.client_message_id,
        `@${row.agent_id}: ${queueRow?.content.slice(0, 120) ?? ""} → ${replyText || "(no text reply)"}`,
      );
    });
    this.awareness = new AwarenessManager({
      db: opts.db,
      journal: this.turnJournal,
      broadcast: (runtime, level, ref) =>
        this.surface?.broadcastAwareness(runtime, level, ref) ?? 0,
      onWarn: opts.onWarn,
    });
    this.approvals = new ApprovalArbiter({
      db: opts.db,
      journal: this.turnJournal,
      getConnection: () => this.loop.current,
      broadcast: (approval) => this.surface?.broadcastApproval(approval) ?? 0,
      broadcastResolution: (id, decision, by) =>
        this.surface?.broadcastApprovalResolution(id, decision, by),
      onWarn: opts.onWarn,
    });
  }

  get state(): string {
    return this.loop.state;
  }

  get held(): string[] {
    return [...this.subscribedKeys];
  }

  async start(): Promise<void> {
    if (this.opts.degraded) {
      // The visible half of the db degrade protocol: an operator reading either the journal or
      // the liveness file sees that the authority was rebuilt, before anything else happens.
      this.opts.journal.append("state_db_degraded", { detail: this.opts.degraded });
      this.opts.onWarn?.(`STATE DB DEGRADED: ${this.opts.degraded}`);
    }
    this.opts.journal.append("worker_boot", {});
    if (this.opts.surfacePort !== undefined) {
      if (!this.opts.stateDir) throw new Error("surfacePort requires stateDir (token home)");
      const token = ensureSurfaceToken(this.opts.stateDir);
      this.surface = new SurfaceServer({
        token,
        journal: this.turnJournal,
        pipeline: this.pipeline,
        approvals: this.approvals,
        awareness: this.awareness,
        routes: this.routes,
        onWarn: this.opts.onWarn,
        // Read-only agent-record lookup for the web slice's model footer, on the
        // worker's OWN connection (the sole client — no side channel to :4577).
        agentInfo: async (agentId: string) => {
          const conn = this.loop.current;
          if (!conn) throw new Error("app server connection down");
          const resp = await conn.request<AgentRetrieveResponseFrame>(
            (rid) => buildAgentRetrieve(rid, agentId),
            Outbound.agentRetrieve,
          );
          if (!resp.success || !resp.agent) throw new Error(resp.error ?? "agent_retrieve failed");
          return resp.agent;
        },
        // /model support for the web slice: enumerate what the provider config (litellm
        // harness included) can reach, and switch the LIVE runtime via update_model.
        listModels: async () => {
          const conn = this.loop.current;
          if (!conn) throw new Error("app server connection down");
          const resp = await conn.request<ListModelsResponseFrame>(
            buildListModels,
            Outbound.listModels,
          );
          if (!resp.success) throw new Error(resp.error ?? "list_models failed");
          return { entries: resp.entries ?? [], available_handles: resp.available_handles ?? [] };
        },
        setModel: async (runtime: RuntimeRef, modelIdentifier: string) => {
          const conn = this.loop.current;
          if (!conn) throw new Error("app server connection down");
          // update_model is a PER-RUNTIME override (verified live: the agent record keeps
          // its old model) — live effect now, then agent_update persists the record so a
          // runtime restart keeps the choice and agent-info/footer stay truthful.
          const resp = await conn.request<UpdateModelResponseFrame>(
            (rid) => buildUpdateModel(rid, runtime, modelIdentifier),
            Outbound.updateModel,
          );
          if (!resp.success) throw new Error(resp.error ?? "update_model failed");
          const handle = resp.model_handle ?? modelIdentifier;
          const persisted = await conn.request<AgentRetrieveResponseFrame>(
            (rid) => buildAgentUpdate(rid, runtime.agent_id, { model: handle }),
            Outbound.agentUpdate,
          );
          if (!persisted.success)
            throw new Error(
              `live switch applied but persisting failed: ${persisted.error ?? "agent_update failed"}`,
            );
          return handle;
        },
      });
      this.surfaceBoundPort = await this.surface.start(this.opts.surfacePort);
    }
    if (this.opts.ingressPort !== undefined) {
      this.ingress = new IngressServer({
        secret: this.opts.ingressSecret ?? "",
        registry: this.opts.registry,
        pipeline: this.pipeline,
        journal: this.turnJournal,
        awareness: this.awareness,
        onWarn: this.opts.onWarn,
      });
      this.ingressBoundPort = await this.ingress.start(this.opts.ingressPort);
    }
    await this.loop.start();
    this.livenessTimer = setInterval(() => void this.livenessProbe(), this.opts.livenessIntervalMs);
    this.livenessTimer.unref?.();
    this.pollTimer = setInterval(() => void this.pollHotset(), this.opts.hotsetPollMs);
    this.pollTimer.unref?.();
    // Sweep for queue rows enqueued by OTHER processes (CLI, ingress) — in-process accepts
    // pump immediately; this poll is the seam that makes the durable queue multi-writer.
    this.queueTimer = setInterval(() => this.pipeline.pump(), this.opts.queuePollMs);
    this.queueTimer.unref?.();
    this.digestTimer = setInterval(() => this.digests.sweep(), this.opts.digestSweepMs ?? 30_000);
    this.digestTimer.unref?.();
    // Prove liveness immediately rather than an interval from now — a daemon that boots and
    // dies inside the first interval would otherwise leave no liveness evidence at all.
    await this.livenessProbe();
  }

  stop(): void {
    if (this.livenessTimer) clearInterval(this.livenessTimer);
    if (this.pollTimer) clearInterval(this.pollTimer);
    if (this.queueTimer) clearInterval(this.queueTimer);
    if (this.digestTimer) clearInterval(this.digestTimer);
    this.livenessTimer = null;
    this.pollTimer = null;
    this.queueTimer = null;
    this.digestTimer = null;
    this.pipeline.stop();
    void this.surface?.stop();
    this.surface = null;
    void this.ingress?.stop();
    this.ingress = null;
    this.loop.stop();
  }

  /** Controller-owned external tools. notify_operator is the only one until C8. */
  private onExternalToolCall(conn: WsConnection, frame: Record<string, unknown>): void {
    const requestId = frame.request_id as string;
    const runtime = frame.runtime as RuntimeRef | undefined;
    const ack = (result: string, isError = false): void => {
      conn.send({
        type: "external_tool_call_response",
        request_id: requestId,
        result: { content: [{ type: "text", text: result }], is_error: isError },
      } as unknown as Parameters<WsConnection["send"]>[0]);
    };
    if (frame.tool_name === "manage_routes" && runtime) {
      const input =
        (frame.input as
          | { op?: string; alias?: string; agent_id?: string; conversation_id?: string }
          | undefined) ?? {};
      const author = `agent:${runtime.agent_id}`;
      try {
        if (input.op === "list") {
          ack(JSON.stringify(this.routes.list()));
        } else if (input.op === "set" && input.alias && input.agent_id) {
          const route = this.routes.set(input.alias, input.agent_id, input.conversation_id, author);
          ack(`route @${route.alias} → ${route.agent_id}/${route.conversation_id}`);
        } else if (input.op === "delete" && input.alias) {
          ack(
            this.routes.delete(input.alias, author)
              ? `route @${input.alias} deleted`
              : `no route @${input.alias}`,
          );
        } else {
          ack("manage_routes: op=set requires alias+agent_id; op=delete requires alias", true);
        }
      } catch (e) {
        ack(e instanceof Error ? e.message : String(e), true);
      }
      return;
    }
    if (frame.tool_name === "notify_operator" && runtime) {
      const input = (frame.input as { level?: string; note?: string } | undefined) ?? {};
      const ok = this.awareness.setDirective(runtime, input.level ?? "");
      ack(
        ok
          ? `awareness set to ${input.level}`
          : `unknown level "${input.level ?? ""}" — use interrupt | badge | muted`,
        !ok,
      );
      return;
    }
    ack(`unknown controller tool: ${String(frame.tool_name)}`, true);
  }

  private async pollHotset(): Promise<void> {
    const conn = this.loop.current;
    if (!conn) return;
    if (this.opts.registry.hotsetVersion() === this.seenHotsetVersion) return;
    await this.subscribePass(conn, "hotset_change");
  }

  private async subscribePass(conn: WsConnection, cause: string): Promise<void> {
    if (this.passInFlight) return;
    this.passInFlight = true;
    try {
      const version = this.opts.registry.hotsetVersion();
      const rows = this.opts.registry.hotRows();
      const fresh = rows.filter((r) => !this.subscribedKeys.has(key(r)));
      if (fresh.length > 0) {
        const report = await subscribeRuntimes(conn, fresh, {
          waitForReplay: true,
          mode: this.opts.runtimeMode,
          externalTools: [{ tools: [NOTIFY_OPERATOR_TOOL, MANAGE_ROUTES_TOOL] }],
        });
        for (const r of report.subscribed) this.subscribedKeys.add(key(r));
        for (const b of report.broken) {
          this.opts.registry.markBroken(b.runtime, b.reason);
          this.opts.journal.append("registry_row_broken", {
            runtime: b.runtime,
            reason: b.reason,
          });
          this.opts.onWarn?.(`registry row BROKEN: ${key(b.runtime)} — ${b.reason}`);
        }
        if (cause === "hotset_change") {
          // The known exposure window (plan): a freshly-warmed runtime is worker-only until the
          // anchor's next poll. Journaled so the gap is on the record, not folklore.
          this.opts.journal.append("hotset_changed", {
            subscribed: report.subscribed,
            exposure: "worker-only until anchor poll catches up",
          });
        }
      }
      this.seenHotsetVersion = version;
    } finally {
      this.passInFlight = false;
    }
  }

  /**
   * One forward-progress round-trip. Success → fresh liveness file. Failure → journal + bounce;
   * the file goes stale and the plist watchdog acts on staleness, not on our self-report.
   */
  private async livenessProbe(): Promise<void> {
    if (this.probeInFlight) return;
    const conn = this.loop.current;
    if (!conn) return;
    this.probeInFlight = true;
    try {
      const hot = this.opts.registry.hotRows();
      const first = hot[0];
      if (first) {
        const runtime = { agent_id: first.agent_id, conversation_id: first.conversation_id };
        await conn.request(
          (rid) => buildSync(rid, runtime, false),
          Outbound.sync,
          this.opts.livenessDeadlineMs,
        );
      } else {
        // Empty hot set: prove the CONNECTION is responsive; there is no runtime to sync.
        await conn.request(
          buildAppServerInfo,
          Outbound.appServerInfo,
          this.opts.livenessDeadlineMs,
        );
      }
      this.writeLiveness(hot.length);
    } catch (e) {
      const detail = e instanceof Error ? e.message : String(e);
      this.opts.journal.append("liveness_probe_failed", { detail });
      this.loop.bounce(`liveness probe failed: ${detail}`);
    } finally {
      this.probeInFlight = false;
    }
  }

  private writeLiveness(hotCount: number): void {
    const payload = JSON.stringify({
      at: new Date().toISOString(),
      state: this.loop.state,
      hot: hotCount,
      subscribed: this.subscribedKeys.size,
      degraded: this.opts.degraded,
    });
    mkdirSync(dirname(this.opts.livenessFile), { recursive: true, mode: 0o700 });
    // Atomic via rename: the watchdog must never read a half-written file.
    const tmp = join(dirname(this.opts.livenessFile), `.liveness.${process.pid}.tmp`);
    writeFileSync(tmp, payload, { mode: 0o600 });
    renameSync(tmp, this.opts.livenessFile);
  }
}
