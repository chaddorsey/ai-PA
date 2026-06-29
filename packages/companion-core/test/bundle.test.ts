/**
 * bundle.test.ts — Plan 2, Task 2
 *
 * Tests for loadBundle() and validateBundle() in src/bundle.ts.
 *
 * Positive: loads the REAL leg58 proxy bundle via an injected resolver and asserts
 *   validateBundle() returns [].
 * Negative: asserts validateBundle() surfaces at least 3 distinct defect kinds.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';
import { loadBundle, validateBundle } from '../src/bundle.js';

const __dir = dirname(fileURLToPath(import.meta.url));

// Path to the real proxy bundle produced by Plan 1
const BUNDLE_PATH = join(
  __dir,
  '../../../tools/amtrak-position-engine/bundles/leg58/bundle.json',
);

// ── Resolver helpers ──────────────────────────────────────────────────────────

/** Resolver that reads the real leg58 bundle from disk. */
async function realResolver(_legId: string): Promise<unknown> {
  const text = readFileSync(BUNDLE_PATH, 'utf-8');
  return JSON.parse(text);
}

/** Resolver that returns an arbitrary in-memory object. */
function memoryResolver(obj: unknown): (legId: string) => Promise<unknown> {
  return async (_legId: string) => obj;
}

// ── Positive test: real proxy bundle ─────────────────────────────────────────

describe('loadBundle with real leg58 proxy bundle', () => {
  it('returns a typed Bundle with zero validation errors', async () => {
    const bundle = await loadBundle('58', realResolver);
    expect(bundle.leg).toBe('58');
    expect(Array.isArray(bundle.units)).toBe(true);
    expect(bundle.units.length).toBeGreaterThan(0);
  });

  it('validateBundle returns [] for the real bundle', () => {
    const raw = JSON.parse(readFileSync(BUNDLE_PATH, 'utf-8'));
    const problems = validateBundle(raw);
    // Must be empty — any content here means the real bundle fails its own contract
    expect(problems).toEqual([]);
  });

  it('returned bundle has schedule_basis with kind trip-actual', async () => {
    const bundle = await loadBundle('58', realResolver);
    expect(bundle.schedule_basis.kind).toBe('trip-actual');
    expect(Array.isArray(bundle.schedule_basis.valid_dates)).toBe(true);
  });

  it('returned bundle has non-empty stations array', async () => {
    const bundle = await loadBundle('58', realResolver);
    expect(bundle.stations.length).toBeGreaterThan(0);
  });

  it('returned bundle has LineString geometry with coordinates', async () => {
    const bundle = await loadBundle('58', realResolver);
    expect(bundle.geometry.type).toBe('LineString');
    expect(bundle.geometry.coordinates.length).toBeGreaterThan(0);
  });

  it('returned bundle has position_table with 4-number rows', async () => {
    const bundle = await loadBundle('58', realResolver);
    expect(bundle.position_table.length).toBeGreaterThan(0);
    const row = bundle.position_table[0];
    expect(row.length).toBe(4);
    for (const v of row) {
      expect(typeof v).toBe('number');
    }
  });

  it('returned bundle has eta_table with p10 ≤ p50 ≤ p90', async () => {
    const bundle = await loadBundle('58', realResolver);
    expect(bundle.eta_table.length).toBeGreaterThan(0);
    for (const row of bundle.eta_table) {
      expect(row.p10_min).toBeLessThanOrEqual(row.p50_min);
      expect(row.p50_min).toBeLessThanOrEqual(row.p90_min);
    }
  });

  it('null place and theme fields do not produce validation errors', () => {
    // The real bundle has many units where place and/or theme are null.
    // validateBundle must tolerate this — null is allowed per contract.
    const raw = JSON.parse(readFileSync(BUNDLE_PATH, 'utf-8'));
    // Confirm the fixture actually has nulls so this test is meaningful
    const hasNullPlace = raw.units.some((u: { place: unknown }) => u.place === null);
    const hasNullTheme = raw.units.some((u: { theme: unknown }) => u.theme === null);
    expect(hasNullPlace).toBe(true);
    expect(hasNullTheme).toBe(true);
    // Must still validate cleanly
    const problems = validateBundle(raw);
    expect(problems).toEqual([]);
  });
});

// ── Negative tests: validateBundle catches real defects ───────────────────────

/** Minimal syntactically-valid bundle for mutation testing. */
const VALID_MIN = {
  leg: '58',
  proxy: false,
  schedule_basis: { kind: 'trip-actual', valid_dates: ['2026-07-11'] },
  stations: [
    { code: 'NOL', name: 'New Orleans', mile: 0, lat: 29.94, lon: -90.07,
      sched_arr: null, sched_dep: '2026-07-12T07:00:00-05:00', dwell_min: 0 },
  ],
  geometry: { type: 'LineString', coordinates: [[-90.07, 29.94], [-90.12, 29.97]] },
  units: [
    { id: 'sq1', kind: 'squib', mile: 10.0,
      place: 'Hammond, LA', side: 'left', salience: 3,
      theme: 'railroad-history', text: 'Historic junction.', lat: 30.5, lon: -90.46,
      dur_s: 38.0, audio: 'audio/sq1.mp3' },
    { id: 'in1', kind: 'interstitial', from_mi: 5.0, to_mi: 25.0,
      place: 'Bayou country', side: null, salience: 2,
      theme: 'nature', text: 'Cypress swamps.', lat: 30.3, lon: -90.5,
      dur_s: 28.0, audio: 'audio/in1.mp3' },
  ],
  layers: { guide: {}, lore: {}, science: {}, connections: {}, themes: {} },
  position_table: [[0, 0, 29.94, -90.07], [60, 50, 31.0, -90.4]],
  eta_table: [{ station_code: 'HMD', p10_min: 56, p50_min: 61, p90_min: 73 }],
};

describe('validateBundle — negative cases', () => {
  it('flags salience out of range (7 > 5)', () => {
    const bad = {
      ...VALID_MIN,
      units: [{ ...VALID_MIN.units[0], salience: 7 }],
    };
    const problems = validateBundle(bad);
    expect(problems.length).toBeGreaterThan(0);
    expect(problems.some((p) => /salience/i.test(p))).toBe(true);
  });

  it('flags salience of 0 (below minimum of 1)', () => {
    const bad = {
      ...VALID_MIN,
      units: [{ ...VALID_MIN.units[0], salience: 0 }],
    };
    const problems = validateBundle(bad);
    expect(problems.some((p) => /salience/i.test(p))).toBe(true);
  });

  it('flags a squib missing its mile field', () => {
    const { mile: _mile, ...squibNoMile } = VALID_MIN.units[0] as { mile: number; [k: string]: unknown };
    const bad = { ...VALID_MIN, units: [squibNoMile] };
    const problems = validateBundle(bad);
    expect(problems.some((p) => /mile/i.test(p))).toBe(true);
  });

  it('flags an interstitial missing to_mi', () => {
    const { to_mi: _to, ...intNoTo } = VALID_MIN.units[1] as { to_mi: number; [k: string]: unknown };
    const bad = { ...VALID_MIN, units: [intNoTo] };
    const problems = validateBundle(bad);
    expect(problems.some((p) => /to_mi/i.test(p))).toBe(true);
  });

  it('flags empty stations array', () => {
    const bad = { ...VALID_MIN, stations: [] };
    const problems = validateBundle(bad);
    expect(problems.some((p) => /stations/i.test(p))).toBe(true);
  });

  it('flags empty units array', () => {
    const bad = { ...VALID_MIN, units: [] };
    const problems = validateBundle(bad);
    expect(problems.some((p) => /units/i.test(p))).toBe(true);
  });

  it('flags empty geometry coordinates', () => {
    const bad = {
      ...VALID_MIN,
      geometry: { type: 'LineString', coordinates: [] },
    };
    const problems = validateBundle(bad);
    expect(problems.some((p) => /geometry|coordinates/i.test(p))).toBe(true);
  });

  it('flags a position_table row that is not a 4-number array', () => {
    const bad = {
      ...VALID_MIN,
      position_table: [[0, 0, 29.94]],  // only 3 numbers
    };
    const problems = validateBundle(bad);
    expect(problems.some((p) => /position_table/i.test(p))).toBe(true);
  });

  it('flags an eta_table row where p10 > p50', () => {
    const bad = {
      ...VALID_MIN,
      eta_table: [{ station_code: 'HMD', p10_min: 80, p50_min: 60, p90_min: 90 }],
    };
    const problems = validateBundle(bad);
    expect(problems.some((p) => /eta_table|p10|p50/i.test(p))).toBe(true);
  });

  it('flags an eta_table row where p50 > p90', () => {
    const bad = {
      ...VALID_MIN,
      eta_table: [{ station_code: 'HMD', p10_min: 50, p50_min: 95, p90_min: 80 }],
    };
    const problems = validateBundle(bad);
    expect(problems.some((p) => /eta_table|p50|p90/i.test(p))).toBe(true);
  });

  it('flags an invalid schedule_basis.kind', () => {
    const bad = {
      ...VALID_MIN,
      schedule_basis: { kind: 'unknown-kind', valid_dates: [] },
    };
    const problems = validateBundle(bad);
    expect(problems.some((p) => /schedule_basis|kind/i.test(p))).toBe(true);
  });

  it('flags missing leg field', () => {
    const { leg: _leg, ...noLeg } = VALID_MIN;
    const problems = validateBundle(noLeg);
    expect(problems.some((p) => /\bleg\b/i.test(p))).toBe(true);
  });

  it('returns [] for the minimal valid bundle', () => {
    const problems = validateBundle(VALID_MIN);
    expect(problems).toEqual([]);
  });

  it('loadBundle throws when resolver returns invalid data', async () => {
    const bad = { ...VALID_MIN, stations: [] };  // empty stations = invalid
    await expect(loadBundle('58', memoryResolver(bad))).rejects.toThrow(/stations/i);
  });

  it('loadBundle passes through valid minimal bundle', async () => {
    const bundle = await loadBundle('58', memoryResolver(VALID_MIN));
    expect(bundle.leg).toBe('58');
  });
});
