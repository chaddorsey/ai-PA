/**
 * anchor.ts — the minimal subscribe-only process that keeps turns alive across worker restarts.
 *
 * C1 S1/S1proc proved the premise live: a second subscriber — in a separate process, even one
 * that attaches late — holds a detached turn to a clean end_turn. The anchor is that second
 * subscriber, permanently, for every hot runtime.
 *
 * Near-zero logic BY DESIGN (plan, Key Technical Decisions): it reads the registry through a
 * READ-ONLY handle, never submits, never journals, and reacts to exactly one signal — the
 * `hotset_version` integer the worker bumps. Everything clever lives in the worker, which is
 * precisely why the worker may restart and the anchor must not have a reason to.
 *
 * Stale subscriptions (a runtime leaving the hot set) are tolerated until the next reconnect:
 * an extra subscription is benign (R1 finding — an observer is not a writer), and teaching the
 * anchor to unsubscribe would give it logic to get wrong.
 */

import type { ReconnectPolicy } from "@ai-pa/letta-continuity-core/connection";
import type { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import { ConnectionLoop } from "./connection-loop.js";
import { subscribeRuntimes } from "./hotset.js";
import type { ReadOnlyRegistry, RuntimeRef } from "./registry.js";

export interface AnchorOptions {
  url: string;
  registry: ReadOnlyRegistry;
  hotsetPollMs: number;
  /** Permission mode stamped on the anchor's hellos (P5 clone scenarios flip it). */
  runtimeMode?: string;
  onWarn?: (msg: string) => void;
  onExhausted: () => void;
  reconnect?: ReconnectPolicy;
  makeConnection?: (url: string, onWarn: (msg: string) => void) => WsConnection;
}

const key = (r: RuntimeRef): string => `${r.agent_id}:${r.conversation_id}`;

export class AnchorDaemon {
  private readonly loop: ConnectionLoop;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private subscribedKeys = new Set<string>();
  private seenHotsetVersion = -1;
  /** Serializes subscription passes; a poll firing mid-pass must not double-subscribe. */
  private passInFlight = false;

  constructor(private readonly opts: AnchorOptions) {
    this.loop = new ConnectionLoop({
      url: opts.url,
      onWarn: opts.onWarn,
      onExhausted: opts.onExhausted,
      reconnect: opts.reconnect,
      makeConnection: opts.makeConnection,
      onConnected: async (conn) => {
        // Fresh socket → no subscriptions survive; rebuild the whole set.
        this.subscribedKeys = new Set();
        await this.subscribePass(conn);
      },
    });
  }

  get state(): string {
    return this.loop.state;
  }

  /** Runtimes currently held on the live connection (test observability). */
  get held(): string[] {
    return [...this.subscribedKeys];
  }

  async start(): Promise<void> {
    await this.loop.start();
    this.pollTimer = setInterval(() => void this.pollHotset(), this.opts.hotsetPollMs);
    this.pollTimer.unref?.();
  }

  stop(): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = null;
    this.loop.stop();
  }

  private async pollHotset(): Promise<void> {
    const conn = this.loop.current;
    if (!conn) return;
    const version = this.opts.registry.hotsetVersion();
    if (version === this.seenHotsetVersion) return;
    await this.subscribePass(conn);
  }

  private async subscribePass(conn: WsConnection): Promise<void> {
    if (this.passInFlight) return;
    this.passInFlight = true;
    try {
      // Read the version BEFORE the rows: a bump landing between the two reads re-triggers the
      // pass on the next poll instead of being silently absorbed into a stale version stamp.
      const version = this.opts.registry.hotsetVersion();
      const rows = this.opts.registry.hotRows();
      const fresh = rows.filter((r) => !this.subscribedKeys.has(key(r)));
      if (fresh.length > 0) {
        const report = await subscribeRuntimes(conn, fresh, {
          waitForReplay: false,
          mode: this.opts.runtimeMode,
        });
        for (const r of report.subscribed) this.subscribedKeys.add(key(r));
        for (const b of report.broken) {
          // Read-only process: the WORKER owns marking rows broken; the anchor only says so.
          this.opts.onWarn?.(
            `anchor: runtime_start refused for ${key(b.runtime)} (${b.reason}) — leaving it to the worker to mark`,
          );
        }
      }
      this.seenHotsetVersion = version;
    } finally {
      this.passInFlight = false;
    }
  }
}
