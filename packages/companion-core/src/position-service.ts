/**
 * position-service.ts — Plan 2, Task 4
 *
 * GPS → dead-reckon → predicted fallback ladder with full robustness per Plan 0 §E:
 *
 * Constants (documented here):
 *   STOPPED_SPEED_MPH      = 1.0  — below this, stopped=true, milepost is HELD
 *   DIRECTION_DEBOUNCE_N   = 3    — consecutive consistent fixes to flip direction
 *   OFFTRACK_REJECT_MI     = 1.0  — fixes beyond this emit 'off-route' state
 *   DEADRECKON_MAX_MIN     = 5.0  — after this long with no GPS, stop advancing → 'predicted'
 *   GPS_STALE_MS           = 60_000 — within this, keep returning 'gps' source
 *   EMA_ALPHA              = 0.3  — smoothing factor for GPS mile EMA
 *   MIN_DISPLACEMENT_MI    = 0.05 — min displacement to update EMA (jitter gate)
 */

import type { Bundle, Position, Polyline, PositionTableRow } from './types.js';
import { milepostToLatLon, projectToLeg } from './projection.js';

// ── Tuning constants ──────────────────────────────────────────────────────────

/** Speed (mph) below which the train is considered stopped. */
const STOPPED_SPEED_MPH = 1.0;

/** Number of consecutive consistent-direction fixes required to flip direction. */
const DIRECTION_DEBOUNCE_N = 3;

/** Fixes farther than this from the polyline are rejected as off-route (miles). */
const OFFTRACK_REJECT_MI = 1.0;

/**
 * After this many minutes with no GPS, dead-reckon stops advancing and source
 * transitions to 'predicted' (position_table interpolation via setDeparture).
 */
const DEADRECKON_MAX_MIN = 5.0;

/** Within this window after the last GPS fix, source is still reported as 'gps'. */
const GPS_STALE_MS = 60_000;

/**
 * Minimum displacement (miles) for a new GPS fix to update the tracked mile.
 * Fixes projecting less than this delta are ignored for mile advancement (jitter gate).
 * This implements the "EMA / min-displacement gate" smoothing per Plan 0 §E.
 */
const MIN_DISPLACEMENT_MI = 0.05;

// ── Internal state ────────────────────────────────────────────────────────────

interface FixState {
  ts: number;          // epoch ms of the fix
  mile: number;        // projected mile (smoothed)
  lat: number;         // raw GPS lat
  lon: number;         // raw GPS lon
  speedMph: number;    // reported speed (or 0)
  stopped: boolean;    // was speed below threshold?
}

// ── PositionService ───────────────────────────────────────────────────────────

export class PositionService {
  private readonly legId: string;
  private readonly poly: Polyline;
  private readonly positionTable: PositionTableRow[];

  // GPS state
  private lastFix: FixState | null = null;
  private smoothedMile: number | null = null;
  private lastOffRoute = false;

  // Departure (for predicted fallback)
  private departureMs: number | null = null;

  // Direction debounce
  private direction: 1 | -1 = 1;
  private directionCandidateCount = 0;  // consecutive fixes in candidate direction
  private directionCandidate: 1 | -1 = 1;

  constructor(bundle: Bundle, poly: Polyline, legId: string) {
    this.legId = legId;
    this.poly = poly;
    this.positionTable = bundle.position_table;
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Supply a GPS fix. ts = unix epoch ms; speed = mph (optional, defaults to 0).
   * Robustness: off-route fixes are recorded as off-route and do NOT update mile.
   * Stopped: speed ≈ 0 → stopped flag, milepost held (no dead-reckon advancement).
   * Smoothing: EMA + min-displacement gate filters sub-threshold jitter.
   * Direction: flipped only after DIRECTION_DEBOUNCE_N consistent backward fixes.
   */
  onFix(lat: number, lon: number, ts: number, speed?: number): void {
    const proj = projectToLeg(this.poly, lat, lon);
    const rawMile = proj.mile;
    const offtrackMi = proj.offtrackMi;
    const speedMph = speed !== undefined ? Math.max(0, speed) : 0;
    const stopped = speedMph < STOPPED_SPEED_MPH;

    // ── OFF-ROUTE REJECTION ────────────────────────────────────────────────────
    if (offtrackMi > OFFTRACK_REJECT_MI) {
      this.lastOffRoute = true;
      // Record the fix timestamp but do NOT update smoothed mile or direction
      // Keep the previous fix's mile so resumed dead-reckon stays honest
      if (this.lastFix !== null) {
        this.lastFix = {
          ...this.lastFix,
          ts,
          lat,
          lon,
          speedMph,
          stopped,
        };
      } else {
        // No prior fix — store a minimal off-route fix at mile 0
        this.lastFix = { ts, mile: 0, lat, lon, speedMph, stopped };
      }
      return;
    }

    this.lastOffRoute = false;

    // ── JITTER SMOOTHING (min-displacement gate) ───────────────────────────────
    // If the new projected mile is within MIN_DISPLACEMENT_MI of the current
    // tracked mile, suppress the update (treat as GPS noise in-place).
    // Displacements above the gate are accepted as-is (no EMA dampening on
    // legitimate large moves).
    let smoothedMile: number;
    if (this.smoothedMile === null) {
      // First valid fix — seed tracker
      smoothedMile = rawMile;
    } else {
      const displacementMi = Math.abs(rawMile - this.smoothedMile);
      if (displacementMi < MIN_DISPLACEMENT_MI) {
        // Below jitter gate — hold current tracked mile
        smoothedMile = this.smoothedMile;
      } else {
        // Above gate — accept the new projected mile
        smoothedMile = rawMile;
      }
    }
    this.smoothedMile = smoothedMile;

    // ── DIRECTION DEBOUNCE ─────────────────────────────────────────────────────
    if (this.lastFix !== null && this.lastFix.mile !== smoothedMile) {
      const candidateDirection: 1 | -1 = smoothedMile >= this.lastFix.mile ? 1 : -1;
      if (candidateDirection === this.direction) {
        // Consistent with current direction — reset debounce candidate counter
        this.directionCandidateCount = 0;
        this.directionCandidate = candidateDirection;
      } else {
        // Inconsistency: accumulate against the candidate flip direction
        if (candidateDirection === this.directionCandidate) {
          this.directionCandidateCount++;
        } else {
          // New candidate direction — reset
          this.directionCandidate = candidateDirection;
          this.directionCandidateCount = 1;
        }
        if (this.directionCandidateCount >= DIRECTION_DEBOUNCE_N) {
          // Enough consistent opposing fixes — flip direction
          this.direction = candidateDirection;
          this.directionCandidateCount = 0;
        }
      }
    }

    // ── UPDATE LAST FIX ────────────────────────────────────────────────────────
    this.lastFix = {
      ts,
      mile: smoothedMile,
      lat,
      lon,
      speedMph,
      stopped,
    };
  }

  /**
   * Set the leg departure epoch (ms). Used by tick() for predicted fallback
   * when no GPS fix is available.
   */
  setDeparture(epochMs: number): void {
    this.departureMs = epochMs;
  }

  /**
   * Compute position at nowMs.
   *
   * Ladder:
   *   1. If off-route:          source = 'off-route', hold last valid mile
   *   2. If GPS is fresh:       source = 'gps', return last fix position
   *   3. If within dead-reckon cap: source = 'deadreckon', advance by speed × elapsed
   *      (BUT: if stopped, hold milepost — no forward movement)
   *   4. If dead-reckon expired: source = 'predicted', interpolate position_table
   *   5. No GPS + no departure: source = 'predicted', fallback to table start
   */
  tick(nowMs: number): Position {
    // ── OFF-ROUTE ──────────────────────────────────────────────────────────────
    if (this.lastOffRoute && this.lastFix !== null) {
      const ll = milepostToLatLon(this.poly, this.lastFix.mile);
      return {
        mile: this.lastFix.mile,
        lat: ll.lat,
        lon: ll.lon,
        source: 'off-route',
        direction: this.direction,
        leg: this.legId,
        stopped: this.lastFix.stopped,
      };
    }

    // ── GPS FRESH (within GPS_STALE_MS) ───────────────────────────────────────
    if (this.lastFix !== null) {
      const elapsedSinceFix = nowMs - this.lastFix.ts;

      if (elapsedSinceFix <= GPS_STALE_MS) {
        const ll = milepostToLatLon(this.poly, this.lastFix.mile);
        return {
          mile: this.lastFix.mile,
          lat: ll.lat,
          lon: ll.lon,
          source: 'gps',
          direction: this.direction,
          leg: this.legId,
          stopped: this.lastFix.stopped,
        };
      }

      // ── DEAD-RECKON (GPS stale but within age cap) ─────────────────────────
      const elapsedSinceFixMin = elapsedSinceFix / 60_000;

      if (elapsedSinceFixMin <= DEADRECKON_MAX_MIN) {
        // STOPPED: do not advance while stopped
        let deadMile: number;
        if (this.lastFix.stopped) {
          deadMile = this.lastFix.mile;
        } else {
          const elapsedHours = elapsedSinceFix / 3_600_000;
          deadMile = this.lastFix.mile + this.direction * this.lastFix.speedMph * elapsedHours;
        }

        // Clamp to polyline bounds
        const minMile = this.poly.length > 0 ? this.poly[0][0] : 0;
        const maxMile = this.poly.length > 0 ? this.poly[this.poly.length - 1][0] : deadMile;
        deadMile = Math.max(minMile, Math.min(maxMile, deadMile));

        const ll = milepostToLatLon(this.poly, deadMile);
        return {
          mile: deadMile,
          lat: ll.lat,
          lon: ll.lon,
          source: 'deadreckon',
          direction: this.direction,
          leg: this.legId,
          stopped: this.lastFix.stopped,
        };
      }

      // ── DEAD-RECKON AGE CAP EXCEEDED → fall through to predicted ──────────
    }

    // ── PREDICTED FALLBACK (position_table interpolation) ─────────────────────
    return this.predictedPosition(nowMs);
  }

  /**
   * Return the most recently computed position (the last tick result or last GPS fix).
   * Falls through to tick(Date.now()) if nothing is cached.
   */
  current(): Position {
    if (this.lastFix !== null) {
      // Return the last GPS fix state directly (off-route or normal)
      if (this.lastOffRoute) {
        const ll = milepostToLatLon(this.poly, this.lastFix.mile);
        return {
          mile: this.lastFix.mile,
          lat: ll.lat,
          lon: ll.lon,
          source: 'off-route',
          direction: this.direction,
          leg: this.legId,
          stopped: this.lastFix.stopped,
        };
      }
      const ll = milepostToLatLon(this.poly, this.lastFix.mile);
      return {
        mile: this.lastFix.mile,
        lat: ll.lat,
        lon: ll.lon,
        source: 'gps',
        direction: this.direction,
        leg: this.legId,
        stopped: this.lastFix.stopped,
      };
    }
    // No GPS fix received — compute predicted from now
    return this.predictedPosition(Date.now());
  }

  // ── Private helpers ─────────────────────────────────────────────────────────

  /**
   * Interpolate position_table by elapsed minutes from departure.
   * Falls back to polyline start if no departure has been set.
   */
  private predictedPosition(nowMs: number): Position {
    const table = this.positionTable;

    if (table.length >= 2 && this.departureMs !== null) {
      const elapsedMin = (nowMs - this.departureMs) / 60_000;

      let mile: number;
      let lat: number;
      let lon: number;

      if (elapsedMin <= table[0][0]) {
        // Before or at table start
        mile = table[0][1];
        lat  = table[0][2];
        lon  = table[0][3];
      } else if (elapsedMin >= table[table.length - 1][0]) {
        // Past table end — clamp
        const last = table[table.length - 1];
        mile = last[1];
        lat  = last[2];
        lon  = last[3];
      } else {
        // Interpolate within table
        mile = table[0][1];
        lat  = table[0][2];
        lon  = table[0][3];
        for (let i = 0; i < table.length - 1; i++) {
          const [t1, m1, la1, lo1] = table[i];
          const [t2, m2, la2, lo2] = table[i + 1];
          if (t1 <= elapsedMin && elapsedMin <= t2) {
            const f = t2 !== t1 ? (elapsedMin - t1) / (t2 - t1) : 0;
            mile = m1 + f * (m2 - m1);
            lat  = la1 + f * (la2 - la1);
            lon  = lo1 + f * (lo2 - lo1);
            break;
          }
        }
      }

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

    // No departure set — return table start or polyline start
    const startMile = table.length > 0 ? table[0][1] : (this.poly.length > 0 ? this.poly[0][0] : 0);
    const startLat  = table.length > 0 ? table[0][2] : (this.poly.length > 0 ? this.poly[0][1] : 0);
    const startLon  = table.length > 0 ? table[0][3] : (this.poly.length > 0 ? this.poly[0][2] : 0);

    return {
      mile: startMile,
      lat: startLat,
      lon: startLon,
      source: 'predicted',
      direction: 1,
      leg: this.legId,
      stopped: false,
    };
  }
}
