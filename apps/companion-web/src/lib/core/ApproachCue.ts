/**
 * ApproachCue — ETA-threshold station approach detector.
 *
 * Instantiate one per trip session. Call check() on each position tick;
 * it fires at most once per station per instance lifecycle.
 * Call reset() to clear fired history (e.g., when starting a new leg).
 *
 * Design: a CLASS (not module-level mutable state) so multiple independent
 * instances can co-exist without leakage (important for tests and multiple legs).
 */

import type { Bundle, EtaResult, Position, Station } from 'companion-core';

// ── Threshold constants ───────────────────────────────────────────────────────

/** Fire the approach cue when ETA p50 is within this window (ms). */
export const APPROACH_ETA_THRESHOLD_MS = 15 * 60 * 1000; // 15 minutes

/** Also fire if the station is within this many miles ahead (distance gate). */
export const APPROACH_DISTANCE_THRESHOLD_MI = 10; // 10 miles

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ApproachResult {
  /** The next station within approach threshold. */
  station: Station;
  /** The p50 ETA epoch-ms from the Eta instance. */
  etaMs: number;
}

/** Minimal Eta interface that ApproachCue needs from companion-core's Eta class. */
export interface EtaLike {
  toStation(code: string, position: Position): EtaResult;
}

// ── ApproachCue class ─────────────────────────────────────────────────────────

export class ApproachCue {
  /** Set of station codes that have already fired in this instance's lifecycle. */
  private readonly fired = new Set<string>();

  /**
   * Check whether any upcoming station is within the approach threshold.
   *
   * Returns the first qualifying station (nearest ahead within threshold),
   * or null if nothing qualifies. Fires at most once per station per
   * instance lifecycle — once a station is returned, it will never be
   * returned again until reset() is called.
   *
   * Stations already passed (station.mile <= position.mile) are silently skipped.
   * If position.source === 'off-route', all checks are skipped and null is returned.
   *
   * @param position  Current position fix from PositionService.
   * @param eta       Eta instance (or compatible mock) for toStation().
   * @param stations  Station list from bundle.stations.
   */
  check(
    position: Position,
    eta: EtaLike,
    stations: Station[],
  ): ApproachResult | null {
    if (position.source === 'off-route') return null;

    const now = Date.now();

    for (const station of stations) {
      // Skip already-fired stations
      if (this.fired.has(station.code)) continue;

      // Skip stations the train has already passed
      if (station.mile <= position.mile) continue;

      const distanceAhead = station.mile - position.mile;

      let etaMs: number;
      let withinTime = false;

      try {
        const result = eta.toStation(station.code, position);
        etaMs = result.p50;
        const timeToArrivalMs = etaMs - now;
        withinTime = timeToArrivalMs > 0 && timeToArrivalMs <= APPROACH_ETA_THRESHOLD_MS;
      } catch {
        // ETA not available — distance-only gate
        if (distanceAhead <= APPROACH_DISTANCE_THRESHOLD_MI) {
          // Estimate etaMs at ~30 mph average
          etaMs = now + (distanceAhead / 30) * 3_600_000;
          this.fired.add(station.code);
          return { station, etaMs };
        }
        continue;
      }

      const withinDistance = distanceAhead <= APPROACH_DISTANCE_THRESHOLD_MI;

      if (withinTime || withinDistance) {
        this.fired.add(station.code);
        return { station, etaMs };
      }
    }

    return null;
  }

  /**
   * Clear the fired-station memory so every station can fire again.
   * Call at leg change or when intentionally replaying approach cues.
   */
  reset(): void {
    this.fired.clear();
  }
}
