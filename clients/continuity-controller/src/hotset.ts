/**
 * hotset.ts — turn registry rows into live subscriptions on one connection.
 *
 * The dual-subscription rule (plan, Key Technical Decisions): BOTH the anchor and the worker
 * `runtime_start` every hot runtime. The worker subscribes with `wait_for_replay` — its
 * subscription is the journaled one, so "subscribed" must mean replay-complete. The anchor
 * subscribes bare — its subscription exists purely for crash-overlap.
 *
 * A row the server refuses (`success:false`) is reported BROKEN, never thrown over: one dead
 * conversation must not cost the other rows their subscriptions (plan C3 edge case).
 */

import { Outbound, buildRuntimeStart } from "@ai-pa/letta-continuity-core/protocol";
import type { WsConnection } from "@ai-pa/letta-continuity-core/ws";
import type { RuntimeRef } from "./registry.js";

export interface SubscribeReport {
  subscribed: RuntimeRef[];
  broken: Array<{ runtime: RuntimeRef; reason: string }>;
}

export interface SubscribeOptions {
  /** True for the worker (journaled subscription), false for the anchor (crash-overlap only). */
  waitForReplay: boolean;
  /** Permission mode stamped on the hello (P5 runs the clone flipped to `standard`). */
  mode?: string;
  /**
   * Controller-owned external tools registered atomically with the hello (C7's
   * notify_operator). Registrations die with the connection, which is exactly why they ride
   * the hello: every reconnect re-registers by construction (C1 S5).
   */
  externalTools?: ReadonlyArray<{ tools: ReadonlyArray<Record<string, unknown>> }>;
  /** Per-runtime hello deadline. */
  timeoutMs?: number;
}

const DEFAULT_HELLO_TIMEOUT_MS = 30_000;

export async function subscribeRuntimes(
  conn: WsConnection,
  runtimes: readonly RuntimeRef[],
  options: SubscribeOptions,
): Promise<SubscribeReport> {
  const report: SubscribeReport = { subscribed: [], broken: [] };
  for (const runtime of runtimes) {
    const ref: RuntimeRef = {
      agent_id: runtime.agent_id,
      conversation_id: runtime.conversation_id,
    };
    let success: boolean;
    let error: string | undefined;
    try {
      const resp = await conn.request(
        // The anchor's hello carries NO wait_for_replay field at all (not `false`): its
        // subscription is crash-overlap only, and the leanest possible frame is the point.
        (rid) => {
          const startOptions: { waitForReplay?: boolean; mode?: string } = {};
          if (options.waitForReplay) startOptions.waitForReplay = true;
          if (options.mode) startOptions.mode = options.mode;
          const frame = buildRuntimeStart(
            rid,
            ref,
            Object.keys(startOptions).length > 0 ? startOptions : undefined,
          );
          if (options.externalTools) frame.external_tools = options.externalTools;
          return frame;
        },
        Outbound.runtimeStart,
        options.timeoutMs ?? DEFAULT_HELLO_TIMEOUT_MS,
      );
      success = resp.success === true;
      error = typeof resp.error === "string" ? resp.error : undefined;
    } catch (e) {
      // A connection-level fault (socket died, RPC timed out) is NOT a broken row — rethrow so
      // the connection loop treats it as a drop. Conflating the two would mark healthy rows
      // broken every time the server restarts mid-boot.
      throw e instanceof Error ? e : new Error(String(e));
    }
    if (success) report.subscribed.push(ref);
    else report.broken.push({ runtime: ref, reason: error ?? "runtime_start refused" });
  }
  return report;
}
