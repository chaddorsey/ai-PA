/**
 * types.test.ts — Plan 2, Task 1
 *
 * Validates that:
 * 1. The TypeScript type definitions compile and can be used for type-checked construction.
 * 2. The real proxy bundle (bundles/leg58/bundle.json) conforms to the Bundle type contract.
 *
 * This test is the seam between Plan 1 (bundle producer) and Plan 2 (companion-core consumer).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';
import type {
  Bundle,
  Unit,
  SquibUnit,
  InterstitialUnit,
  Station,
  Position,
  SchedulerSettings,
  Favorite,
  DiveCard,
  EtaResult,
} from '../src/types.js';

// ── Type construction smoke tests ─────────────────────────────────────────────

describe('SquibUnit type', () => {
  it('accepts the canonical squib shape', () => {
    const u: SquibUnit = {
      id: 'u1',
      kind: 'squib',
      mile: 100.5,
      place: 'Raton, NM',
      side: 'left',
      salience: 4,
      theme: 'railroad-history',
      text: 'Raton Pass.',
      lat: 36.9,
      lon: -104.4,
      dur_s: 42.5,
      audio: 'audio/abc.mp3',
    };
    expect(u.kind).toBe('squib');
    expect(u.salience).toBe(4);
  });

  it('accepts optional poi_lat, poi_lon, offtrack_mi', () => {
    const u: SquibUnit = {
      id: 'u-poi',
      kind: 'squib',
      mile: 50,
      place: 'Some Place',
      side: 'right',
      salience: 3,
      theme: 'nature',
      text: 'A squib with POI.',
      lat: 30.5,
      lon: -90.5,
      dur_s: 30,
      audio: 'audio/poi.mp3',
      poi_lat: 30.51,
      poi_lon: -90.51,
      offtrack_mi: 0.2,
    };
    expect(u.poi_lat).toBe(30.51);
  });

  it('accepts place as null', () => {
    const u: SquibUnit = {
      id: 'u-null-place',
      kind: 'squib',
      mile: 10,
      place: null,
      side: 'ahead',
      salience: 2,
      theme: 'geology',
      text: 'No place name.',
      lat: 30.0,
      lon: -90.0,
      dur_s: 25,
      audio: 'audio/x.mp3',
    };
    expect(u.place).toBeNull();
  });
});

describe('InterstitialUnit type', () => {
  it('accepts the canonical interstitial shape', () => {
    const u: InterstitialUnit = {
      id: 'u2',
      kind: 'interstitial',
      from_mi: 95.0,
      to_mi: 110.0,
      place: 'Raton region',
      side: null,
      salience: 2,
      theme: 'geology',
      text: 'The Rockies begin here.',
      lat: 36.8,
      lon: -104.3,
      dur_s: 30.0,
      audio: 'audio/def.mp3',
    };
    expect(u.kind).toBe('interstitial');
    expect(u.from_mi).toBe(95.0);
  });
});

describe('Position type', () => {
  it('accepts all source and direction variants', () => {
    const p: Position = {
      mile: 250,
      lat: 33.5,
      lon: -90.2,
      source: 'gps',
      direction: 1,
      leg: '58',
      stopped: false,
    };
    expect(p.source).toBe('gps');
    expect(p.stopped).toBe(false);
  });
});

describe('SchedulerSettings type', () => {
  it('accepts themes as a Set', () => {
    const s: SchedulerSettings = {
      fillPct: 0.7,
      themes: new Set(['nature', 'civil-rights']),
      highlightOnly: false,
    };
    expect(s.themes.has('nature')).toBe(true);
  });
});

describe('EtaResult type', () => {
  it('has estimated flag', () => {
    const e: EtaResult = { p10: 1_000_000, p50: 1_001_000, p90: 1_002_000, estimated: false };
    expect(e.estimated).toBe(false);
  });
});

describe('Favorite + DiveCard types', () => {
  it('constructs a Favorite with optional dive', () => {
    const unit: SquibUnit = {
      id: 'u1', kind: 'squib', mile: 100, place: 'Test', side: 'left',
      salience: 5, theme: 'civil-rights', text: 'Historic.', lat: 31.5, lon: -90.4,
      dur_s: 50, audio: 'audio/u1.mp3',
    };
    const pos: Position = {
      mile: 100, lat: 31.5, lon: -90.4, source: 'gps', direction: 1, leg: '58', stopped: false,
    };
    const dive: DiveCard = {
      body: 'Deep dive context.',
      sources: ['https://example.com/source'],
      createdAt: Date.now(),
    };
    const fav: Favorite = {
      id: 'fav-001',
      leg: '58',
      unitSnapshot: unit,
      position: pos,
      kind: 'star',
      createdAt: Date.now(),
      dive,
    };
    expect(fav.kind).toBe('star');
    expect(fav.dive?.body).toBe('Deep dive context.');
  });
});

// ── Real proxy bundle conformance ─────────────────────────────────────────────

const BUNDLE_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  '../../../tools/amtrak-position-engine/bundles/leg58/bundle.json',
);

describe('Real proxy bundle (leg58) conforms to Bundle type', () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let raw: any;

  it('loads and parses without error', () => {
    const text = readFileSync(BUNDLE_PATH, 'utf-8');
    raw = JSON.parse(text);
    expect(raw).toBeDefined();
  });

  it('bundle.proxy === true', () => {
    expect(raw.proxy).toBe(true);
  });

  it('bundle.leg is a string', () => {
    expect(typeof raw.leg).toBe('string');
    expect(raw.leg).toBe('58');
  });

  it('bundle.schedule_basis.kind === "trip-actual"', () => {
    expect(raw.schedule_basis?.kind).toBe('trip-actual');
  });

  it('bundle.schedule_basis.valid_dates is a non-empty array of strings', () => {
    expect(Array.isArray(raw.schedule_basis?.valid_dates)).toBe(true);
    expect(raw.schedule_basis.valid_dates.length).toBeGreaterThan(0);
    expect(typeof raw.schedule_basis.valid_dates[0]).toBe('string');
  });

  it('bundle.stations is non-empty with required fields', () => {
    expect(Array.isArray(raw.stations)).toBe(true);
    expect(raw.stations.length).toBeGreaterThan(0);
    for (const s of raw.stations as Station[]) {
      expect(typeof s.code).toBe('string');
      expect(typeof s.name).toBe('string');
      expect(typeof s.mile).toBe('number');
      expect(typeof s.lat).toBe('number');
      expect(typeof s.lon).toBe('number');
      expect(typeof s.dwell_min).toBe('number');
      // sched_arr / sched_dep may be null
      expect(s.sched_arr === null || typeof s.sched_arr === 'string').toBe(true);
      expect(s.sched_dep === null || typeof s.sched_dep === 'string').toBe(true);
    }
  });

  it('bundle.geometry is a LineString with coordinates', () => {
    expect(raw.geometry?.type).toBe('LineString');
    expect(Array.isArray(raw.geometry?.coordinates)).toBe(true);
    expect(raw.geometry.coordinates.length).toBeGreaterThan(0);
    // Each coordinate is [lon, lat]
    const first = raw.geometry.coordinates[0];
    expect(Array.isArray(first)).toBe(true);
    expect(first.length).toBe(2);
    expect(typeof first[0]).toBe('number');
    expect(typeof first[1]).toBe('number');
  });

  it('bundle.units is non-empty', () => {
    expect(Array.isArray(raw.units)).toBe(true);
    expect(raw.units.length).toBeGreaterThan(0);
  });

  it('every unit has required scalar fields', () => {
    for (const u of raw.units as Unit[]) {
      expect(typeof u.id).toBe('string');
      expect(['squib', 'interstitial']).toContain(u.kind);
      // theme may be null (some units in the real bundle have no theme)
      expect(u.theme === null || typeof u.theme === 'string').toBe(true);
      expect(typeof u.text).toBe('string');
      expect(typeof u.lat).toBe('number');
      expect(typeof u.lon).toBe('number');
      expect(typeof u.dur_s).toBe('number');
      expect(typeof u.audio).toBe('string');
      // place may be null
      expect(u.place === null || typeof u.place === 'string').toBe(true);
    }
  });

  it('every unit salience is an integer 1–5', () => {
    for (const u of raw.units as Unit[]) {
      const s = u.salience;
      expect(Number.isInteger(s)).toBe(true);
      expect(s).toBeGreaterThanOrEqual(1);
      expect(s).toBeLessThanOrEqual(5);
    }
  });

  it('squib units have mile field', () => {
    const squibs = (raw.units as Unit[]).filter((u) => u.kind === 'squib') as SquibUnit[];
    expect(squibs.length).toBeGreaterThan(0);
    for (const u of squibs) {
      expect(typeof u.mile).toBe('number');
    }
  });

  it('interstitial units have from_mi and to_mi', () => {
    const ints = (raw.units as Unit[]).filter((u) => u.kind === 'interstitial') as InterstitialUnit[];
    expect(ints.length).toBeGreaterThan(0);
    for (const u of ints) {
      expect(typeof u.from_mi).toBe('number');
      expect(typeof u.to_mi).toBe('number');
      expect(u.from_mi).toBeLessThanOrEqual(u.to_mi);
    }
  });

  it('bundle.position_table is non-empty with 4-element rows', () => {
    expect(Array.isArray(raw.position_table)).toBe(true);
    expect(raw.position_table.length).toBeGreaterThan(0);
    for (const row of raw.position_table as unknown[]) {
      expect(Array.isArray(row)).toBe(true);
      expect((row as unknown[]).length).toBe(4);
      for (const v of row as number[]) {
        expect(typeof v).toBe('number');
      }
    }
  });

  it('bundle.eta_table rows have p10 ≤ p50 ≤ p90', () => {
    expect(Array.isArray(raw.eta_table)).toBe(true);
    expect(raw.eta_table.length).toBeGreaterThan(0);
    for (const row of raw.eta_table as { station_code: string; p10_min: number; p50_min: number; p90_min: number }[]) {
      expect(typeof row.station_code).toBe('string');
      expect(typeof row.p10_min).toBe('number');
      expect(typeof row.p50_min).toBe('number');
      expect(typeof row.p90_min).toBe('number');
      expect(row.p10_min).toBeLessThanOrEqual(row.p50_min);
      expect(row.p50_min).toBeLessThanOrEqual(row.p90_min);
    }
  });

  it('bundle.layers has all five required keys', () => {
    const layers = raw.layers as Record<string, unknown>;
    for (const key of ['guide', 'lore', 'science', 'connections', 'themes']) {
      expect(key in layers).toBe(true);
    }
  });
});
