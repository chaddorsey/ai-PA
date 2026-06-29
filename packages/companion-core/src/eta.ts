/**
 * Eta — ETA estimation for the Amtrak companion.
 *
 * Two paths:
 *
 * trip-actual (`schedule_basis.kind === 'trip-actual'`):
 *   Uses the real ensemble from `bundle.eta_table` (per-station p10/p50/p90 in minutes
 *   from departure), converted to absolute epoch-ms via the departure clock.
 *   `estimated: false`.
 *
 *   For toMile, elapsed_min is interpolated from `position_table` (linear on the
 *   [elapsed_min, mile] column) to get p50. The p10/p90 spread is derived by
 *   bracketing with the nearest eta_table neighbours: the spread at the queried mile
 *   is linearly interpolated between the two bracketing station spreads, then applied
 *   symmetrically around the interpolated p50.
 *
 * generic-scheduled:
 *   Returns a single time (p10 === p50 === p90) derived from the position_table
 *   elapsed_min at the requested mile/station. No fake band.
 *   `estimated: true`.
 *
 * Departure clock:
 *   Pass `departureMs` to the constructor, or call `setDeparture(ms)` before use.
 *   Without a departure, results are NaN (no absolute anchor available).
 */

import type { Bundle, EtaResult, EtaTableRow, Position, PositionTableRow } from './types.js';

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Linear interpolation: given a sorted table of [x, y] pairs, find y at xQuery.
 * Clamps to endpoints outside the table range.
 */
function lerpTable(table: [number, number][], xQuery: number): number {
  if (table.length === 0) return NaN;
  if (xQuery <= table[0][0]) return table[0][1];
  if (xQuery >= table[table.length - 1][0]) return table[table.length - 1][1];
  for (let i = 0; i < table.length - 1; i++) {
    const [x1, y1] = table[i];
    const [x2, y2] = table[i + 1];
    if (x1 <= xQuery && xQuery <= x2) {
      const f = x2 !== x1 ? (xQuery - x1) / (x2 - x1) : 0;
      return y1 + f * (y2 - y1);
    }
  }
  return table[table.length - 1][1];
}

/**
 * Build a sorted [mile, elapsed_min] lookup from position_table.
 * position_table rows: [elapsed_min, mile, lat, lon]
 */
function buildMileToMinTable(posTable: PositionTableRow[]): [number, number][] {
  return posTable.map(([elapsed_min, mile]) => [mile, elapsed_min]);
}

// ─────────────────────────────────────────────────────────────────────────────
// Eta class
// ─────────────────────────────────────────────────────────────────────────────

export class Eta {
  private readonly bundle: Bundle;
  private departureMs: number;

  /** sorted [mile, elapsed_min] table derived from position_table */
  private readonly mileToMin: [number, number][];

  /**
   * @param bundle      The trip bundle. Must include position_table.
   *                    For trip-actual, must include eta_table.
   * @param departureMs Absolute epoch-ms of leg departure (NOL sched_dep).
   *                    Can also be set later via setDeparture().
   */
  constructor(bundle: Bundle, departureMs?: number) {
    this.bundle = bundle;
    this.departureMs = departureMs ?? NaN;
    this.mileToMin = buildMileToMinTable(bundle.position_table);
  }

  /** Set (or update) the departure epoch-ms. */
  setDeparture(epochMs: number): void {
    this.departureMs = epochMs;
  }

  private get isTripActual(): boolean {
    return this.bundle.schedule_basis.kind === 'trip-actual';
  }

  // ─── toStation ─────────────────────────────────────────────────────────────

  /**
   * Estimate time of arrival at the named station.
   *
   * trip-actual: reads the eta_table row directly → absolute epoch-ms band.
   * generic-scheduled: reads sched_arr from stations list → single absolute epoch-ms.
   *
   * Throws if the station code is not found.
   */
  toStation(code: string, _position: Position): EtaResult {
    if (this.isTripActual) {
      return this._toStationTripActual(code);
    }
    return this._toStationGeneric(code);
  }

  private _toStationTripActual(code: string): EtaResult {
    const row = this.bundle.eta_table.find((r: EtaTableRow) => r.station_code === code);
    if (!row) {
      throw new Error(`Eta.toStation: station "${code}" not found in eta_table`);
    }
    const dep = this.departureMs;
    return {
      p10: dep + row.p10_min * 60_000,
      p50: dep + row.p50_min * 60_000,
      p90: dep + row.p90_min * 60_000,
      estimated: false,
    };
  }

  private _toStationGeneric(code: string): EtaResult {
    // For generic, use the station's sched_arr as the single estimate.
    const station = this.bundle.stations.find(s => s.code === code);
    if (!station) {
      throw new Error(`Eta.toStation: station "${code}" not found in bundle.stations`);
    }

    let singleMs: number;
    if (station.sched_arr) {
      singleMs = new Date(station.sched_arr).getTime();
    } else if (station.sched_dep) {
      // Origin station has no sched_arr; use sched_dep (departure = arrival for origin)
      singleMs = new Date(station.sched_dep).getTime();
    } else {
      // Fall back to position_table interpolation from departure clock
      const elapsedMin = lerpTable(this.mileToMin, station.mile);
      singleMs = this.departureMs + elapsedMin * 60_000;
    }

    return { p10: singleMs, p50: singleMs, p90: singleMs, estimated: true };
  }

  // ─── toMile ────────────────────────────────────────────────────────────────

  /**
   * Estimate time of arrival at the given milepost.
   *
   * p50 for both trip-actual and generic comes from linear interpolation of
   * position_table (elapsed_min at that mile → absolute epoch-ms via departure clock).
   *
   * trip-actual additionally derives a p10/p90 band by linearly interpolating the
   * spread between the two nearest eta_table station brackets, applied ±around p50.
   *
   * generic-scheduled: p10 === p50 === p90.
   */
  toMile(mile: number, _position: Position): EtaResult {
    // p50: interpolate elapsed_min from position_table
    const elapsedMin50 = lerpTable(this.mileToMin, mile);
    const p50 = this.departureMs + elapsedMin50 * 60_000;

    if (!this.isTripActual) {
      return { p10: p50, p50, p90: p50, estimated: true };
    }

    // trip-actual: derive p10/p90 spread by bracketing with eta_table
    const spread = this._interpolateSpread(mile, elapsedMin50);
    const p10 = this.departureMs + (elapsedMin50 - spread.halfWidthLow) * 60_000;
    const p90 = this.departureMs + (elapsedMin50 + spread.halfWidthHigh) * 60_000;

    // Clamp so p10 <= p50 <= p90 (defensive; interpolation should already satisfy this)
    return {
      p10: Math.min(p10, p50),
      p50,
      p90: Math.max(p90, p50),
      estimated: false,
    };
  }

  /**
   * For a given mile (with its position_table p50 elapsed_min), interpolate the
   * p10 and p90 half-widths by bracketing with the two nearest eta_table stations.
   *
   * Each eta_table row gives p10_min/p50_min/p90_min from departure.  The spread
   * at a given elapsed_min is:
   *   halfWidthLow  = p50_min - p10_min
   *   halfWidthHigh = p90_min - p50_min
   *
   * We find the two eta_table stations that bracket the queried mile (sorted by their
   * p50_min, which corresponds to position on the route) and linearly interpolate the
   * half-widths between them.
   *
   * If the queried mile is before all eta_table entries, we use the first entry's spread.
   * If after all, we use the last entry's spread.
   */
  private _interpolateSpread(
    mile: number,
    _elapsedMin50: number,
  ): { halfWidthLow: number; halfWidthHigh: number } {
    const etaTable = this.bundle.eta_table;
    if (etaTable.length === 0) {
      return { halfWidthLow: 0, halfWidthHigh: 0 };
    }

    // Build a sorted table of [station_mile, halfWidthLow, halfWidthHigh]
    // using the stations list to map station_code → mile.
    const stationMileMap = new Map<string, number>(
      this.bundle.stations.map(s => [s.code, s.mile]),
    );

    type SpreadEntry = { stationMile: number; low: number; high: number };
    const spreads: SpreadEntry[] = etaTable
      .map((row: EtaTableRow) => {
        const stationMile = stationMileMap.get(row.station_code);
        if (stationMile === undefined) return null;
        return {
          stationMile,
          low: row.p50_min - row.p10_min,
          high: row.p90_min - row.p50_min,
        };
      })
      .filter((e): e is SpreadEntry => e !== null)
      .sort((a, b) => a.stationMile - b.stationMile);

    if (spreads.length === 0) return { halfWidthLow: 0, halfWidthHigh: 0 };

    // Clamp at endpoints
    if (mile <= spreads[0].stationMile) {
      return { halfWidthLow: spreads[0].low, halfWidthHigh: spreads[0].high };
    }
    if (mile >= spreads[spreads.length - 1].stationMile) {
      const last = spreads[spreads.length - 1];
      return { halfWidthLow: last.low, halfWidthHigh: last.high };
    }

    // Linear interpolation between brackets
    for (let i = 0; i < spreads.length - 1; i++) {
      const a = spreads[i];
      const b = spreads[i + 1];
      if (a.stationMile <= mile && mile <= b.stationMile) {
        const f =
          b.stationMile !== a.stationMile
            ? (mile - a.stationMile) / (b.stationMile - a.stationMile)
            : 0;
        return {
          halfWidthLow: a.low + f * (b.low - a.low),
          halfWidthHigh: a.high + f * (b.high - a.high),
        };
      }
    }

    const last = spreads[spreads.length - 1];
    return { halfWidthLow: last.low, halfWidthHigh: last.high };
  }
}
