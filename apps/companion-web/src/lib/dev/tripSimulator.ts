// DEV-ONLY: trip simulator for on-device couch testing.
// This module is ONLY used when DEV affordances are active.
// It is tree-shaken from production builds if not imported.

import type { Bundle, Position, PositionTableRow } from 'companion-core';

// ── Constants ─────────────────────────────────────────────────────────────────

/** Speed multipliers available in the dev UI. */
export const SIM_SPEED_OPTIONS = [0.5, 1, 2, 4, 8] as const;
export type SimSpeed = (typeof SIM_SPEED_OPTIONS)[number];

/** Default speed multiplier (real-time). */
const DEFAULT_SPEED: SimSpeed = 1;

/** Tick interval used by the simulator internally (ms). */
export const SIM_TICK_MS = 2_000;

// ── TripSimulator ─────────────────────────────────────────────────────────────

/**
 * DEV: Simulates a train moving along leg-58's position_table.
 *
 * Usage:
 *   const sim = new TripSimulator(bundle);
 *   sim.start(2);            // start at 2x speed
 *   const pos = sim.step(Date.now()); // get current simulated Position
 *   sim.stop();
 */
export class TripSimulator {
  private readonly positionTable: PositionTableRow[];
  private readonly legId: string;
  private _running = false;
  private _speed: SimSpeed = DEFAULT_SPEED;
  /** Simulated elapsed minutes along the position_table (starts at 0). */
  private _elapsedMin = 0;
  /** Real-world epoch ms when start() was called (or last resume). */
  private _startedAtMs = 0;
  /** Simulated elapsed minutes at last start()/resume call. */
  private _baseElapsedMin = 0;

  constructor(bundle: Bundle) {
    this.positionTable = bundle.position_table;
    this.legId = bundle.leg;
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  get running(): boolean {
    return this._running;
  }

  get speed(): SimSpeed {
    return this._speed;
  }

  /** Start or resume the simulator at the given speed multiplier. */
  start(speed: SimSpeed = DEFAULT_SPEED): void {
    this._speed = speed;
    this._startedAtMs = Date.now();
    this._baseElapsedMin = this._elapsedMin;
    this._running = true;
  }

  /** Stop the simulator. Does not reset position. */
  stop(): void {
    if (this._running) {
      // Snapshot elapsed before stopping so resume works correctly
      this._elapsedMin = this._computeElapsedMin(Date.now());
    }
    this._running = false;
  }

  /** Reset the simulated position to the start of the leg. */
  reset(): void {
    this._running = false;
    this._elapsedMin = 0;
    this._baseElapsedMin = 0;
    this._startedAtMs = 0;
  }

  /**
   * Compute the current simulated Position at nowMs.
   * Monotonically advances mile while running.
   * Safe to call when stopped (returns last position).
   */
  step(nowMs: number): Position {
    const elapsedMin = this._running
      ? this._computeElapsedMin(nowMs)
      : this._elapsedMin;

    // Clamp to table bounds
    const table = this.positionTable;
    if (table.length === 0) {
      return this._fallback();
    }

    const [lat, lon, mile] = this._interpolate(elapsedMin, table);

    return {
      mile,
      lat,
      lon,
      source: 'predicted',
      direction: 1,
      leg: this.legId,
      stopped: false,
    };
  }

  // ── Private helpers ─────────────────────────────────────────────────────────

  private _computeElapsedMin(nowMs: number): number {
    const realElapsedMin = (nowMs - this._startedAtMs) / 60_000;
    return this._baseElapsedMin + realElapsedMin * this._speed;
  }

  /**
   * Interpolate position_table (rows: [elapsed_min, mile, lat, lon]) at elapsedMin.
   * Returns [lat, lon, mile].
   */
  private _interpolate(elapsedMin: number, table: PositionTableRow[]): [number, number, number] {
    const first = table[0];
    const last = table[table.length - 1];

    if (elapsedMin <= first[0]) {
      return [first[2], first[3], first[1]];
    }
    if (elapsedMin >= last[0]) {
      return [last[2], last[3], last[1]];
    }

    for (let i = 0; i < table.length - 1; i++) {
      const [t1, m1, la1, lo1] = table[i];
      const [t2, m2, la2, lo2] = table[i + 1];
      if (t1 <= elapsedMin && elapsedMin <= t2) {
        const f = t2 !== t1 ? (elapsedMin - t1) / (t2 - t1) : 0;
        const mile = m1 + f * (m2 - m1);
        const lat = la1 + f * (la2 - la1);
        const lon = lo1 + f * (lo2 - lo1);
        return [lat, lon, mile];
      }
    }

    // Should not reach here, but be safe
    return [last[2], last[3], last[1]];
  }

  private _fallback(): Position {
    return {
      mile: 0,
      lat: 0,
      lon: 0,
      source: 'predicted',
      direction: 1,
      leg: this.legId,
      stopped: false,
    };
  }
}
