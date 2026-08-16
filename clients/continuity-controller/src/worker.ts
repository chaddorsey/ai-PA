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
import type { ReconnectPolicy } from "@ai-pa/letta-continuity-core/connection";
import { Outbound, buildAppServerInfo, buildSync } from "@ai-pa/letta-continuity-core/protocol";
import type { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import { ConnectionLoop } from "./connection-loop.js";
import { subscribeRuntimes } from "./hotset.js";
import type { Registry, RuntimeRef } from "./registry.js";
import type { Journal } from "./state/journal.js";

export interface WorkerOptions {
  url: string;
  registry: Registry;
  journal: Journal;
  livenessFile: string;
  livenessIntervalMs: number;
  livenessDeadlineMs: number;
  hotsetPollMs: number;
  /** Degradation report from openStateDb — carried into journal + liveness, never dropped. */
  degraded: string | null;
  onWarn?: (msg: string) => void;
  onExhausted: () => void;
  reconnect?: ReconnectPolicy;
  makeConnection?: (url: string, onWarn: (msg: string) => void) => WsConnection;
}

const key = (r: RuntimeRef): string => `${r.agent_id}:${r.conversation_id}`;

export class WorkerDaemon {
  private readonly loop: ConnectionLoop;
  private livenessTimer: ReturnType<typeof setInterval> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private subscribedKeys = new Set<string>();
  private seenHotsetVersion = -1;
  private passInFlight = false;
  private probeInFlight = false;

  constructor(private readonly opts: WorkerOptions) {
    this.loop = new ConnectionLoop({
      url: opts.url,
      onWarn: opts.onWarn,
      onExhausted: opts.onExhausted,
      reconnect: opts.reconnect,
      makeConnection: opts.makeConnection,
      onConnected: async (conn) => {
        this.subscribedKeys = new Set();
        await this.subscribePass(conn, "connect");
        this.opts.journal.append("worker_connected", {
          url: this.opts.url,
          subscribed: [...this.subscribedKeys],
        });
      },
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
    await this.loop.start();
    this.livenessTimer = setInterval(() => void this.livenessProbe(), this.opts.livenessIntervalMs);
    this.livenessTimer.unref?.();
    this.pollTimer = setInterval(() => void this.pollHotset(), this.opts.hotsetPollMs);
    this.pollTimer.unref?.();
    // Prove liveness immediately rather than an interval from now — a daemon that boots and
    // dies inside the first interval would otherwise leave no liveness evidence at all.
    await this.livenessProbe();
  }

  stop(): void {
    if (this.livenessTimer) clearInterval(this.livenessTimer);
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.livenessTimer = null;
    this.pollTimer = null;
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
        const report = await subscribeRuntimes(conn, fresh, { waitForReplay: true });
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
