/**
 * Projection golden tests — Plan 2 Task 3.
 *
 * Every case in test/fixtures/projection-leg58.json was produced by running the
 * real Python position_engine on leg 58's polyline. The TS implementation must
 * match within:
 *   lat/lon  ≤ 0.001°
 *   mile     ≤ 0.01 mi
 *   offtrackMi ≤ 0.01 mi
 *   side     exactly (engine lowercase: 'left' | 'right' | 'ahead')
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { join, dirname } from 'path';
import { milepostToLatLon, projectToLeg } from '../src/projection.js';
import type { Polyline } from '../src/types.js';

const __dir = dirname(fileURLToPath(import.meta.url));

// ── Tolerances ─────────────────────────────────────────────────────────────────
const LAT_TOL = 0.001;  // degrees
const LON_TOL = 0.001;  // degrees
const MI_TOL  = 0.01;   // miles

// ── Load the golden fixture ────────────────────────────────────────────────────
interface MilepostCase {
  mile: number;
  lat: number;
  lon: number;
}

interface ProjectCase {
  _label?: string;
  lat: number;
  lon: number;
  mile: number;
  offtrackMi: number;
  side: string;
}

interface Fixture {
  polyline: [number, number, number][];
  milepost_cases: MilepostCase[];
  project_cases: ProjectCase[];
}

const fixturePath = join(__dir, 'fixtures', 'projection-leg58.json');
const fixture: Fixture = JSON.parse(readFileSync(fixturePath, 'utf8'));
const POLY: Polyline = fixture.polyline as Polyline;

// ── milepostToLatLon — unit tests against simple 3-vertex line ────────────────
describe('milepostToLatLon — unit', () => {
  // Straight line: New Orleans → Jackson → Chicago (synthetic)
  const UNIT_POLY: Polyline = [
    [0,   29.946, -90.078],
    [200, 32.298, -90.185],
    [500, 38.627, -90.199],
  ];

  it('returns exact start vertex at mile 0', () => {
    const r = milepostToLatLon(UNIT_POLY, 0);
    expect(Math.abs(r.lat - 29.946)).toBeLessThan(LAT_TOL);
    expect(Math.abs(r.lon - -90.078)).toBeLessThan(LON_TOL);
  });

  it('returns exact end vertex at last mile', () => {
    const r = milepostToLatLon(UNIT_POLY, 500);
    expect(Math.abs(r.lat - 38.627)).toBeLessThan(LAT_TOL);
    expect(Math.abs(r.lon - -90.199)).toBeLessThan(LON_TOL);
  });

  it('interpolates at midpoint of first segment (mile 100)', () => {
    const r = milepostToLatLon(UNIT_POLY, 100);
    const expectedLat = (29.946 + 32.298) / 2;
    const expectedLon = (-90.078 + -90.185) / 2;
    expect(Math.abs(r.lat - expectedLat)).toBeLessThan(LAT_TOL);
    expect(Math.abs(r.lon - expectedLon)).toBeLessThan(LON_TOL);
  });

  it('clamps below mile 0 to start', () => {
    const r = milepostToLatLon(UNIT_POLY, -99);
    expect(r.lat).toBe(UNIT_POLY[0][1]);
    expect(r.lon).toBe(UNIT_POLY[0][2]);
  });

  it('clamps above last mile to end', () => {
    const r = milepostToLatLon(UNIT_POLY, 9999);
    expect(r.lat).toBe(UNIT_POLY[2][1]);
    expect(r.lon).toBe(UNIT_POLY[2][2]);
  });

  it('returns exact mid-vertex at its anchor mile', () => {
    const r = milepostToLatLon(UNIT_POLY, 200);
    expect(Math.abs(r.lat - 32.298)).toBeLessThan(LAT_TOL);
    expect(Math.abs(r.lon - -90.185)).toBeLessThan(LON_TOL);
  });
});

// ── projectToLeg — unit tests ─────────────────────────────────────────────────
describe('projectToLeg — unit', () => {
  // Two-segment line: straight N–S then NE turn
  const UNIT_POLY: Polyline = [
    [0,   30.0, -90.0],
    [50,  31.0, -90.0],
    [100, 32.0, -89.0],
  ];

  it('returns ahead for a point exactly on-track (< 0.3 mi)', () => {
    // Exactly on the track at mile 25 (midpoint of first segment)
    const midLat = (30.0 + 31.0) / 2;
    const midLon = (-90.0 + -90.0) / 2;
    const r = projectToLeg(UNIT_POLY, midLat, midLon);
    expect(r.side).toBe('ahead');
    expect(r.offtrackMi).toBeLessThan(0.3);
  });

  it('projects a point left of northward travel to left', () => {
    // Train goes north (increasing lat, same lon). Point to the WEST = left when facing north.
    const r = projectToLeg(UNIT_POLY, 30.5, -90.2);
    expect(r.side).toBe('left');
  });

  it('projects a point right of northward travel to right', () => {
    // Point to the EAST = right when facing north.
    const r = projectToLeg(UNIT_POLY, 30.5, -89.8);
    expect(r.side).toBe('right');
  });

  it('mile output is within the polyline range', () => {
    const r = projectToLeg(UNIT_POLY, 30.5, -90.0);
    expect(r.mile).toBeGreaterThanOrEqual(0);
    expect(r.mile).toBeLessThanOrEqual(100);
  });

  it('offtrackMi is non-negative', () => {
    const r = projectToLeg(UNIT_POLY, 31.0, -89.5);
    expect(r.offtrackMi).toBeGreaterThanOrEqual(0);
  });
});

// ── Golden tests: TS output matches Python engine within tolerance ─────────────
describe('Golden: milepostToLatLon vs Python engine (leg 58)', () => {
  const cases = fixture.milepost_cases;

  let maxLatErr = 0;
  let maxLonErr = 0;

  it(`runs all ${cases.length} milepost cases within tolerance`, () => {
    for (const c of cases) {
      const r = milepostToLatLon(POLY, c.mile);
      const latErr = Math.abs(r.lat - c.lat);
      const lonErr = Math.abs(r.lon - c.lon);
      if (latErr > maxLatErr) maxLatErr = latErr;
      if (lonErr > maxLonErr) maxLonErr = lonErr;
      expect(latErr, `lat err at mile ${c.mile}`).toBeLessThan(LAT_TOL);
      expect(lonErr, `lon err at mile ${c.mile}`).toBeLessThan(LON_TOL);
    }
    console.info(
      `  milepostToLatLon: max lat err=${maxLatErr.toExponential(3)}, ` +
      `max lon err=${maxLonErr.toExponential(3)} (tol=${LAT_TOL})`
    );
  });
});

describe('Golden: projectToLeg vs Python engine (leg 58)', () => {
  const cases = fixture.project_cases;

  let maxMileErr = 0;
  let maxOfftrackErr = 0;
  let sideMismatches = 0;

  it(`runs all ${cases.length} project cases within tolerance`, () => {
    for (const c of cases) {
      const r = projectToLeg(POLY, c.lat, c.lon);
      const mileErr     = Math.abs(r.mile - c.mile);
      const offtrackErr = Math.abs(r.offtrackMi - c.offtrackMi);
      if (mileErr     > maxMileErr)     maxMileErr     = mileErr;
      if (offtrackErr > maxOfftrackErr) maxOfftrackErr = offtrackErr;
      if (r.side !== c.side) sideMismatches++;

      expect(mileErr,     `mile err for ${c._label ?? `(${c.lat},${c.lon})`}`).toBeLessThan(MI_TOL);
      expect(offtrackErr, `offtrack err for ${c._label ?? ''}`).toBeLessThan(MI_TOL);
      expect(r.side,      `side for ${c._label ?? ''}`).toBe(c.side);
    }
    console.info(
      `  projectToLeg: max mile err=${maxMileErr.toExponential(3)}, ` +
      `max offtrack err=${maxOfftrackErr.toExponential(3)}, ` +
      `side mismatches=${sideMismatches}/${cases.length}`
    );
  });
});
