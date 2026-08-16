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
import { Outbound, buildAppServerInfo, buildSync } from "@ai-pa/letta-continuity-core/protocol";
import type { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import { ApprovalArbiter } from "./approvals.js";
import { ConnectionLoop } from "./connection-loop.js";
import { subscribeRuntimes } from "./hotset.js";
import { TurnJournal } from "./journal.js";
import type { Registry, RuntimeRef } from "./registry.js";
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
  onWarn?: (msg: string) => void;
  onExhausted: () => void;
  reconnect?: ReconnectPolicy;
  makeConnection?: (url: string, onWarn: (msg: string) => void) => WsConnection;
}

const key = (r: RuntimeRef): string => `${r.agent_id}:${r.conversation_id}`;

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
  private readonly turnJournal: TurnJournal;
  private livenessTimer: ReturnType<typeof setInterval> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private queueTimer: ReturnType<typeof setInterval> | null = null;
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
        onWarn: this.opts.onWarn,
      });
      this.surfaceBoundPort = await this.surface.start(this.opts.surfacePort);
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
    // Prove liveness immediately rather than an interval from now — a daemon that boots and
    // dies inside the first interval would otherwise leave no liveness evidence at all.
    await this.livenessProbe();
  }

  stop(): void {
    if (this.livenessTimer) clearInterval(this.livenessTimer);
    if (this.pollTimer) clearInterval(this.pollTimer);
    if (this.queueTimer) clearInterval(this.queueTimer);
    this.livenessTimer = null;
    this.pollTimer = null;
    this.queueTimer = null;
    this.pipeline.stop();
    void this.surface?.stop();
    this.surface = null;
    this.loop.stop();
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
