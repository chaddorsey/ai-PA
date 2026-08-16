/**
 * config.ts — the controller's env-derived configuration, resolved once at boot.
 *
 * Everything here has a production default; the clone-validation launcher overrides via env in
 * its own plist copy only (the same single-writer-safety idiom as run-letta-app-server.sh:
 * a leaked value must never silently repoint a production daemon).
 */

import { homedir } from "node:os";
import { join } from "node:path";

export interface ControllerConfig {
  /** App Server WS endpoint. Loopback-only (core's trust boundary enforces it). */
  wsUrl: string;
  /** SQLite + liveness + token home. Created 0700 at boot. */
  stateDir: string;
  /** The worker's forward-progress liveness file (atomic-rename JSON). */
  livenessFile: string;
  /** How often the worker runs its liveness round-trip. */
  livenessIntervalMs: number;
  /** Deadline for one liveness round-trip; a miss forces a reconnect. */
  livenessDeadlineMs: number;
  /** How often the anchor (and worker) re-read the registry's hotset version. */
  hotsetPollMs: number;
  /** How often the worker sweeps for externally-enqueued turn rows. */
  queuePollMs: number;
  /** Wall-clock backstop per turn (C4) — coupled to abort_message, never a silent drop. */
  turnTimeoutMs: number;
  /** Bound on the abort round-trip before a wedged turn bounces the connection. */
  abortConfirmMs: number;
  /** Loopback surface-API port (C5). */
  surfacePort: number;
  /** Scheduler-dialect ingress port (C7). */
  ingressPort: number;
  /** Shared ingress secret (C7). Empty = ingress stays DOWN (fail-closed). */
  ingressSecret: string;
}

const DEFAULT_WS_URL = "ws://127.0.0.1:4577/ws";
const DEFAULT_LIVENESS_INTERVAL_MS = 20_000;
const DEFAULT_LIVENESS_DEADLINE_MS = 10_000;
const DEFAULT_HOTSET_POLL_MS = 2_000;
const DEFAULT_QUEUE_POLL_MS = 300;
const DEFAULT_TURN_TIMEOUT_MS = 600_000;
const DEFAULT_ABORT_CONFIRM_MS = 10_000;
const DEFAULT_SURFACE_PORT = 4610;
const DEFAULT_INGRESS_PORT = 4611;

function intFromEnv(value: string | undefined, fallback: number): number {
  const n = value === undefined ? Number.NaN : Number.parseInt(value, 10);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): ControllerConfig {
  const stateDir =
    env.CONTINUITY_STATE_DIR ??
    join(homedir(), "Library", "Application Support", "continuity-controller");
  return {
    wsUrl: env.CONTINUITY_WS_URL ?? DEFAULT_WS_URL,
    stateDir,
    livenessFile: join(stateDir, "liveness.json"),
    livenessIntervalMs: intFromEnv(
      env.CONTINUITY_LIVENESS_INTERVAL_MS,
      DEFAULT_LIVENESS_INTERVAL_MS,
    ),
    livenessDeadlineMs: intFromEnv(
      env.CONTINUITY_LIVENESS_DEADLINE_MS,
      DEFAULT_LIVENESS_DEADLINE_MS,
    ),
    hotsetPollMs: intFromEnv(env.CONTINUITY_HOTSET_POLL_MS, DEFAULT_HOTSET_POLL_MS),
    queuePollMs: intFromEnv(env.CONTINUITY_QUEUE_POLL_MS, DEFAULT_QUEUE_POLL_MS),
    turnTimeoutMs: intFromEnv(env.CONTINUITY_TURN_TIMEOUT_MS, DEFAULT_TURN_TIMEOUT_MS),
    abortConfirmMs: intFromEnv(env.CONTINUITY_ABORT_CONFIRM_MS, DEFAULT_ABORT_CONFIRM_MS),
    surfacePort: intFromEnv(env.CONTINUITY_SURFACE_PORT, DEFAULT_SURFACE_PORT),
    ingressPort: intFromEnv(env.CONTINUITY_INGRESS_PORT, DEFAULT_INGRESS_PORT),
    ingressSecret: env.CONTINUITY_INGRESS_SECRET ?? "",
  };
}
