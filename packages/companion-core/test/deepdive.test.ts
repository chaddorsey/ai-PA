/**
 * deepdive.test.ts — Task 1
 *
 * Validates that:
 * - validateBundle accepts bundles with a well-formed deepdives array
 * - validateBundle accepts bundles WITHOUT a deepdives field (backward compat)
 * - DeepDive types are exported from the package index
 */

import { describe, it, expect } from 'vitest';
import { validateBundle } from '../src/bundle.js';
import type { DeepDive, DeepDiveImage, DeepDiveSource, Bundle } from '../src/index.js';

// ── Minimal valid bundle fixture (no deepdives) ───────────────────────────────

const VALID_MIN = {
  leg: '58',
  proxy: false,
  schedule_basis: { kind: 'trip-actual', valid_dates: ['2026-07-11'] },
  stations: [
    {
      code: 'DEN', name: 'Denver', mile: 0, lat: 39.75, lon: -104.99,
      sched_arr: null, sched_dep: '2026-07-11T08:00:00-06:00', dwell_min: 0,
    },
  ],
  geometry: { type: 'LineString', coordinates: [[-104.99, 39.75], [-105.0, 39.8]] },
  units: [
    {
      id: 'sq1', kind: 'squib', mile: 10,
      place: 'Clear Creek Canyon', side: 'right', salience: 4,
      theme: 'geology', text: 'The canyon walls rise.', lat: 39.76, lon: -105.1,
      dur_s: 30, audio: 'audio/sq1.mp3',
    },
  ],
  layers: { guide: {}, lore: {}, science: {}, connections: {}, themes: {} },
  position_table: [[0, 0, 39.75, -104.99], [60, 50, 39.8, -105.0]],
  eta_table: [{ station_code: 'GJT', p10_min: 180, p50_min: 190, p90_min: 210 }],
};

// ── Sample deep-dive fixture ──────────────────────────────────────────────────

const SAMPLE_DEEPDIVE: DeepDive = {
  id: 'dd-casey-jones',
  theme: 'Corridor of Movement',
  title: 'The Wreck of Casey Jones',
  mile: 200,
  trigger_mile: 192,
  nearest_place: 'Vaughan, MS',
  hook: 'On a foggy April morning in 1900, engineer John Luther Jones held his throttle wide open heading into history.',
  body_md: `## The Wreck of Casey Jones\n\nOn April 30, 1900, Illinois Central engineer John Luther Jones — known as Casey — was at the throttle of his fast mail train near Vaughan, Mississippi.\n\n*(Draft placeholder — full story pending review.)*`,
  narration_text: 'On a foggy April morning in 1900, engineer John Luther Jones held his throttle wide open.',
  est_listen_min: 4,
  audio: null,
  images: [] as DeepDiveImage[],
  sources: [] as DeepDiveSource[],
  salience: 4,
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('validateBundle — deepdives field handling', () => {
  it('accepts a bundle without a deepdives field (backward compat)', () => {
    const problems = validateBundle(VALID_MIN);
    expect(problems).toEqual([]);
  });

  it('accepts a bundle with an empty deepdives array', () => {
    const bundle = { ...VALID_MIN, deepdives: [] };
    const problems = validateBundle(bundle);
    expect(problems).toEqual([]);
  });

  it('accepts a bundle with well-formed deepdives entries', () => {
    const bundle = { ...VALID_MIN, deepdives: [SAMPLE_DEEPDIVE] };
    const problems = validateBundle(bundle);
    expect(problems).toEqual([]);
  });

  it('accepts a bundle with multiple deepdive entries', () => {
    const dd2: DeepDive = {
      ...SAMPLE_DEEPDIVE,
      id: 'dd-flood-1927',
      title: 'The Great Flood of 1927',
      mile: 350,
      trigger_mile: 342,
    };
    const dd3: DeepDive = {
      ...SAMPLE_DEEPDIVE,
      id: 'dd-train-in-song',
      title: 'The Train in the Song',
      mile: 600,
      trigger_mile: 592,
    };
    const bundle = { ...VALID_MIN, deepdives: [SAMPLE_DEEPDIVE, dd2, dd3] };
    const problems = validateBundle(bundle);
    expect(problems).toEqual([]);
  });

  it('still validates the rest of the bundle when deepdives is present', () => {
    // Corrupt the leg field — must still surface that error even with deepdives
    const bundle = { ...VALID_MIN, leg: '', deepdives: [SAMPLE_DEEPDIVE] };
    const problems = validateBundle(bundle);
    expect(problems.some((p) => /leg/i.test(p))).toBe(true);
  });
});

describe('DeepDive type exports', () => {
  it('DeepDive fields are accessible (type-level smoke test)', () => {
    const dd: DeepDive = SAMPLE_DEEPDIVE;
    expect(dd.id).toBe('dd-casey-jones');
    expect(dd.theme).toBe('Corridor of Movement');
    expect(dd.audio).toBeNull();
    expect(Array.isArray(dd.images)).toBe(true);
    expect(Array.isArray(dd.sources)).toBe(true);
  });

  it('Bundle type accepts optional deepdives field', () => {
    // Type-level test: assign a bundle with deepdives and verify runtime shape
    const bundle: Partial<Bundle> = {
      ...VALID_MIN,
      deepdives: [SAMPLE_DEEPDIVE],
    };
    expect(bundle.deepdives).toHaveLength(1);
    expect(bundle.deepdives![0].id).toBe('dd-casey-jones');
  });

  it('Bundle type works without deepdives field', () => {
    const bundle: Partial<Bundle> = { ...VALID_MIN };
    expect(bundle.deepdives).toBeUndefined();
  });
});
