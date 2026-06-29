/**
 * Test suite for Eta module — Plan 2 Task 6.
 *
 * Tests both trip-actual (real ensemble band, estimated:false) and
 * generic-scheduled (single time, estimated:true) paths against
 * the real leg-58 bundle.json.
 */
import { describe, it, expect, beforeAll } from 'vitest';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';
import { Eta } from '../src/eta.js';
import type { Bundle, EtaTableRow, Position } from '../src/types.js';

const __dir = dirname(fileURLToPath(import.meta.url));
const BUNDLE_PATH = join(__dir, '../../../tools/amtrak-position-engine/bundles/leg58/bundle.json');

// Departure: 2026-07-11T15:45:00-05:00 → absolute epoch-ms
// (UTC = 2026-07-11T20:45:00Z)
const DEP_ISO = '2026-07-11T15:45:00-05:00';
const DEP_MS = new Date(DEP_ISO).getTime(); // 1783802700000

/** Build a Position anchored to the given mile, with nowMs as the observation time. */
function makePos(mile: number, nowMs: number = DEP_MS): Position {
  return {
    mile,
    lat: 0,
    lon: 0,
    source: 'gps',
    direction: 1,
    leg: '58',
    stopped: false,
  };
}

let bundle: Bundle;

beforeAll(() => {
  const raw = JSON.parse(readFileSync(BUNDLE_PATH, 'utf8'));
  // leg is a number in the JSON; coerce to string per Bundle contract
  raw.leg = String(raw.leg);
  bundle = raw as Bundle;
});

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function getEtaRow(code: string): EtaTableRow {
  const row = bundle.eta_table.find(r => r.station_code === code);
  if (!row) throw new Error(`eta_table row for ${code} not found`);
  return row;
}

// ─────────────────────────────────────────────────────────────────────────────
// A. trip-actual path — toStation
// ─────────────────────────────────────────────────────────────────────────────
describe('Eta.toStation — trip-actual (estimated:false)', () => {
  it('returns estimated:false for a trip-actual bundle', () => {
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const result = eta.toStation('HMD', pos);
    expect(result.estimated).toBe(false);
  });

  it('returns absolute epoch-ms (values > DEP_MS)', () => {
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const result = eta.toStation('HMD', pos);
    expect(result.p10).toBeGreaterThan(DEP_MS);
    expect(result.p50).toBeGreaterThan(DEP_MS);
    expect(result.p90).toBeGreaterThan(DEP_MS);
  });

  it('p10 <= p50 <= p90 for HMD', () => {
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const result = eta.toStation('HMD', pos);
    expect(result.p10).toBeLessThanOrEqual(result.p50);
    expect(result.p50).toBeLessThanOrEqual(result.p90);
  });

  it('spread matches the eta_table row for HMD (converted to epoch-ms)', () => {
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const result = eta.toStation('HMD', pos);
    const row = getEtaRow('HMD');
    // The absolute times = DEP_MS + p_min * 60000
    expect(result.p10).toBe(DEP_MS + row.p10_min * 60_000);
    expect(result.p50).toBe(DEP_MS + row.p50_min * 60_000);
    expect(result.p90).toBe(DEP_MS + row.p90_min * 60_000);
  });

  it('farther stations have larger p50 than nearer ones', () => {
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const hmd = eta.toStation('HMD', pos);
    const mem = eta.toStation('MEM', pos);
    const chi = eta.toStation('CHI', pos);
    expect(hmd.p50).toBeLessThan(mem.p50);
    expect(mem.p50).toBeLessThan(chi.p50);
  });

  it('throws (or returns undefined-like error) for unknown station code', () => {
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    expect(() => eta.toStation('XXX', pos)).toThrow();
  });

  it('works for all 19 eta_table stations: p10 <= p50 <= p90', () => {
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    for (const row of bundle.eta_table) {
      const result = eta.toStation(row.station_code, pos);
      expect(result.estimated).toBe(false);
      expect(result.p10).toBeLessThanOrEqual(result.p50);
      expect(result.p50).toBeLessThanOrEqual(result.p90);
      expect(result.p10).toBe(DEP_MS + row.p10_min * 60_000);
      expect(result.p50).toBe(DEP_MS + row.p50_min * 60_000);
      expect(result.p90).toBe(DEP_MS + row.p90_min * 60_000);
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// B. trip-actual path — toMile
// ─────────────────────────────────────────────────────────────────────────────
describe('Eta.toMile — trip-actual (estimated:false)', () => {
  it('returns estimated:false', () => {
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const result = eta.toMile(100, pos);
    expect(result.estimated).toBe(false);
  });

  it('p50 is an absolute epoch-ms greater than DEP_MS', () => {
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const result = eta.toMile(100, pos);
    expect(result.p50).toBeGreaterThan(DEP_MS);
  });

  it('p10 <= p50 <= p90', () => {
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const result = eta.toMile(100, pos);
    expect(result.p10).toBeLessThanOrEqual(result.p50);
    expect(result.p50).toBeLessThanOrEqual(result.p90);
  });

  it('farther miles have larger p50 (monotonic in position_table)', () => {
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const r100 = eta.toMile(100, pos);
    const r300 = eta.toMile(300, pos);
    const r600 = eta.toMile(600, pos);
    expect(r100.p50).toBeLessThan(r300.p50);
    expect(r300.p50).toBeLessThan(r600.p50);
  });

  it('toMile on a station mile is close to toStation p50 (within 15 min)', () => {
    // HMD is at mile 53; toMile(53) should be near toStation('HMD')
    const eta = new Eta(bundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const byMile = eta.toMile(53, pos);
    const byStation = eta.toStation('HMD', pos);
    const diffMs = Math.abs(byMile.p50 - byStation.p50);
    // Allow up to 15 minutes difference (interpolation vs. ensemble anchor)
    expect(diffMs).toBeLessThan(15 * 60_000);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// C. generic-scheduled path — estimated:true, p10===p50===p90
// ─────────────────────────────────────────────────────────────────────────────
describe('Eta — generic-scheduled path (estimated:true)', () => {
  let genericBundle: Bundle;

  beforeAll(() => {
    // Build a generic bundle by cloning the trip-actual bundle and swapping kind,
    // clearing eta_table, and clearing valid_dates.
    genericBundle = {
      ...bundle,
      schedule_basis: { kind: 'generic-scheduled', valid_dates: [] },
      // eta_table absent/empty for generic
      eta_table: [],
    };
  });

  it('toStation returns estimated:true for generic bundle', () => {
    const eta = new Eta(genericBundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    // HMD is in the stations list with a sched_arr; use it
    const result = eta.toStation('HMD', pos);
    expect(result.estimated).toBe(true);
  });

  it('toStation: p10 === p50 === p90 (single time, no fake band)', () => {
    const eta = new Eta(genericBundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const result = eta.toStation('HMD', pos);
    expect(result.p10).toBe(result.p50);
    expect(result.p50).toBe(result.p90);
  });

  it('toStation generic returns a value > DEP_MS', () => {
    const eta = new Eta(genericBundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const result = eta.toStation('HMD', pos);
    expect(result.p50).toBeGreaterThan(DEP_MS);
  });

  it('toMile returns estimated:true for generic bundle', () => {
    const eta = new Eta(genericBundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const result = eta.toMile(100, pos);
    expect(result.estimated).toBe(true);
  });

  it('toMile generic: p10 === p50 === p90', () => {
    const eta = new Eta(genericBundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const result = eta.toMile(100, pos);
    expect(result.p10).toBe(result.p50);
    expect(result.p50).toBe(result.p90);
  });

  it('toMile generic farther mile still has larger p50', () => {
    const eta = new Eta(genericBundle, DEP_MS);
    const pos = makePos(0, DEP_MS);
    const r100 = eta.toMile(100, pos);
    const r400 = eta.toMile(400, pos);
    expect(r100.p50).toBeLessThan(r400.p50);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// D. setDeparture / constructor departure param
// ─────────────────────────────────────────────────────────────────────────────
describe('Eta — departure clock', () => {
  it('setDeparture changes the result base time', () => {
    const eta = new Eta(bundle);
    const pos = makePos(0, DEP_MS);
    eta.setDeparture(DEP_MS);
    const r1 = eta.toStation('HMD', pos);
    eta.setDeparture(DEP_MS + 3600_000); // 1 hour later
    const r2 = eta.toStation('HMD', pos);
    expect(r2.p50 - r1.p50).toBe(3600_000);
  });

  it('no departure set → toStation throws or returns NaN (cannot compute absolute)', () => {
    const eta = new Eta(bundle); // no departure
    const pos = makePos(0);
    // With no departure clock, result should throw or p50 should be NaN/not-finite
    let threw = false;
    let result: ReturnType<Eta['toStation']> | undefined;
    try {
      result = eta.toStation('HMD', pos);
    } catch {
      threw = true;
    }
    if (!threw && result) {
      // If it doesn't throw, it should produce NaN (no departure to anchor to)
      expect(!isFinite(result.p50)).toBe(true);
    }
  });
});
